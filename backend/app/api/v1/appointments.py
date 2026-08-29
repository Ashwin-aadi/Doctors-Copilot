from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import CurrentUser, get_current_user, require_captcha
from app.core.errors import ApiError
from app.db.models.clinical import TriageSession, Visit
from app.db.models.scheduling import Appointment, QueueEntry
from app.db.session import SessionLocal
from app.services.queueing.pq import enqueue
from app.services.queueing.schemas import QueueEntryOut
from app.services.scheduling import lifecycle
from app.services.scheduling.optimizer import rank_doctors
from app.services.scheduling.repo import booked_slots as repo_booked_slots
from app.services.scheduling.schemas import DoctorRankedOut
from app.services.scheduling.slots import free_slots

log = structlog.get_logger(__name__)

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
    # N3.2 referral-out payload; only read when `status == "referred"`.
    target_facility_type: str | None = None
    target_clinic_id: UUID | None = None
    reason: str | None = None


class SimulateRequest(BaseModel):
    """`POST /appointments/simulate` -- the same inputs as a booking, minus
    the patient. Returns the top alternatives so the UI can offer a choice
    instead of silently forcing rank #1 on the patient.
    """

    specialty: str
    lat: float | None = None
    lng: float | None = None
    preferred_from: datetime | None = None
    max_fee: float | None = None
    language: str | None = None
    scheme: str | None = None
    limit: int = 5


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


async def _ensure_triage_finalized(triage_session_id: UUID) -> None:
    """A patient can book the moment they are happy with the interview, without
    running it to the eight-question limit -- in which case `finalize` has never
    run and the session carries a transcript but no result. The doctor would
    then open the chart to a conversation with no severity, no rationale and no
    suggested labs. Finalizing here is what makes the booking produce a
    complete record.
    """
    from app.rag.triage_rag import finalize

    async with SessionLocal() as session:
        record = await session.get(TriageSession, triage_session_id)
        if record is None or record.result:
            return
        if not (record.transcript or []):
            return
        try:
            await finalize(session, triage_session_id)
        except Exception as exc:  # noqa: BLE001
            # A failed finalize must not cost the patient their appointment --
            # the booking is already committed by this point.
            log.warning(
                "triage_finalize_on_booking_failed",
                session_id=str(triage_session_id),
                error=str(exc),
            )


async def _open_visit(
    *, patient_id: UUID, doctor_id: UUID, triage_session_id: UUID | None, now: datetime
) -> UUID:
    """Re-use the patient's visit only while it is still at TRIAGED -- that is
    a booking that has not started any clinical work yet, so pointing it at
    this doctor and this triage session is right. A visit that has moved on
    (labs ordered, results in, brief built) belongs to an earlier episode of
    care; a new booking opens a new record rather than reopening that one and
    showing the doctor a chart that does not match what the patient just said.
    """
    if triage_session_id:
        await _ensure_triage_finalized(triage_session_id)

    async with SessionLocal() as session:
        existing = (
            await session.execute(
                select(Visit)
                .where(Visit.patient_id == patient_id, Visit.state == "TRIAGED")
                .order_by(Visit.created_at.desc())
            )
        ).scalars().first()

        # Never let a booking inherit an earlier interview. If this booking
        # carries no triage session and the open visit already has one, that
        # visit belongs to a different conversation -- reusing it would show
        # the doctor a transcript and rationale the patient never gave for
        # this appointment. Open a fresh record instead.
        if existing is not None and not triage_session_id and existing.triage_session_id:
            existing = None

        if existing is not None:
            existing.doctor_id = doctor_id
            if triage_session_id:
                existing.triage_session_id = triage_session_id
            existing.updated_at = now
            await session.commit()
            return existing.id

        visit = Visit(
            id=uuid4(),
            patient_id=patient_id,
            doctor_id=doctor_id,
            state="TRIAGED",
            triage_session_id=triage_session_id,
            created_at=now,
            updated_at=now,
        )
        session.add(visit)
        await session.commit()
        return visit.id


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

    # Open the clinical record for this booking. Without it the doctor gets a
    # queue row with nothing behind it -- no triage, no transcript, nowhere to
    # order labs. The visit carries the triage session so the chart opens on
    # what the patient actually said.
    visit_id = await _open_visit(
        patient_id=body.patient_id,
        doctor_id=chosen.doctor_id,
        triage_session_id=body.triage_session_id,
        now=now,
    )

    return {
        "appointment": _appointment_dict(appt),
        "doctor": chosen,
        "queue": queue_out,
        "visit_id": visit_id,
    }


@router.post("/simulate", response_model=list[DoctorRankedOut])
async def simulate_appointment(
    body: SimulateRequest, user: CurrentUser = Depends(get_current_user)
) -> list[DoctorRankedOut]:
    """N3.3: dry-run the optimizer and hand back the top `limit` doctors with
    full bilingual `reasons`. Books nothing and mutates nothing, so it is
    safe to call on every keystroke of a specialty picker.
    """
    now = datetime.now(UTC)
    date_from = body.preferred_from or now
    if date_from.tzinfo is None:
        date_from = date_from.replace(tzinfo=UTC)

    ranked = await rank_doctors(
        specialty=body.specialty,
        lat=body.lat,
        lng=body.lng,
        date_from=date_from,
        max_fee=body.max_fee,
        language=body.language,
        scheme=body.scheme,
        now=now,
    )
    return ranked[: max(1, body.limit)]


@router.get("/{appointment_id}")
async def get_appointment(
    appointment_id: UUID, user: CurrentUser = Depends(get_current_user)
) -> dict:
    async with SessionLocal() as session:
        appt = await session.get(Appointment, appointment_id)
        if appt is None:
            raise ApiError("NOT_FOUND", "appointment not found", status_code=404)
        return _appointment_dict(appt)


@router.patch("/{appointment_id}")
async def update_appointment(
    appointment_id: UUID, body: AppointmentPatch, user: CurrentUser = Depends(get_current_user)
) -> dict:
    """N3.2 lifecycle transitions. A status change routes into
    `app.services.scheduling.lifecycle`, which frees the slot, re-keys the
    queue, notifies the patient and republishes the OPD board -- none of
    which the CP1 straight-column-write did. A slot move with no status
    change is a reschedule.
    """
    now = datetime.now(UTC)

    if body.status == "cancelled":
        return await lifecycle.cancel(appointment_id, now=now, reason=body.reason)
    if body.status == "no_show":
        return await lifecycle.mark_no_show(appointment_id, now=now)
    if body.status == "referred":
        if not body.target_facility_type:
            raise ApiError(
                "VALIDATION_FAILED",
                "target_facility_type is required to refer a patient out",
                status_code=422,
            )
        return await lifecycle.refer_out(
            appointment_id,
            target_facility_type=body.target_facility_type,
            target_clinic_id=body.target_clinic_id,
            reason=body.reason or "referred by treating doctor",
            now=now,
        )
    if body.slot_start is not None:
        return await lifecycle.reschedule(appointment_id, body.slot_start, now=now)
    if body.status is not None:
        raise ApiError(
            "VALIDATION_FAILED",
            f"unsupported appointment status '{body.status}'",
            status_code=422,
            details={"allowed": ["cancelled", "no_show", "referred"]},
        )

    async with SessionLocal() as session:
        appt = await session.get(Appointment, appointment_id)
        if appt is None:
            raise ApiError("NOT_FOUND", "appointment not found", status_code=404)
        return _appointment_dict(appt)
