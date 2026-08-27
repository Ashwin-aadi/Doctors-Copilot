"""Doctor & clinic profile management, weekly availability, and the leave/
blackout calendar (checkpoint P3.4). Admin-only CRUD for `Doctor`/`Clinic`;
a doctor may `PATCH` their own non-financial fields (name, specialties,
qualifications) but never their own registration number, registration
council/year, fee, or rating.

`doctors.registration_council`/`registration_year` and `clinics.
facility_type` (added in `alembic/versions/d4a1f6e29c88_...py`) and the new
`availability_blackouts` table have no ORM columns/model on
`app/db/models/` (off limits -- see docs/DECISIONS.md), so all three are
read/written through local SQLAlchemy Core `Table` objects, the same
pattern `app/services/consent.py`/`app/services/notify.py` already use.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, time
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    select,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user, require_role
from app.core.errors import ApiError
from app.db.models.scheduling import Availability, Clinic, Doctor
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/doctors-profile", tags=["doctors-profile"])

_require_admin = require_role("admin")

_NMC_REG_RE = re.compile(r"^[A-Z0-9][A-Z0-9/-]{3,31}$")
_PIN_RE = re.compile(r"^\d{6}$")
_FACILITY_TYPES = ("PHC", "CHC", "district_hospital", "private_clinic", "private_hospital")
_SLOT_MINUTES = (10, 15, 20, 30)
# India's rough bounding box (mainland + islands).
_INDIA_LAT = (6.5, 37.6)
_INDIA_LNG = (68.0, 97.5)

_metadata = MetaData()
_doctors_extra = Table(
    "doctors",
    _metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("registration_council", String(64)),
    Column("registration_year", Integer),
)
_clinics_extra = Table(
    "clinics",
    _metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("facility_type", String(32)),
)
_blackouts_table = Table(
    "availability_blackouts",
    _metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("clinic_id", PGUUID(as_uuid=True), ForeignKey("clinics.id"), nullable=True),
    Column("doctor_id", PGUUID(as_uuid=True), ForeignKey("doctors.id"), nullable=True),
    Column("blackout_date", Date),
    Column("reason", String(255)),
    Column("state", String(64)),
    Column("created_at", DateTime(timezone=True)),
)


# ---------------------------------------------------------------- schemas --


class DoctorIn(BaseModel):
    user_id: UUID
    name: str
    specialties: list[str] = []
    qualifications: str | None = None
    nmc_reg_no: str
    registration_council: str | None = "NMC"
    registration_year: int | None = None
    fee: float = 0.0
    clinic_id: UUID

    @field_validator("nmc_reg_no")
    @classmethod
    def _validate_reg_no(cls, v: str) -> str:
        if not _NMC_REG_RE.match(v):
            raise ValueError("nmc_reg_no must be 4-32 alphanumeric characters (with optional -/)")
        return v


class DoctorPatch(BaseModel):
    name: str | None = None
    specialties: list[str] | None = None
    qualifications: str | None = None
    # Admin-only fields; rejected outright if a doctor tries to set them on
    # their own record.
    nmc_reg_no: str | None = None
    registration_council: str | None = None
    registration_year: int | None = None
    fee: float | None = None
    rating: float | None = None
    clinic_id: UUID | None = None


_SELF_EDITABLE_FIELDS = {"name", "specialties", "qualifications"}


class ClinicIn(BaseModel):
    name: str
    lat: float
    lng: float
    is_emergency_capable: bool = False
    facility_type: Literal[
        "PHC", "CHC", "district_hospital", "private_clinic", "private_hospital"
    ]
    state: str
    pin_code: str

    @field_validator("pin_code")
    @classmethod
    def _validate_pin(cls, v: str) -> str:
        if not _PIN_RE.match(v):
            raise ValueError("pin_code must be exactly 6 digits")
        return v


class ClinicPatch(BaseModel):
    name: str | None = None
    lat: float | None = None
    lng: float | None = None
    is_emergency_capable: bool | None = None
    facility_type: str | None = None
    state: str | None = None
    pin_code: str | None = None


class AvailabilityIn(BaseModel):
    doctor_id: UUID
    clinic_id: UUID
    weekday: int
    start_time: str
    end_time: str
    slot_minutes: int = 15
    valid_from: date | None = None
    valid_to: date | None = None


class BlackoutIn(BaseModel):
    clinic_id: UUID | None = None
    doctor_id: UUID | None = None
    blackout_date: date
    reason: str | None = None
    state: str | None = None


# ------------------------------------------------------------- validators --


def _validate_latlng(lat: float, lng: float) -> None:
    if not (_INDIA_LAT[0] <= lat <= _INDIA_LAT[1] and _INDIA_LNG[0] <= lng <= _INDIA_LNG[1]):
        raise ApiError(
            "VALIDATION_FAILED", "clinic coordinates must fall inside India", status_code=422
        )


def _parse_time(raw: str) -> time:
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError as exc:
        raise ApiError(
            "VALIDATION_FAILED", "start_time/end_time must be HH:MM", status_code=422
        ) from exc


async def _validate_availability(
    db: AsyncSession, body: AvailabilityIn, *, exclude_id: UUID | None = None
) -> tuple[time, time, date, date]:
    if not (0 <= body.weekday <= 6):
        raise ApiError("VALIDATION_FAILED", "weekday must be 0-6", status_code=422)

    start_t = _parse_time(body.start_time)
    end_t = _parse_time(body.end_time)
    if not start_t < end_t:
        raise ApiError(
            "VALIDATION_FAILED", "start_time must be before end_time", status_code=422
        )

    if body.slot_minutes not in _SLOT_MINUTES:
        raise ApiError(
            "VALIDATION_FAILED", f"slot_minutes must be one of {_SLOT_MINUTES}", status_code=422
        )

    valid_from = body.valid_from or date.today()
    valid_to = body.valid_to or date(valid_from.year + 1, valid_from.month, valid_from.day)
    if valid_from > valid_to:
        raise ApiError("VALIDATION_FAILED", "valid_from must be <= valid_to", status_code=422)

    existing = await db.execute(
        select(Availability).where(
            Availability.doctor_id == body.doctor_id, Availability.weekday == body.weekday
        )
    )
    for row in existing.scalars().all():
        if exclude_id is not None and row.id == exclude_id:
            continue
        if start_t < row.end_time and end_t > row.start_time:
            raise ApiError(
                "VALIDATION_FAILED",
                "overlaps an existing availability window for this doctor/weekday",
                status_code=422,
            )

    return start_t, end_t, valid_from, valid_to


# -------------------------------------------------------------- doctors --


def _serialize_doctor(d: Doctor, extra: dict) -> dict:
    return {
        "id": d.id,
        "user_id": d.user_id,
        "name": d.name,
        "specialties": d.specialties,
        "qualifications": d.qualifications,
        "nmc_reg_no": d.nmc_reg_no,
        "registration_council": extra.get("registration_council"),
        "registration_year": extra.get("registration_year"),
        "fee": d.fee,
        "rating": d.rating,
        "clinic_id": d.clinic_id,
    }


async def _doctor_extra(db: AsyncSession, doctor_id: UUID) -> dict:
    result = await db.execute(_doctors_extra.select().where(_doctors_extra.c.id == doctor_id))
    row = result.first()
    return {} if row is None else {"registration_council": row.registration_council, "registration_year": row.registration_year}


@router.get("")
async def list_doctor_profiles(
    _user: CurrentUser = Depends(_require_admin), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    result = await db.execute(select(Doctor))
    doctors = result.scalars().all()
    out = []
    for d in doctors:
        out.append(_serialize_doctor(d, await _doctor_extra(db, d.id)))
    return out


@router.post("")
async def create_doctor_profile(
    body: DoctorIn,
    _user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, body.user_id)
    if user is None or user.role != "doctor":
        raise ApiError(
            "VALIDATION_FAILED", "user_id must reference an existing doctor account", status_code=422
        )
    clinic = await db.get(Clinic, body.clinic_id)
    if clinic is None:
        raise ApiError("VALIDATION_FAILED", "clinic_id does not exist", status_code=422)

    dup = await db.execute(select(Doctor.id).where(Doctor.nmc_reg_no == body.nmc_reg_no))
    if dup.scalar_one_or_none() is not None:
        raise ApiError(
            "CONFLICT", "a doctor with this registration number already exists", status_code=409
        )

    doctor = Doctor(
        user_id=body.user_id,
        name=body.name,
        specialties=body.specialties,
        qualifications=body.qualifications,
        nmc_reg_no=body.nmc_reg_no,
        fee=body.fee,
        clinic_id=body.clinic_id,
    )
    db.add(doctor)
    await db.flush()
    await db.execute(
        _doctors_extra.update()
        .where(_doctors_extra.c.id == doctor.id)
        .values(
            registration_council=body.registration_council,
            registration_year=body.registration_year,
        )
    )
    await db.commit()
    await db.refresh(doctor)
    return _serialize_doctor(doctor, await _doctor_extra(db, doctor.id))


@router.patch("/{doctor_id}")
async def update_doctor_profile(
    doctor_id: UUID,
    body: DoctorPatch,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    doctor = await db.get(Doctor, doctor_id)
    if doctor is None:
        raise ApiError("NOT_FOUND", "doctor profile not found", status_code=404)

    is_admin = user.role == "admin"
    is_self = user.role == "doctor" and doctor.user_id == user.id
    if not (is_admin or is_self):
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)

    updates = body.model_dump(exclude_unset=True)
    if is_self and not is_admin:
        disallowed = set(updates) - _SELF_EDITABLE_FIELDS
        if disallowed:
            raise ApiError(
                "AUTH_FORBIDDEN",
                f"doctors may not edit: {', '.join(sorted(disallowed))}",
                status_code=403,
            )

    if "nmc_reg_no" in updates:
        if not _NMC_REG_RE.match(updates["nmc_reg_no"]):
            raise ApiError("VALIDATION_FAILED", "invalid nmc_reg_no format", status_code=422)
        dup = await db.execute(
            select(Doctor.id).where(Doctor.nmc_reg_no == updates["nmc_reg_no"], Doctor.id != doctor_id)
        )
        if dup.scalar_one_or_none() is not None:
            raise ApiError("CONFLICT", "registration number already in use", status_code=409)

    extra_updates = {}
    for key in ("registration_council", "registration_year"):
        if key in updates:
            extra_updates[key] = updates.pop(key)

    for key, value in updates.items():
        setattr(doctor, key, value)

    if extra_updates:
        await db.execute(
            _doctors_extra.update().where(_doctors_extra.c.id == doctor_id).values(**extra_updates)
        )
    await db.commit()
    await db.refresh(doctor)
    return _serialize_doctor(doctor, await _doctor_extra(db, doctor.id))


# --------------------------------------------------------------- clinics --


def _serialize_clinic(c: Clinic, facility_type: str | None) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "lat": c.lat,
        "lng": c.lng,
        "is_emergency_capable": c.is_emergency_capable,
        "facility_type": facility_type,
        "state": c.state,
        "pin_code": c.pin_code,
    }


async def _clinic_facility_type(db: AsyncSession, clinic_id: UUID) -> str | None:
    result = await db.execute(_clinics_extra.select().where(_clinics_extra.c.id == clinic_id))
    row = result.first()
    return row.facility_type if row is not None else None


@router.get("/clinics")
async def list_clinics(
    _user: CurrentUser = Depends(_require_admin), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    result = await db.execute(select(Clinic))
    out = []
    for c in result.scalars().all():
        out.append(_serialize_clinic(c, await _clinic_facility_type(db, c.id)))
    return out


@router.post("/clinics")
async def create_clinic(
    body: ClinicIn,
    _user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _validate_latlng(body.lat, body.lng)
    clinic = Clinic(
        name=body.name,
        lat=body.lat,
        lng=body.lng,
        is_emergency_capable=body.is_emergency_capable,
        state=body.state,
        pin_code=body.pin_code,
    )
    db.add(clinic)
    await db.flush()
    await db.execute(
        _clinics_extra.update()
        .where(_clinics_extra.c.id == clinic.id)
        .values(facility_type=body.facility_type)
    )
    await db.commit()
    await db.refresh(clinic)
    return _serialize_clinic(clinic, body.facility_type)


@router.patch("/clinics/{clinic_id}")
async def update_clinic(
    clinic_id: UUID,
    body: ClinicPatch,
    _user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    clinic = await db.get(Clinic, clinic_id)
    if clinic is None:
        raise ApiError("NOT_FOUND", "clinic not found", status_code=404)

    updates = body.model_dump(exclude_unset=True)
    if "pin_code" in updates and not _PIN_RE.match(updates["pin_code"]):
        raise ApiError("VALIDATION_FAILED", "pin_code must be exactly 6 digits", status_code=422)
    if "facility_type" in updates and updates["facility_type"] not in _FACILITY_TYPES:
        raise ApiError("VALIDATION_FAILED", "invalid facility_type", status_code=422)

    new_lat = updates.get("lat", clinic.lat)
    new_lng = updates.get("lng", clinic.lng)
    if "lat" in updates or "lng" in updates:
        _validate_latlng(new_lat, new_lng)

    facility_type = updates.pop("facility_type", None)
    for key, value in updates.items():
        setattr(clinic, key, value)
    await db.commit()
    await db.refresh(clinic)

    if facility_type is not None:
        await db.execute(
            _clinics_extra.update()
            .where(_clinics_extra.c.id == clinic_id)
            .values(facility_type=facility_type)
        )
        await db.commit()

    return _serialize_clinic(clinic, await _clinic_facility_type(db, clinic_id))


# ---------------------------------------------------------- availability --


def _serialize_availability(a: Availability) -> dict:
    return {
        "id": a.id,
        "doctor_id": a.doctor_id,
        "clinic_id": a.clinic_id,
        "weekday": a.weekday,
        "start_time": a.start_time.strftime("%H:%M"),
        "end_time": a.end_time.strftime("%H:%M"),
        "slot_minutes": a.slot_minutes,
        "valid_from": a.valid_from,
        "valid_to": a.valid_to,
    }


@router.post("/availability")
async def create_availability(
    body: AvailabilityIn,
    _user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    start_t, end_t, valid_from, valid_to = await _validate_availability(db, body)
    availability = Availability(
        doctor_id=body.doctor_id,
        clinic_id=body.clinic_id,
        weekday=body.weekday,
        start_time=start_t,
        end_time=end_t,
        slot_minutes=body.slot_minutes,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    db.add(availability)
    await db.commit()
    await db.refresh(availability)
    return _serialize_availability(availability)


@router.get("/availability")
async def list_availability(
    doctor_id: UUID | None = None,
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = select(Availability)
    if doctor_id is not None:
        stmt = stmt.where(Availability.doctor_id == doctor_id)
    result = await db.execute(stmt)
    return [_serialize_availability(a) for a in result.scalars().all()]


@router.delete("/availability/{availability_id}")
async def delete_availability(
    availability_id: UUID,
    _user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    availability = await db.get(Availability, availability_id)
    if availability is None:
        raise ApiError("NOT_FOUND", "availability window not found", status_code=404)
    await db.delete(availability)
    await db.commit()
    return {"status": "ok"}


# -------------------------------------------------------------- blackouts --


def _serialize_blackout(row) -> dict:
    return {
        "id": row.id,
        "clinic_id": row.clinic_id,
        "doctor_id": row.doctor_id,
        "blackout_date": row.blackout_date,
        "reason": row.reason,
        "state": row.state,
    }


@router.post("/blackouts")
async def create_blackout(
    body: BlackoutIn,
    _user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    blackout_id = uuid.uuid4()
    await db.execute(
        _blackouts_table.insert().values(
            id=blackout_id,
            clinic_id=body.clinic_id,
            doctor_id=body.doctor_id,
            blackout_date=body.blackout_date,
            reason=body.reason,
            state=body.state,
            created_at=datetime.now(UTC),
        )
    )
    await db.commit()
    result = await db.execute(_blackouts_table.select().where(_blackouts_table.c.id == blackout_id))
    return _serialize_blackout(result.first())


@router.get("/blackouts")
async def list_blackouts(
    doctor_id: UUID | None = None,
    clinic_id: UUID | None = None,
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = _blackouts_table.select()
    if doctor_id is not None:
        stmt = stmt.where(
            (_blackouts_table.c.doctor_id == doctor_id) | (_blackouts_table.c.doctor_id.is_(None))
        )
    if clinic_id is not None:
        stmt = stmt.where(
            (_blackouts_table.c.clinic_id == clinic_id) | (_blackouts_table.c.clinic_id.is_(None))
        )
    result = await db.execute(stmt)
    return [_serialize_blackout(row) for row in result.fetchall()]


@router.delete("/blackouts/{blackout_id}")
async def delete_blackout(
    blackout_id: UUID,
    _user: CurrentUser = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await db.execute(_blackouts_table.delete().where(_blackouts_table.c.id == blackout_id))
    await db.commit()
    return {"status": "ok"}
