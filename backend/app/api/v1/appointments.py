from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import CurrentUser, get_current_user, require_captcha
from app.core.errors import ApiError, not_implemented
from app.db.models.scheduling import Appointment, QueueEntry
from app.db.session import SessionLocal
from app.services.queueing.pq import enqueue
from app.services.queueing.schemas import QueueEntryOut
from app.services.scheduling.optimizer import rank_doctors
from app.services.scheduling.repo import booked_slots as repo_booked_slots
from app.services.scheduling.schemas import DoctorRankedOut
from app.services.scheduling.slots import free_slots

router = APIRouter(prefix="/appointments", tags=["appointments"])


class AppointmentCreate(BaseModel):
    patient_id: UUID
    specialty: str
    lat: float | None = None
    lng: float | None = None
    preferred_from: datetime | None = None
    doctor_id: UUID | None = None
    language: str | None = None
    scheme: str | None = None
    severity_esi: int = 4
    # N2.1: if a triage session already ran for this booking, its own
    # severity/specialty must win over the body defaults above -- booking
    # must not silently default a triaged RED patient down to the routine
    # tier-4 default. Additive, optional field; omitting it keeps the exact
    # CP1 request shape working unchanged.
    triage_session_id: UUID | None = None


class AppointmentPatch(BaseModel):
    status: str | None = None
    slot_start: datetime | None = None
    slot_end: datetime | None = None


def _appointment_dict(a: Appointment) -> dict:
    return {
        "id": a.id,
        "patient_id": a.patient_id,
        "doctor_id": a.doctor_id,
        "clinic_id": a.clinic_id,
        "slot_start": a.slot_start,
        "slot_end": a.slot_end,
        "status": a.status,
    }


@router.get("")
async def list_appointments(
    patient_id: UUID | None = None, user: CurrentUser = Depends(get_current_user)
) -> list[dict]:
    stmt = select(Appointment)
    if patient_id is not None:
        stmt = stmt.where(Appointment.patient_id == patient_id)
    async with SessionLocal() as session:
        rows = (await session.execute(stmt)).scalars().all()
        return [_appointment_dict(a) for a in rows]


@router.post("", status_code=201)
async def create_appointment(
    body: AppointmentCreate,
    user: CurrentUser = Depends(get_current_user),
    _captcha: None = Depends(require_captcha),
) -> dict:
    now = datetime.now(UTC)
    date_from = body.preferred_from or now
    if date_from.tzinfo is None:
        date_from = date_from.replace(tzinfo=UTC)

    specialty = body.specialty
    severity_esi = body.severity_esi
    if body.triage_session_id is not None:
        from app.core.errors import ApiError as _ApiError
        from app.rag import triage_rag

        try:
            async with SessionLocal() as session:
                triage_result = await triage_rag.get_result(session, body.triage_session_id)
            specialty = triage_result.specialty or specialty
            severity_esi = triage_result.severity_esi
        except _ApiError:
            # triage session exists but hasn't been finalized yet -- fall
            # back to whatever the caller supplied rather than failing the
            # booking outright.
            pass

    ranked = await rank_doctors(
        specialty=specialty,
        lat=body.lat,
        lng=body.lng,
        date_from=date_from,
        max_fee=None,
        language=body.language,
        scheme=body.scheme,
        now=now,
    )
    if not ranked:
        raise ApiError("NOT_FOUND", "no doctor available for this specialty", status_code=404)

    chosen: DoctorRankedOut
    if body.doctor_id is not None:
        matches = [d for d in ranked if d.doctor_id == body.doctor_id]
        if not matches:
            raise ApiError("NOT_FOUND", "requested doctor has no availability in the horizon", status_code=404)
        chosen = matches[0]
    else:
        chosen = ranked[0]

    date_to = date_from.date() + timedelta(days=7)
    booked = (await repo_booked_slots([chosen.doctor_id], date_from.date(), date_to)).get(chosen.doctor_id, [])
    candidate_slots = free_slots(chosen.doctor_id, chosen.clinic_id, date_from.date(), date_to, booked)
    slot = next((s for s in candidate_slots if s[0] == chosen.next_slot), None)
    if slot is None:
        raise ApiError("CONFLICT", "selected slot is no longer available", status_code=409)
    slot_start, slot_end = slot

    async with SessionLocal() as session:
        appt = Appointment(
            id=uuid4(),
            patient_id=body.patient_id,
            doctor_id=chosen.doctor_id,
            clinic_id=chosen.clinic_id,
            slot_start=slot_start,
            slot_end=slot_end,
            status="booked",
        )
        session.add(appt)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ApiError("CONFLICT", "slot already booked", status_code=409) from exc

    queue_entry = QueueEntry(
        id=uuid4(),
        appointment_id=appt.id,
        patient_id=body.patient_id,
        doctor_id=chosen.doctor_id,
        clinic_id=chosen.clinic_id,
        severity_esi=severity_esi,
        emergency=False,
        enqueued_at=now,
        status="waiting",
    )
    queue_out: QueueEntryOut = await enqueue(queue_entry, now=now)

    return {"appointment": _appointment_dict(appt), "doctor": chosen, "queue": queue_out}


@router.post("/simulate")
async def simulate_appointment() -> dict:
    raise not_implemented("appointment simulation lands in CP3 (N3.3)")


@router.patch("/{appointment_id}")
async def update_appointment(
    appointment_id: UUID, body: AppointmentPatch, user: CurrentUser = Depends(get_current_user)
) -> dict:
    async with SessionLocal() as session:
        appt = await session.get(Appointment, appointment_id)
        if appt is None:
            raise ApiError("NOT_FOUND", "appointment not found", status_code=404)
        if body.status is not None:
            appt.status = body.status
        if body.slot_start is not None and body.slot_end is not None:
            appt.slot_start = body.slot_start
            appt.slot_end = body.slot_end
        await session.commit()
        return _appointment_dict(appt)
