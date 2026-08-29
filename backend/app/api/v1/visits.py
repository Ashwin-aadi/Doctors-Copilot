"""Visit read and advance endpoints.

`GET /visits/{id}` returns the whole visit -- triage, documents, brief, safety
report and queue position -- in one response, so the doctor's screen needs a
single call. `POST /visits/{id}/advance` is the only way a visit changes state
from outside; illegal transitions come back as 409 CONFLICT.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user, require_role
from app.core.errors import ApiError
from app.db.session import get_db
from app.schemas.visit import VisitOut, VisitState
from app.services import visit as visit_service

router = APIRouter(prefix="/visits", tags=["visits"])


class AdvanceIn(BaseModel):
    target: VisitState | None = None


class VisitSummary(BaseModel):
    """Deliberately thinner than `VisitOut`: a list screen wants a row per
    visit, not the assembled brief/safety/document payload for each one.
    """

    id: UUID
    patient_id: UUID
    patient_name: str | None = None
    doctor_id: UUID | None = None
    doctor_name: str | None = None
    state: VisitState
    severity_esi: int | None = None
    triage_colour: str | None = None
    lab_order_id: UUID | None = None
    document_count: int = 0
    created_at: datetime
    updated_at: datetime


class TranscriptTurn(BaseModel):
    role: str
    content: str


class TranscriptOut(BaseModel):
    visit_id: UUID
    session_id: UUID | None = None
    turns: list[TranscriptTurn] = []


async def _assert_may_read(db: AsyncSession, visit_id: UUID, user: CurrentUser) -> None:
    if user.role in ("doctor", "staff", "admin"):
        return

    from app.db.models.clinical import Visit
    from app.rag.patient_chat import resolve_patient_for_user

    record = await db.get(Visit, visit_id)
    patient = await resolve_patient_for_user(db, user.id)
    if record is None or patient is None or record.patient_id != patient.id:
        # Never distinguish "not yours" from "does not exist".
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)


@router.get("", response_model=list[VisitSummary])
async def list_visits(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[VisitSummary]:
    """A patient sees their own visits; a clinician sees the ones assigned to
    them. Staff and admin see the whole clinic, since they work the desk for
    every doctor in it.
    """
    from app.db.models.clinical import TriageSession, Visit
    from app.db.models.document import Document
    from app.db.models.patient import Patient
    from app.db.models.scheduling import Doctor
    from app.rag.patient_chat import resolve_patient_for_user

    stmt = select(Visit)
    if user.role == "patient":
        patient = await resolve_patient_for_user(db, user.id)
        if patient is None:
            return []
        stmt = stmt.where(Visit.patient_id == patient.id)
    elif user.role == "doctor":
        doctor_id = (
            await db.execute(select(Doctor.id).where(Doctor.user_id == user.id))
        ).scalar_one_or_none()
        if doctor_id is None:
            return []
        stmt = stmt.where(Visit.doctor_id == doctor_id)

    visits = list((await db.execute(stmt.order_by(Visit.created_at.desc()))).scalars())
    if not visits:
        return []

    names = dict(
        (await db.execute(select(Patient.id, Patient.name).where(
            Patient.id.in_([v.patient_id for v in visits])
        ))).all()
    )
    doctor_ids = [v.doctor_id for v in visits if v.doctor_id]
    doctors = (
        dict((await db.execute(select(Doctor.id, Doctor.name).where(
            Doctor.id.in_(doctor_ids)
        ))).all())
        if doctor_ids
        else {}
    )
    sessions = dict(
        (await db.execute(select(TriageSession.id, TriageSession.result).where(
            TriageSession.id.in_([v.triage_session_id for v in visits if v.triage_session_id])
        ))).all()
    )

    rows: list[VisitSummary] = []
    for v in visits:
        result = sessions.get(v.triage_session_id) or {}
        count = (
            await db.execute(
                select(Document.id).where(Document.patient_id == v.patient_id)
            )
        ).scalars()
        rows.append(
            VisitSummary(
                id=v.id,
                patient_id=v.patient_id,
                patient_name=names.get(v.patient_id),
                doctor_id=v.doctor_id,
                doctor_name=doctors.get(v.doctor_id) if v.doctor_id else None,
                state=v.state,
                severity_esi=result.get("severity_esi"),
                triage_colour=result.get("triage_colour"),
                lab_order_id=v.lab_order_id,
                document_count=len(list(count)),
                created_at=v.created_at,
                updated_at=v.updated_at,
            )
        )
    return rows


@router.get("/{visit_id}/transcript", response_model=TranscriptOut)
async def get_visit_transcript(
    visit_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> TranscriptOut:
    """The triage interview behind a visit. The doctor reads this alongside the
    triage result -- the scored output alone loses the patient's own wording,
    which is often the useful part.
    """
    from app.db.models.clinical import TriageSession, Visit

    await _assert_may_read(db, visit_id, user)
    record = await db.get(Visit, visit_id)
    if record is None:
        raise ApiError("NOT_FOUND", "visit not found", status_code=404)
    if record.triage_session_id is None:
        return TranscriptOut(visit_id=visit_id)

    session = await db.get(TriageSession, record.triage_session_id)
    turns = [
        TranscriptTurn(role=str(t.get("role", "")), content=str(t.get("content", "")))
        for t in (session.transcript or [])
        if isinstance(t, dict)
    ]
    return TranscriptOut(
        visit_id=visit_id, session_id=record.triage_session_id, turns=turns
    )


@router.get("/{visit_id}", response_model=VisitOut)
async def get_visit(
    visit_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> VisitOut:
    await _assert_may_read(db, visit_id, user)
    return await visit_service.assemble(db, visit_id)


@router.post("/{visit_id}/advance", response_model=VisitOut)
async def advance_visit(
    visit_id: UUID,
    body: AdvanceIn | None = None,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role("doctor", "staff", "admin")),
) -> VisitOut:
    target = body.target if body else None
    await visit_service.advance(db, visit_id, target, actor_id=user.id)
    return await visit_service.assemble(db, visit_id)
