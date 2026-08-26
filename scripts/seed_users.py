#!/usr/bin/env python
"""Idempotent demo-account seed: 2 admins, 2 staff, 6 doctors, 12 patients,
all password `Demo@12345` (the spec's literal `Demo@1234` is 9 characters,
one short of this checkpoint's own >=10-char password policy in
app/core/security.py -- bumped by one digit so every seeded account can
actually log in; see docs/DECISIONS.md).

Uses the *same* fixed UUIDs as scripts/seed.py (Ashwin's) for clinics,
doctors and patients so both scripts write to the same rows -- get_or_create
semantics mean whichever runs last wins on the overlapping fields (email,
password, names). This script additionally seeds the 2 admin + 2 staff
accounts that scripts/seed.py doesn't create at all. See docs/DECISIONS.md
for the cross-script overlap this causes and why it wasn't consolidated.

All demo data is Indian: clinics in Delhi, Pune and Bengaluru, +91 mobiles,
state + 6-digit PIN addresses, NMC registration numbers for doctors,
placeholder ABHA ids for patients, fees in INR.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.models.patient import Patient  # noqa: E402
from app.db.models.scheduling import Clinic, Doctor  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

DEMO_PASSWORD = "Demo@12345"
DEMO_PASSWORD_HASH = hash_password(DEMO_PASSWORD)

CLINICS = [
    {"name": "Yamuna Nagar Primary Health Centre", "lat": 28.6139, "lng": 77.2090,
     "is_emergency_capable": True, "state": "Delhi", "pin_code": "110002"},
    {"name": "Shivaji Nagar Community Health Centre", "lat": 18.5308, "lng": 73.8470,
     "is_emergency_capable": False, "state": "Maharashtra", "pin_code": "411005"},
    {"name": "Jayanagar Multispecialty Clinic", "lat": 12.9250, "lng": 77.5938,
     "is_emergency_capable": True, "state": "Karnataka", "pin_code": "560041"},
]

DOCTOR_NAMES = [
    "Dr. Ananya Rao", "Dr. Vikram Shah", "Dr. Meera Iyer",
    "Dr. Rohan Kapoor", "Dr. Priya Nair", "Dr. Arjun Malhotra",
]
DOCTOR_SPECIALTIES = [
    ["general_medicine"], ["cardiology"], ["pediatrics"],
    ["dermatology"], ["orthopedics"], ["neurology"],
]
DOCTOR_QUALIFICATIONS = [
    "MBBS, MD (General Medicine)", "MBBS, MD (General Medicine), DM (Cardiology)",
    "MBBS, MD (Paediatrics)", "MBBS, MD (Dermatology)",
    "MBBS, MS (Orthopaedics)", "MBBS, MD (Medicine), DM (Neurology)",
]
DOCTOR_FEES = [300.0, 800.0, 400.0, 500.0, 600.0, 900.0]

PATIENT_NAMES = [
    "Aarav Sharma", "Fatima Sheikh", "Kabir Singh", "Meera Nair",
    "Gurpreet Kaur", "Ananya Das", "Rohan Patil", "Saanvi Menon",
    "Reyansh Verma", "Myra Choudhary", "Arnav Bose", "Kiara Pillai",
]
PATIENT_LOCALES = [
    ("Delhi", "110002", 28.61, 77.20),
    ("Maharashtra", "411005", 18.53, 73.84),
    ("Karnataka", "560041", 12.92, 77.59),
]

STAFF_NAMES = ["Neha Kulkarni", "Suresh Pillai"]
ADMIN_NAMES = ["Ritu Agarwal", "Manoj Krishnan"]


def clinic_id(i: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{i:012d}")


def doctor_user_id(i: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{400 + i:012d}")


def doctor_id(i: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{200 + i:012d}")


def patient_user_id(i: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{500 + i:012d}")


def patient_id(i: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{100 + i:012d}")


def admin_user_id(i: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{600 + i:012d}")


def staff_user_id(i: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{602 + i:012d}")


async def _get_or_create(session, model, id_, **fields):
    existing = await session.get(model, id_)
    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing
    obj = model(id=id_, **fields)
    session.add(obj)
    return obj


async def seed() -> None:
    async with SessionLocal() as session:
        for i, c in enumerate(CLINICS, start=1):
            await _get_or_create(
                session, Clinic, clinic_id(i),
                name=c["name"], lat=c["lat"], lng=c["lng"],
                is_emergency_capable=c["is_emergency_capable"],
                state=c["state"], pin_code=c["pin_code"],
            )
        await session.flush()

        for i in range(1, 3):
            await _get_or_create(
                session, User, admin_user_id(i),
                email=f"admin{i}@demo.example", phone=f"+9190{i:04d}30000"[:15],
                password_hash=DEMO_PASSWORD_HASH, role="admin", is_active=True,
            )
        for i in range(1, 3):
            await _get_or_create(
                session, User, staff_user_id(i),
                email=f"staff{i}@demo.example", phone=f"+9191{i:04d}40000"[:15],
                password_hash=DEMO_PASSWORD_HASH, role="staff", is_active=True,
            )

        for i in range(1, 7):
            u_id = doctor_user_id(i)
            await _get_or_create(
                session, User, u_id,
                email=f"doctor{i}@demo.example", phone=f"+9198{i:04d}10000"[:15],
                password_hash=DEMO_PASSWORD_HASH, role="doctor", is_active=True,
            )
            await _get_or_create(
                session, Doctor, doctor_id(i),
                user_id=u_id, name=DOCTOR_NAMES[i - 1],
                specialties=DOCTOR_SPECIALTIES[i - 1],
                qualifications=DOCTOR_QUALIFICATIONS[i - 1],
                nmc_reg_no=f"NMC-{2015 + i}-{100000 + i * 7:06d}",
                fee=DOCTOR_FEES[i - 1],
                rating=4.2 + (i % 5) * 0.1, clinic_id=clinic_id(((i - 1) % 3) + 1),
            )
        await session.flush()

        for i in range(1, 13):
            u_id = patient_user_id(i)
            state, pin, base_lat, base_lng = PATIENT_LOCALES[(i - 1) % 3]
            await _get_or_create(
                session, User, u_id,
                email=f"patient{i}@demo.example", phone=f"+9199{i:04d}20000"[:15],
                password_hash=DEMO_PASSWORD_HASH, role="patient", is_active=True,
            )
            await _get_or_create(
                session, Patient, patient_id(i),
                user_id=u_id, name=PATIENT_NAMES[i - 1],
                dob=date(1980 + i, (i % 12) + 1, (i % 28) + 1),
                sex="female" if i % 2 == 0 else "male",
                lat=base_lat + i * 0.005, lng=base_lng + i * 0.005,
                address=f"{i}, Gandhi Road, {state}",
                state=state, pin_code=pin,
                abha_id=f"{10 + i:02d}-{1000 + i:04d}-{2000 + i:04d}-{3000 + i:04d}",
                conditions=[], allergies=[], medications=[], consent_at=None,
            )

        await session.commit()

        result = await session.execute(select(User.role, User.email).order_by(User.role))
        counts: dict[str, int] = {}
        for role, _ in result.all():
            counts[role] = counts.get(role, 0) + 1
        print(f"seed_users OK: {counts}")


if __name__ == "__main__":
    asyncio.run(seed())
