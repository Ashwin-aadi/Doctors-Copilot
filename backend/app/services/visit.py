"""Visit state machine and full-visit assembly.

The visit is the spine every other feature hangs off: triage finalises it, the
lab order locks it forward, a finished OCR job moves it again, the copilot brief
marks it ready for the doctor, and the signed prescription closes it.

    TRIAGED          --triage.finalize-->        LABS_SUGGESTED
    LABS_SUGGESTED   --lab-order lock-->         LABS_APPROVED
    LABS_APPROVED    --document.status==done-->  RESULTS_UPLOADED
    RESULTS_UPLOADED --build_brief-->            BRIEF_READY
    BRIEF_READY      --doctor advance-->         CONSULTED
    CONSULTED        --prescription lock-->      PRESCRIBED

Anything else is a 409 CONFLICT. Every accepted transition publishes
`visit.updated` on Redis pub/sub, which is what `/ws/visit/{id}` fans out.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.events import publish
from app.core.logging import get_logger
from app.db.models.clinical import LabOrder, LabResult, Prescription, TriageSession, Visit
from app.db.models.document import Document
from app.db.models.scheduling import QueueEntry
from app.schemas.copilot import CopilotBrief
from app.schemas.document import DocumentOut, LabResultOut
from app.schemas.ml import InteractionReport
from app.schemas.scheduling import QueueEntryOut
from app.schemas.triage import TriageResult, colour_for_esi
from app.schemas.visit import VisitOut, VisitState

log = get_logger(__name__)

VISIT_CHANNEL = "visit.updated"

TRANSITIONS: dict[VisitState, VisitState] = {
    VisitState.TRIAGED: VisitState.LABS_SUGGESTED,
    VisitState.LABS_SUGGESTED: VisitState.LABS_APPROVED,
    VisitState.LABS_APPROVED: VisitState.RESULTS_UPLOADED,
    VisitState.RESULTS_UPLOADED: VisitState.BRIEF_READY,
    VisitState.BRIEF_READY: VisitState.CONSULTED,
    VisitState.CONSULTED: VisitState.PRESCRIBED,
}

# What has to be true in the database before each transition is allowed. A
# doctor cannot mark a visit CONSULTED before a brief exists, and cannot close
# it PRESCRIBED before a prescription has actually been signed and locked.
_GUARD_MESSAGES: dict[VisitState, str] = {
    VisitState.LABS_APPROVED: "lab order must be approved and locked first",
    VisitState.RESULTS_UPLOADED: "no completed document for this patient yet",
    VisitState.PRESCRIBED: "prescription must be approved and locked first",
}


def next_state(current: VisitState) -> VisitState | None:
    return TRANSITIONS.get(current)


def can_advance(current: VisitState, target: VisitState) -> bool:
    return TRANSITIONS.get(current) == target


async def _load(db: AsyncSession, visit_id: UUID) -> Visit:
    visit = await db.get(Visit, visit_id)
    if visit is None:
        raise ApiError("NOT_FOUND", "visit not found", status_code=404)
    return visit


async def _guard_satisfied(db: AsyncSession, visit: Visit, target: VisitState) -> bool:
    if target is VisitState.LABS_APPROVED:
        if visit.lab_order_id is None:
            return False
        order = await db.get(LabOrder, visit.lab_order_id)
        return bool(order and order.locked)

    if target is VisitState.RESULTS_UPLOADED:
        done = await db.execute(
            select(Document.id)
            .where(Document.patient_id == visit.patient_id, Document.status == "done")
            .limit(1)
        )
        return done.scalar_one_or_none() is not None

    if target is VisitState.PRESCRIBED:
        signed = await db.execute(
            select(Prescription.id)
            .where(Prescription.visit_id == visit.id, Prescription.locked.is_(True))
            .limit(1)
        )
        return signed.scalar_one_or_none() is not None

    return True


async def advance(
    db: AsyncSession,
    visit_id: UUID,
    target: VisitState | None = None,
    *,
    actor_id: UUID | None = None,
    force_guard: bool = False,
) -> Visit:
    """Move a visit one step forward. `target` defaults to the next legal state.

    `force_guard=True` skips the database precondition check and is used only by
    the internal callers that have just created the thing the guard looks for,
    within the same uncommitted transaction.
    """

    visit = await _load(db, visit_id)
    current = VisitState(visit.state)
    intended = target or next_state(current)

    if intended is None:
        raise ApiError(
            "CONFLICT",
            f"visit is already in its final state ({current.value})",
            status_code=409,
        )

    if not can_advance(current, intended):
        raise ApiError(
            "CONFLICT",
            f"illegal transition {current.value} -> {intended.value}",
            status_code=409,
            details={"from": current.value, "to": intended.value},
        )

    if not force_guard and not await _guard_satisfied(db, visit, intended):
        raise ApiError(
            "CONFLICT",
            _GUARD_MESSAGES.get(intended, "precondition for this transition is not met"),
            status_code=409,
            details={"from": current.value, "to": intended.value},
        )

    visit.state = intended.value
    visit.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(visit)

    await publish(
        VISIT_CHANNEL,
        {
            "visit_id": str(visit.id),
            "patient_id": str(visit.patient_id),
            "doctor_id": str(visit.doctor_id) if visit.doctor_id else None,
            "from": current.value,
            "state": intended.value,
            "actor_id": str(actor_id) if actor_id else None,
            "updated_at": visit.updated_at.isoformat(),
        },
    )

    # The patient's own plain-language corpus is rebuilt on every transition, so
    # the chatbot can answer about a lab or prescription the moment it lands.
    try:
        from app.rag.ingest_patient import sync_patient as sync_chat_corpus

        await sync_chat_corpus(db, visit.patient_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("patient_corpus_sync_failed", visit_id=str(visit.id), error=str(exc))

    # Keep the knowledge graph in step with the relational record.
    try:
        from app.kg.ingest import sync_patient

        await sync_patient(visit.patient_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("kg_sync_failed", visit_id=str(visit.id), error=str(exc))

    log.info(
        "visit_advanced",
        visit_id=str(visit.id),
        **{"from": current.value, "to": intended.value},
    )
    return visit


# ------------------------------------------------------------- assembly


def _lab_out(lab: LabResult) -> LabResultOut:
    return LabResultOut(
        test_name=lab.test_name,
        normalized_name=lab.normalized_name,
        value=lab.value_num if lab.value_num is not None else (lab.value_text or ""),
        unit=lab.unit,
        ref_low=lab.ref_low,
        ref_high=lab.ref_high,
        flag=lab.flag if lab.flag in ("critical", "high", "low", "normal") else "unknown",
        confidence=lab.confidence,
    )


async def _documents(db: AsyncSession, patient_id: UUID) -> list[DocumentOut]:
    documents = (
        await db.execute(select(Document).where(Document.patient_id == patient_id))
    ).scalars().all()
    if not documents:
        return []

    labs = (
        await db.execute(
            select(LabResult).where(
                LabResult.document_id.in_([d.id for d in documents]),
            )
        )
    ).scalars().all()
    by_document: dict[UUID, list[LabResultOut]] = {}
    for lab in labs:
        if lab.document_id:
            by_document.setdefault(lab.document_id, []).append(_lab_out(lab))

    return [
        DocumentOut(
            id=doc.id,
            patient_id=doc.patient_id,
            file_id=doc.file_id,
            status=doc.status if doc.status in ("queued", "processing", "done", "failed") else "queued",
            engine=doc.engine,
            mean_confidence=doc.mean_confidence,
            text=doc.text,
            labs=by_document.get(doc.id, []),
            error=doc.error,
            test_name=doc.test_name,
        )
        for doc in documents
    ]


async def _queue_entry(db: AsyncSession, patient_id: UUID) -> QueueEntryOut | None:
    entry = (
        await db.execute(
            select(QueueEntry)
            .where(QueueEntry.patient_id == patient_id)
            .where(QueueEntry.status.in_(("waiting", "in_consult")))
            .order_by(QueueEntry.enqueued_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if entry is None:
        return None

    from app.db.models.patient import Patient

    patient = await db.get(Patient, patient_id)
    waited = max(0, int((datetime.now(UTC) - entry.enqueued_at).total_seconds() // 60))
    ahead = (
        await db.execute(
            select(QueueEntry.id)
            .where(QueueEntry.clinic_id == entry.clinic_id, QueueEntry.status == "waiting")
            .where(QueueEntry.severity_esi <= entry.severity_esi)
            .where(QueueEntry.enqueued_at < entry.enqueued_at)
        )
    ).scalars().all()

    return QueueEntryOut(
        id=entry.id,
        patient_id=entry.patient_id,
        patient_name=patient.name if patient else "",
        doctor_id=entry.doctor_id,
        clinic_id=entry.clinic_id,
        severity_esi=entry.severity_esi,
        triage_colour=colour_for_esi(entry.severity_esi),
        emergency=entry.emergency,
        position=len(ahead) + 1,
        waited_minutes=waited,
        estimated_wait_minutes=len(ahead) * 10,
        status=entry.status if entry.status in ("waiting", "in_consult", "done", "cancelled") else "waiting",
        reasons=[],
    )


async def _safety(db: AsyncSession, visit: Visit) -> InteractionReport | None:
    """Drug-interaction and allergy report, via Virat's ML tools behind the
    circuit breaker. Returns None rather than an empty report when nothing to
    check, so the UI can tell "no medicines" from "checked, all clear"."""

    from app.db.models.patient import Patient
    from app.rag.tool_bridge import check_interactions

    patient = await db.get(Patient, visit.patient_id)
    medications = list(patient.medications or []) if patient else []
    if not medications:
        return None

    raw = await check_interactions(visit.patient_id, medications)
    return InteractionReport(
        pairs=raw.get("pairs", []),
        allergy_conflicts=raw.get("allergy_conflicts", []),
        contraindications=raw.get("contraindications", []),
        generated_at=datetime.now(UTC),
    )


async def assemble(db: AsyncSession, visit_id: UUID, *, with_brief: bool = True) -> VisitOut:
    """The whole visit in one response -- triage, documents, brief, safety, queue."""

    visit = await _load(db, visit_id)

    triage: TriageResult | None = None
    if visit.triage_session_id:
        session = await db.get(TriageSession, visit.triage_session_id)
        if session is not None and session.result:
            triage = TriageResult.model_validate(session.result)

    brief: CopilotBrief | None = None
    state = VisitState(visit.state)
    if with_brief and state in (
        VisitState.BRIEF_READY,
        VisitState.CONSULTED,
        VisitState.PRESCRIBED,
    ):
        try:
            from app.rag.clinical_rag import build_brief

            brief = await build_brief(visit.id, db)
        except Exception as exc:  # noqa: BLE001
            log.warning("brief_assembly_failed", visit_id=str(visit.id), error=str(exc))

    return VisitOut(
        id=visit.id,
        patient_id=visit.patient_id,
        doctor_id=visit.doctor_id,
        state=state,
        triage=triage,
        lab_order_id=visit.lab_order_id,
        documents=await _documents(db, visit.patient_id),
        brief=brief,
        safety=await _safety(db, visit),
        queue=await _queue_entry(db, visit.patient_id),
        updated_at=visit.updated_at,
    )
