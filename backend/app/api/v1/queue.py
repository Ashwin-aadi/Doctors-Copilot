from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from app.core.deps import CurrentUser, get_current_user, require_role
from app.core.errors import ApiError
from app.db.models.scheduling import Doctor, QueueEntry
from app.db.session import SessionLocal
from app.services.queueing.pq import enqueue, escalate, pop_next, snapshot
from app.services.queueing.schemas import QueueEntryOut

router = APIRouter(prefix="/queue", tags=["queue"])


class WalkInCreate(BaseModel):
    clinic_id: UUID
    patient_id: UUID
    doctor_id: UUID | None = None
    severity_esi: int = 4


class EscalateBody(BaseModel):
    reason: str


async def _least_loaded_doctor(clinic_id: UUID) -> UUID:
    async with SessionLocal() as session:
        doctors = (
            await session.execute(select(Doctor.id).where(Doctor.clinic_id == clinic_id).order_by(Doctor.id))
        ).scalars().all()
        if not doctors:
            raise ApiError("NOT_FOUND", "no doctors assigned to this clinic", status_code=404)
        counts = dict(
            (
                await session.execute(
                    select(QueueEntry.doctor_id, func.count(QueueEntry.id))
                    .where(QueueEntry.doctor_id.in_(doctors))
                    .where(QueueEntry.status == "waiting")
                    .group_by(QueueEntry.doctor_id)
                )
            ).all()
        )
    return min(doctors, key=lambda d: (counts.get(d, 0), str(d)))


@router.get("/{clinic_id}", response_model=list[QueueEntryOut])
async def get_queue(clinic_id: UUID, user: CurrentUser = Depends(get_current_user)) -> list[QueueEntryOut]:
    now = datetime.now(timezone.utc)
    return await snapshot(clinic_id, now=now)


@router.post("/walk-in", response_model=QueueEntryOut, status_code=201)
async def walk_in(
    body: WalkInCreate, user: CurrentUser = Depends(require_role("staff", "doctor"))
) -> QueueEntryOut:
    now = datetime.now(timezone.utc)
    doctor_id = body.doctor_id or await _least_loaded_doctor(body.clinic_id)
    entry = QueueEntry(
        id=uuid4(),
        appointment_id=None,
        patient_id=body.patient_id,
        doctor_id=doctor_id,
        clinic_id=body.clinic_id,
        severity_esi=body.severity_esi,
        emergency=False,
        enqueued_at=now,
        status="waiting",
    )
    return await enqueue(entry, now=now)


@router.post("/{clinic_id}/next", response_model=QueueEntryOut | None)
async def next_in_queue(
    clinic_id: UUID, doctor_id: UUID, user: CurrentUser = Depends(require_role("doctor", "staff"))
) -> QueueEntryOut | None:
    now = datetime.now(timezone.utc)
    return await pop_next(clinic_id, doctor_id, now=now)


@router.post("/{queue_entry_id}/escalate", response_model=QueueEntryOut)
async def escalate_queue(
    queue_entry_id: UUID, body: EscalateBody, user: CurrentUser = Depends(require_role("doctor", "staff"))
) -> QueueEntryOut:
    now = datetime.now(timezone.utc)
    try:
        return await escalate(queue_entry_id, body.reason, now=now)
    except LookupError as exc:
        raise ApiError("NOT_FOUND", str(exc), status_code=404)
