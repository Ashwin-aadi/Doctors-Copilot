#!/usr/bin/env python
"""Idempotent demo data seed: clinics, doctors, patients, availability, one visit.

All demo data is Indian: clinics in Delhi, Pune and Bengaluru, consultation fees in
INR, +91 phone numbers, state and PIN code addresses, NMC registration numbers for
doctors and placeholder ABHA IDs for patients.

Fixed UUIDs (documented in docs/ARCHITECTURE.md) so every teammate's tests and
manual curl sessions can reference the same records:
  clinics       00000000-0000-0000-0000-0000000000{01-03}
  doctor users  00000000-0000-0000-0000-0000000004{01-06}
  doctors       00000000-0000-0000-0000-0000000002{01-06}
  patient users 00000000-0000-0000-0000-0000000005{01-12}
  patients      00000000-0000-0000-0000-0000000001{01-12}
  visit         00000000-0000-0000-0000-000000000301
"""

import asyncio
import sys
from datetime import date, time, timedelta
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from passlib.context import CryptContext  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.models.clinical import LabResult, Visit  # noqa: E402
from app.db.models.patient import Patient  # noqa: E402
from app.db.models.scheduling import Availability, Clinic, Doctor  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DEMO_PASSWORD_HASH = pwd_context.hash("demo-password-123")

# Three real Indian cities so distance ranking and clinic choice look plausible
# in the demo: Delhi, Pune and Bengaluru.
CLINICS = [
    {"name": "Yamuna Nagar Primary Health Centre", "lat": 28.6139, "lng": 77.2090,
     "is_emergency_capable": True, "state": "Delhi", "pin_code": "110002"},
    {"name": "Shivaji Nagar Community Health Centre", "lat": 18.5308, "lng": 73.8470,
     "is_emergency_capable": False, "state": "Maharashtra", "pin_code": "411005"},
    {"name": "Jayanagar Multispecialty Clinic", "lat": 12.9250, "lng": 77.5938,
     "is_emergency_capable": True, "state": "Karnataka", "pin_code": "560041"},
]

DOCTOR_SPECIALTIES = [
    ["general_medicine"],
    ["cardiology"],
    ["pediatrics"],
    ["dermatology"],
    ["orthopedics"],
    ["neurology"],
]
DOCTOR_NAMES = [
    "Dr. Ananya Rao", "Dr. Vikram Shah", "Dr. Meera Iyer",
    "Dr. Rohan Kapoor", "Dr. Priya Nair", "Dr. Arjun Malhotra",
]
DOCTOR_QUALIFICATIONS = [
    "MBBS, MD (General Medicine)",
    "MBBS, MD (General Medicine), DM (Cardiology)",
    "MBBS, MD (Paediatrics)",
    "MBBS, MD (Dermatology)",
    "MBBS, MS (Orthopaedics)",
    "MBBS, MD (Medicine), DM (Neurology)",
]
# Consultation fees in INR, in the range an Indian clinic actually charges.
DOCTOR_FEES = [300.0, 800.0, 400.0, 500.0, 600.0, 900.0]

PATIENT_NAMES = [
    "Aarav Sharma", "Diya Patel", "Kabir Singh", "Ishita Gupta",
    "Vivaan Reddy", "Ananya Joshi", "Aditya Kumar", "Saanvi Menon",
    "Reyansh Verma", "Myra Choudhary", "Arnav Bose", "Kiara Pillai",
]
# One address per patient, cycling through the three clinic cities.
PATIENT_LOCALES = [
    ("Delhi", "110002", 28.61, 77.20),
    ("Maharashtra", "411005", 18.53, 73.84),
    ("Karnataka", "560041", 12.92, 77.59),
]


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


