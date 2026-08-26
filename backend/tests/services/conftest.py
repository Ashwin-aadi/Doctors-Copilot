"""Deterministic Chennai clinic-day fixture shared by every services test.

3 clinics (1 PHC, 1 CHC, 1 district hospital -- the DH `is_emergency_capable`
and PM-JAY empanelled per the TEMP-ADAPTER overrides in
app/services/scheduling/repo.py), 6 doctors with mixed languages, IST OPD
hours 09:00-13:00 + 17:00-20:00, fixed `now = 2026-01-12T09:00:00Z`
(14:30 IST, a Monday -- `Availability.weekday` uses Python's `date.weekday()`
convention, Monday=0).

Function-scoped and autouse: each test gets a fresh event loop (see the root
conftest's `_dispose_engine_after_test` docstring), so fixture rows are
upserted fresh per test via get-or-create rather than relying on a shared
session/module-scoped seed.
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID

import pytest_asyncio

from app.db.models.scheduling import Availability, Clinic, Doctor
from app.db.models.user import User
from app.db.session import SessionLocal

NOW = dt.datetime(2026, 1, 12, 9, 0, tzinfo=dt.timezone.utc)  # 14:30 IST, Monday
OPD_WEEKDAY = 0  # Monday, per date.weekday()

CLINIC_PHC = UUID("00000000-0000-0000-0000-000000000001")
CLINIC_CHC = UUID("00000000-0000-0000-0000-000000000002")
CLINIC_DH = UUID("00000000-0000-0000-0000-000000000003")

_CLINICS = [
    {
        "id": CLINIC_PHC,
        "name": "Egmore Primary Health Centre",
        "lat": 13.0732,
        "lng": 80.2609,
        "is_emergency_capable": False,
        "state": "Tamil Nadu",
        "pin_code": "600008",
    },
    {
        "id": CLINIC_CHC,
        "name": "Adyar Community Health Centre",
        "lat": 13.0012,
        "lng": 80.2565,
        "is_emergency_capable": False,
        "state": "Tamil Nadu",
        "pin_code": "600020",
    },
    {
        "id": CLINIC_DH,
        "name": "Chennai District Hospital",
        "lat": 13.0827,
        "lng": 80.2707,
        "is_emergency_capable": True,
        "state": "Tamil Nadu",
        "pin_code": "600001",
    },
]

_DOCTOR_USER_BASE = 400
_DOCTORS = [
    {"i": 1, "id": 201, "clinic": CLINIC_PHC, "name": "Dr. Lakshmi Sundaram",
     "specialties": ["general_medicine"], "fee": 0.0, "rating": 4.3},
    {"i": 2, "id": 202, "clinic": CLINIC_PHC, "name": "Dr. Karthik Raman",
     "specialties": ["general_medicine"], "fee": 0.0, "rating": 4.1},
    {"i": 3, "id": 203, "clinic": CLINIC_CHC, "name": "Dr. Divya Chandrasekaran",
     "specialties": ["obstetrics_gynaecology"], "fee": 100.0, "rating": 4.5},
    {"i": 4, "id": 204, "clinic": CLINIC_CHC, "name": "Dr. Arun Prakash",
     "specialties": ["paediatrics"], "fee": 100.0, "rating": 4.4},
    {"i": 5, "id": 205, "clinic": CLINIC_DH, "name": "Dr. Meenakshi Iyer",
     "specialties": ["cardiology"], "fee": 300.0, "rating": 4.7},
    {"i": 6, "id": 206, "clinic": CLINIC_DH, "name": "Dr. Suriya Narayanan",
     "specialties": ["general_surgery"], "fee": 300.0, "rating": 4.2},
]

OPD_SESSIONS = [
    (dt.time(9, 0), dt.time(13, 0)),
    (dt.time(17, 0), dt.time(20, 0)),
]


def doctor_id(i: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{200 + i:012d}")


def doctor_user_id(i: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{_DOCTOR_USER_BASE + i:012d}")


def availability_id(doctor_i: int, session_i: int) -> UUID:
    return UUID(f"00000000-0000-0000-0001-{doctor_i:04d}{session_i:08d}")


async def _get_or_create(session, model, id_, **fields):
    existing = await session.get(model, id_)
    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing
    obj = model(id=id_, **fields)
    session.add(obj)
    return obj


async def _seed_chennai_fixture() -> None:
    async with SessionLocal() as session:
        for c in _CLINICS:
            await _get_or_create(
                session, Clinic, c["id"],
                name=c["name"], lat=c["lat"], lng=c["lng"],
                is_emergency_capable=c["is_emergency_capable"],
                state=c["state"], pin_code=c["pin_code"],
            )
        await session.flush()

        for d in _DOCTORS:
            u_id = doctor_user_id(d["i"])
            await _get_or_create(
                session, User, u_id,
                email=f"chennai.doctor{d['i']}@demo.example",
                phone=f"+9198{d['i']:04d}50000"[:15],
                password_hash="not-a-real-hash",
                role="doctor", is_active=True,
            )
            did = doctor_id(d["i"])
            await _get_or_create(
                session, Doctor, did,
                user_id=u_id, name=d["name"], specialties=d["specialties"],
                qualifications=None, nmc_reg_no=f"TNMC-{2010 + d['i']}-{500000 + d['i']:06d}",
                fee=d["fee"], rating=d["rating"], clinic_id=d["clinic"],
            )
            await session.flush()

            for session_i, (start, end) in enumerate(OPD_SESSIONS, start=1):
                await _get_or_create(
                    session, Availability, availability_id(d["i"], session_i),
                    doctor_id=did, clinic_id=d["clinic"], weekday=OPD_WEEKDAY,
                    start_time=start, end_time=end, slot_minutes=15,
                    valid_from=dt.date(2026, 1, 1), valid_to=dt.date(2026, 12, 31),
                )

        await session.commit()


@pytest_asyncio.fixture(autouse=True)
async def chennai_fixture() -> None:
    await _seed_chennai_fixture()
