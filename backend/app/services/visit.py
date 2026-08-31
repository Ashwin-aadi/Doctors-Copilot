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

from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

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
    VisitState.RESULTS_UPLOADED: "no completed report uploaded for this visit yet",
    VisitState.PRESCRIBED: "prescription must be approved and locked first",
}


# The forward order, used to tell "earlier" from "later" when a clinician
# steps a visit back.
STATE_ORDER: list[VisitState] = [
    VisitState.TRIAGED,
    VisitState.LABS_SUGGESTED,
    VisitState.LABS_APPROVED,
    VisitState.RESULTS_UPLOADED,
    VisitState.BRIEF_READY,
    VisitState.CONSULTED,
    VisitState.PRESCRIBED,
]


def is_earlier(target: VisitState, current: VisitState) -> bool:
    return STATE_ORDER.index(target) < STATE_ORDER.index(current)


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
        # This visit's own report. A document uploaded for a different episode
        # of care used to satisfy this, letting a visit with nothing uploaded
        # walk straight past the stage that collects the reports.
        done = await db.execute(
            select(Document.id)
            .where(Document.visit_id == visit.id, Document.status == "done")
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


# The stage the lab order is drafted and signed at. Stepping back to it, or
# past it, is what puts the order back in the doctor's hands.
_LAB_ORDER_STAGE = VisitState.LABS_SUGGESTED


async def _reopen_lab_order(db: AsyncSession, visit: Visit, target: VisitState) -> UUID | None:
    """Give a visit stepped back to the lab-order stage an editable order.

    The doctor's reason for stepping back is almost always the order itself --
    the wrong test, a test the lab cannot run, one that should have been added.
    Leaving the signed order in place makes the trip back pointless: the panel
    renders read-only and there is nothing to change.

    A signed order is not reopened in place. It carries a practitioner's
    signature over a content hash, and `lab_order_lock` raises `record_locked`
    on any UPDATE to it, so editing one would either destroy what the signature
    covers or fail at the database. Instead the visit gets a *new draft*
    carrying the signed order's items, pointing back at it through
    `supersedes_id`. The doctor edits and re-signs that; the original stays on
    the record exactly as it was signed.

    Returns the id of the order that was superseded, or None if there was
    nothing to reopen -- no order yet, or one still an unsigned draft, which is
    already editable and is left alone so an in-progress edit is not discarded.
    """
    if is_earlier(_LAB_ORDER_STAGE, target) or visit.lab_order_id is None:
        return None

    signed = await db.get(LabOrder, visit.lab_order_id)
    if signed is None or not signed.locked:
        return None

    amendment = LabOrder(
        id=uuid4(),
        visit_id=signed.visit_id,
        patient_id=signed.patient_id,
        # A copy, not a reference: the amendment's items must be free to
        # diverge without touching the signed row's JSONB.
        items=deepcopy(signed.items or []),
        status="draft",
        locked=False,
        supersedes_id=signed.id,
    )
    db.add(amendment)
    await db.flush()
    visit.lab_order_id = amendment.id
    return signed.id


async def rewind(
    db: AsyncSession,
    visit_id: UUID,
    target: VisitState,
    *,
    actor_id: UUID | None = None,
) -> Visit:
    """Step a visit back to an earlier stage.

    Real consultations do not run in one direction: a report comes back
    unreadable, the brief was built before the second lab arrived, the doctor
    marked the visit consulted by mistake. Without this the visit is stuck and
    the only way back is a database edit.

    What this deliberately does NOT do is undo signed work. A locked lab order
    or prescription stays locked and stays on the record -- an approval carries
    a practitioner's signature and a content hash, so it is amended, never
    silently reopened. Moving back only changes which stage the visit is
    working at; every guard is re-checked on the way forward again.

    Stepping back to the lab-order stage does reopen the order for editing, by
    the amendment route: see `_reopen_lab_order`.
    """
    visit = await _load(db, visit_id)
    current = VisitState(visit.state)

    if target is current:
        return visit

    if not is_earlier(target, current):
        raise ApiError(
            "CONFLICT",
            f"{target.value} is not earlier than {current.value}; use advance instead",
            status_code=409,
            details={"from": current.value, "to": target.value},
        )

    visit.state = target.value
    visit.updated_at = datetime.now(UTC)
    amended_from = await _reopen_lab_order(db, visit, target)
    await db.commit()
    await db.refresh(visit)

    log.info(
        "visit_rewound",
        visit_id=str(visit.id),
        **{"from": current.value},
        to=target.value,
        actor_id=str(actor_id) if actor_id else None,
        lab_order_amended_from=str(amended_from) if amended_from else None,
    )

    await publish(
        VISIT_CHANNEL,
        {
            "visit_id": str(visit.id),
            "patient_id": str(visit.patient_id),
            "doctor_id": str(visit.doctor_id) if visit.doctor_id else None,
            "from": current.value,
            "state": target.value,
            "actor_id": str(actor_id) if actor_id else None,
            "updated_at": visit.updated_at.isoformat(),
        },
    )
    return visit


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


async def _documents(db: AsyncSession, visit_id: UUID) -> list[DocumentOut]:
    """The reports uploaded for this visit.

    Scoped to the visit, not the patient. A patient accumulates documents
    across every episode of care they have ever had; showing all of them here
    put another visit's blood work in this visit's report summary, and fed the
    lot to the copilot brief.
    """
    documents = (
        await db.execute(select(Document).where(Document.visit_id == visit_id))
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

            # Read, never generate. This runs on every page load and every
            # socket update, and building here cost the caller a full
            # retrieval and generation -- around twenty seconds -- which made
            # advancing a visit feel broken. `POST /copilot/brief` builds it;
            # this serves what that produced.
            brief = await build_brief(visit.id, db, allow_build=False)
        except Exception as exc:  # noqa: BLE001
            log.warning("brief_assembly_failed", visit_id=str(visit.id), error=str(exc))

    return VisitOut(
        id=visit.id,
        patient_id=visit.patient_id,
        doctor_id=visit.doctor_id,
        state=state,
        triage=triage,
        lab_order_id=visit.lab_order_id,
        documents=await _documents(db, visit.id),
        brief=brief,
        safety=await _safety(db, visit),
        queue=await _queue_entry(db, visit.patient_id),
        updated_at=visit.updated_at,
    )