VISIT_ID = UUID("00000000-0000-0000-0000-000000000301")


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

        for i in range(1, 7):
            u_id = doctor_user_id(i)
            await _get_or_create(
                session, User, u_id,
                email=f"doctor{i}@doctorcopilot.dev", phone=f"+9198{i:04d}10000"[:15],
                password_hash=DEMO_PASSWORD_HASH, role="doctor", is_active=True,
            )
            clinic = clinic_id(((i - 1) % 3) + 1)
            await _get_or_create(
                session, Doctor, doctor_id(i),
                user_id=u_id, name=DOCTOR_NAMES[i - 1],
                specialties=DOCTOR_SPECIALTIES[i - 1],
                qualifications=DOCTOR_QUALIFICATIONS[i - 1],
                nmc_reg_no=f"NMC-{2015 + i}-{100000 + i * 7:06d}",
                fee=DOCTOR_FEES[i - 1],
                rating=4.2 + (i % 5) * 0.1, clinic_id=clinic,
            )
        await session.flush()

        today = date.today()
        for i in range(1, 7):
            d_id = doctor_id(i)
            for weekday in range(5):  # Mon-Fri
                avail_id = UUID(f"00000000-0000-0000-0000-{700000 + i * 10 + weekday:012d}")
                await _get_or_create(
                    session, Availability, avail_id,
                    doctor_id=d_id, clinic_id=clinic_id(((i - 1) % 3) + 1),
                    weekday=weekday, start_time=time(9, 0), end_time=time(17, 0),
                    slot_minutes=30, valid_from=today, valid_to=today + timedelta(days=14),
                )
        await session.flush()

        # Patient 1 (the seeded visit's patient) carries realistic clinical history
        # so knowledge-graph sync and the clinical copilot brief have real content
        # to work with, rather than an empty demo record.
        PATIENT_1_CONDITIONS = [{"name": "type 2 diabetes mellitus", "since": "2021-03-01"}]
        PATIENT_1_ALLERGIES = [{"name": "penicillin", "severity": "moderate"}]
        PATIENT_1_MEDICATIONS = [{"name": "metformin", "rxcui": "6809", "dose": "500mg BD"}]

        for i in range(1, 13):
            u_id = patient_user_id(i)
            state, pin, base_lat, base_lng = PATIENT_LOCALES[(i - 1) % 3]
            await _get_or_create(
                session, User, u_id,
                email=f"patient{i}@doctorcopilot.dev", phone=f"+9199{i:04d}20000"[:15],
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
                # Placeholder ABHA IDs in the real 14-digit format, for demo only.
                abha_id=f"91{i:04d}0000{i:04d}"[:14],
                conditions=PATIENT_1_CONDITIONS if i == 1 else [],
                allergies=PATIENT_1_ALLERGIES if i == 1 else [],
                medications=PATIENT_1_MEDICATIONS if i == 1 else [],
                consent_at=None,
            )
        await session.flush()

        result = await session.execute(select(Visit).where(Visit.id == VISIT_ID))
        if result.scalar_one_or_none() is None:
            from datetime import UTC, datetime

            session.add(
                Visit(
                    id=VISIT_ID,
                    patient_id=patient_id(1),
                    doctor_id=doctor_id(1),
                    state="TRIAGED",
                    triage_session_id=None,
                    lab_order_id=None,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )

        lab_id = UUID("00000000-0000-0000-0000-000000000901")
        result = await session.execute(select(LabResult).where(LabResult.id == lab_id))
        if result.scalar_one_or_none() is None:
            session.add(
                LabResult(
                    id=lab_id,
                    document_id=None,
                    patient_id=patient_id(1),
                    test_name="HbA1c",
                    normalized_name="hemoglobin_a1c",
                    value_num=9.2,
                    value_text=None,
                    unit="%",
                    ref_low=4.0,
                    ref_high=5.6,
                    flag="high",
                    confidence=0.95,
                    observed_at=None,
                )
            )

        await session.commit()
    print("seed OK: 3 clinics, 6 doctors, 12 patients, availability, 1 demo visit")


if __name__ == "__main__":
    asyncio.run(seed())
