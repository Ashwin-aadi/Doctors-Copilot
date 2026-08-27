"""Thin, batched query layer over Ashwin's scheduling tables.

No ORM objects leak past this module -- every function returns dataclasses.
All methods are single-round-trip regardless of how many ids are passed in
(no N+1 queries).

TEMP-ADAPTER: `Doctor.languages`, `Doctor.registration_council`,
`Clinic.facility_type` and `Clinic.schemes` do not exist yet on
`app/db/models/scheduling.py` (not an owned path for this checkpoint).
Until Ashwin ships those columns, this module fills them from
`_DOCTOR_LOCALE_OVERRIDES` / `_CLINIC_LOCALE_OVERRIDES` (keyed by the fixed
demo UUIDs from scripts/seed_users.py and tests/services/conftest.py) with a
generic fallback for any row not in that table. See docs/DECISIONS.md for the
DRIFT note. Remove the overrides and read straight off the model once those
columns land.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select

from app.db.models.scheduling import Appointment, Availability, Clinic, Doctor, QueueEntry
from app.db.session import SessionLocal

# Appointment statuses that hand the slot back to the free pool. Defined here
# rather than in `lifecycle` (which imports this module) to keep the
# dependency one-way; `lifecycle` re-exports it under the same name.
RELEASING_STATUSES = ("cancelled", "no_show", "referred")

# IST is a half-hour offset -- any code that assumes whole hours is a bug.
_IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True, slots=True)
class DoctorRow:
    doctor_id: UUID
    name: str
    specialties: list[str]
    fee_inr: float
    rating: float
    clinic_id: UUID
    languages: list[str]
    registration_council: str | None
    nmc_reg_no: str | None


@dataclass(frozen=True, slots=True)
class ClinicRow:
    clinic_id: UUID
    name: str
    lat: float
    lng: float
    facility_type: str
    is_emergency_capable: bool
    schemes: list[str]
    state: str | None
    pin_code: str | None


@dataclass(frozen=True, slots=True)
class AvailRow:
    availability_id: UUID
    doctor_id: UUID
    clinic_id: UUID
    weekday: int
    start_time: time
    end_time: time
    slot_minutes: int
    valid_from: date
    valid_to: date


# TEMP-ADAPTER: remove when Doctor.languages / Doctor.registration_council ship.
_DOCTOR_LOCALE_OVERRIDES: dict[UUID, tuple[list[str], str | None]] = {
    UUID("00000000-0000-0000-0000-000000000201"): (["ta", "en"], "Tamil Nadu Medical Council"),
    UUID("00000000-0000-0000-0000-000000000202"): (["hi", "en"], "Medical Council of India"),
    UUID("00000000-0000-0000-0000-000000000203"): (["te", "ta"], "Tamil Nadu Medical Council"),
    UUID("00000000-0000-0000-0000-000000000204"): (["ta", "en"], "Tamil Nadu Medical Council"),
    UUID("00000000-0000-0000-0000-000000000205"): (["hi", "en"], "Medical Council of India"),
    UUID("00000000-0000-0000-0000-000000000206"): (["ta", "hi", "en"], "Tamil Nadu Medical Council"),
}
_DOCTOR_LOCALE_DEFAULT: tuple[list[str], str | None] = (["en"], None)

# TEMP-ADAPTER: remove when Clinic.facility_type / Clinic.schemes ship.
_CLINIC_LOCALE_OVERRIDES: dict[UUID, tuple[str, list[str]]] = {
    UUID("00000000-0000-0000-0000-000000000001"): ("phc", ["state_scheme"]),
    UUID("00000000-0000-0000-0000-000000000002"): ("chc", ["state_scheme"]),
    UUID("00000000-0000-0000-0000-000000000003"): ("dh", ["pmjay", "cghs", "state_scheme"]),
}


def _clinic_locale_default(is_emergency_capable: bool) -> tuple[str, list[str]]:
    return ("dh", ["pmjay"]) if is_emergency_capable else ("phc", [])


def _doctor_row(d: Doctor) -> DoctorRow:
    languages, registration_council = _DOCTOR_LOCALE_OVERRIDES.get(d.id, _DOCTOR_LOCALE_DEFAULT)
    return DoctorRow(
        doctor_id=d.id,
        name=d.name,
        specialties=list(d.specialties or []),
        fee_inr=d.fee,
        rating=d.rating,
        clinic_id=d.clinic_id,
        languages=languages,
        registration_council=registration_council,
        nmc_reg_no=d.nmc_reg_no,
    )


def _clinic_row(c: Clinic) -> ClinicRow:
    facility_type, schemes = _CLINIC_LOCALE_OVERRIDES.get(
        c.id, _clinic_locale_default(c.is_emergency_capable)
    )
    return ClinicRow(
        clinic_id=c.id,
        name=c.name,
        lat=c.lat,
        lng=c.lng,
        facility_type=facility_type,
        is_emergency_capable=c.is_emergency_capable,
        schemes=schemes,
        state=c.state,
        pin_code=c.pin_code,
    )


async def doctors_by_specialty(specialty: str, max_fee: float | None) -> list[DoctorRow]:
    stmt = select(Doctor).where(Doctor.specialties.contains([specialty]))
    if max_fee is not None:
        stmt = stmt.where(Doctor.fee <= max_fee)
    stmt = stmt.order_by(Doctor.id)
    async with SessionLocal() as session:
        result = await session.execute(stmt)
        return [_doctor_row(d) for d in result.scalars().all()]


async def availability_for(
    doctor_ids: list[UUID], date_from: date, date_to: date
) -> dict[UUID, list[AvailRow]]:
    out: dict[UUID, list[AvailRow]] = {doctor_id: [] for doctor_id in doctor_ids}
    if not doctor_ids:
        return out
    stmt = (
        select(Availability)
        .where(Availability.doctor_id.in_(doctor_ids))
        .where(Availability.valid_from <= date_to)
        .where(Availability.valid_to >= date_from)
        .order_by(Availability.doctor_id, Availability.weekday, Availability.start_time)
    )
    async with SessionLocal() as session:
        result = await session.execute(stmt)
        for a in result.scalars().all():
            out[a.doctor_id].append(
                AvailRow(
                    availability_id=a.id,
                    doctor_id=a.doctor_id,
                    clinic_id=a.clinic_id,
                    weekday=a.weekday,
                    start_time=a.start_time,
                    end_time=a.end_time,
                    slot_minutes=a.slot_minutes,
                    valid_from=a.valid_from,
                    valid_to=a.valid_to,
                )
            )
    return out


async def booked_slots(
    doctor_ids: list[UUID], date_from: date, date_to: date
) -> dict[UUID, list[tuple[datetime, datetime]]]:
    out: dict[UUID, list[tuple[datetime, datetime]]] = {doctor_id: [] for doctor_id in doctor_ids}
    if not doctor_ids:
        return out
    range_start = datetime.combine(date_from, time.min, tzinfo=None)
    range_end = datetime.combine(date_to, time.max, tzinfo=None)
    stmt = (
        select(Appointment)
        .where(Appointment.doctor_id.in_(doctor_ids))
        # N3.2: `referred` joins cancelled/no_show as a slot-releasing status.
        # A patient sent up the referral ladder is not coming to this OPD
        # session, so holding their slot would leave it dark for the rest of
        # the day.
        .where(Appointment.status.notin_(list(RELEASING_STATUSES)))
        .where(Appointment.slot_start >= range_start)
        .where(Appointment.slot_start <= range_end)
        .order_by(Appointment.doctor_id, Appointment.slot_start)
    )
    async with SessionLocal() as session:
        result = await session.execute(stmt)
        for ap in result.scalars().all():
            out[ap.doctor_id].append((ap.slot_start, ap.slot_end))
    return out


async def queue_load(clinic_ids: list[UUID], *, now: datetime) -> dict[UUID, int]:
    out: dict[UUID, int] = {clinic_id: 0 for clinic_id in clinic_ids}
    if not clinic_ids:
        return out
    stmt = (
        select(QueueEntry.clinic_id, func.count(QueueEntry.id))
        .where(QueueEntry.clinic_id.in_(clinic_ids))
        .where(QueueEntry.status == "waiting")
        .group_by(QueueEntry.clinic_id)
    )
    async with SessionLocal() as session:
        result = await session.execute(stmt)
        for clinic_id, count in result.all():
            out[clinic_id] = count
    return out


async def doctor_session_load(
    doctor_ids: list[UUID], *, now: datetime
) -> dict[UUID, int]:
    """How many patients each doctor is already carrying for the current OPD
    service day: booked appointments plus still-open queue entries.

    N3.3's fairness constraint compares this against
    `max_patients_per_doctor_per_session`. Counted over the IST service day
    (not a rolling 24 h) because that is the unit an OPD session is actually
    scheduled in. Two queries total regardless of how many doctors are
    passed -- the optimizer's batching budget has no room for an N+1 here.
    """
    out: dict[UUID, int] = {doctor_id: 0 for doctor_id in doctor_ids}
    if not doctor_ids:
        return out

    service_date = now.astimezone(_IST).date()
    day_start = datetime.combine(service_date, time.min, tzinfo=_IST)
    day_end = day_start + timedelta(days=1)

    async with SessionLocal() as session:
        appt_rows = (
            await session.execute(
                select(Appointment.doctor_id, func.count(Appointment.id))
                .where(Appointment.doctor_id.in_(doctor_ids))
                .where(Appointment.status.notin_(list(RELEASING_STATUSES)))
                .where(Appointment.slot_start >= day_start)
                .where(Appointment.slot_start < day_end)
                .group_by(Appointment.doctor_id)
            )
        ).all()
        # walk-ins have no appointment row, so they are counted separately off
        # the queue; a booked patient who has checked in appears in both and
        # is deduplicated by only counting appointment-less queue entries.
        queue_rows = (
            await session.execute(
                select(QueueEntry.doctor_id, func.count(QueueEntry.id))
                .where(QueueEntry.doctor_id.in_(doctor_ids))
                .where(QueueEntry.appointment_id.is_(None))
                .where(QueueEntry.status.in_(["waiting", "in_consult"]))
                .where(QueueEntry.enqueued_at >= day_start)
                .where(QueueEntry.enqueued_at < day_end)
                .group_by(QueueEntry.doctor_id)
            )
        ).all()

    for doctor_id, count in appt_rows:
        out[doctor_id] = out.get(doctor_id, 0) + count
    for doctor_id, count in queue_rows:
        out[doctor_id] = out.get(doctor_id, 0) + count
    return out


async def clinics_by_ids(ids: list[UUID]) -> dict[UUID, ClinicRow]:
    if not ids:
        return {}
    stmt = select(Clinic).where(Clinic.id.in_(ids)).order_by(Clinic.id)
    async with SessionLocal() as session:
        result = await session.execute(stmt)
        return {c.id: _clinic_row(c) for c in result.scalars().all()}


async def all_clinics() -> list[ClinicRow]:
    """Every clinic, batched in one round trip. N2.3's referral-ladder check
    needs to search by facility capability independent of which doctors
    happen to be rostered today -- `rank_doctors` is doctor-availability
    driven and would wrongly suppress a valid transfer suggestion for a
    capable-but-understaffed facility, so escalation.py searches clinics
    directly instead of going through the optimizer.
    """
    stmt = select(Clinic).order_by(Clinic.id)
    async with SessionLocal() as session:
        result = await session.execute(stmt)
        return [_clinic_row(c) for c in result.scalars().all()]
