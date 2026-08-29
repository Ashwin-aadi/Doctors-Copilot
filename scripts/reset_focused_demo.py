"""Reduce the database to the one clinical pathway worth demonstrating:
a single general-medicine doctor, with every clinical record cleared.

The bulk demo data (12 doctors across three cities) is useful for showing the
ranking optimiser off, but it makes a manual walkthrough ambiguous -- the
booker can land on any of six doctors, and the queue you open as `doctor1` is
not the queue the patient joined. This keeps Dr. Ananya Rao (general medicine,
Yamuna Nagar PHC) and deletes the other doctors, so booking has exactly one
possible outcome, and wipes every visit, triage session, document and lab
result so the walkthrough starts from nothing.

Staff, admin and patient accounts are left alone -- they do not affect which
doctor a booking lands on, and the security fixtures expect them to exist.

Idempotent: run it as often as you like. Destructive by design -- re-run
`scripts/seed.py` and `scripts/seed_demo.py` to get the full set back.

    python scripts/reset_focused_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import delete, select, text  # noqa: E402

from app.db.models.clinical import LabOrder, Prescription, TriageSession, Visit  # noqa: E402
from app.db.models.document import Document  # noqa: E402
from app.db.models.patient import Patient  # noqa: E402
from app.db.models.scheduling import Appointment, Availability, Doctor, QueueEntry  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

KEEP_DOCTOR_EMAIL = "doctor1@demo.example"
KEEP_PATIENT_EMAIL = "patient1@demo.example"


async def main() -> None:
    async with SessionLocal() as db:
        doctor = (
            await db.execute(
                select(Doctor).join(User, User.id == Doctor.user_id).where(
                    User.email == KEEP_DOCTOR_EMAIL
                )
            )
        ).scalar_one()
        patient = (
            await db.execute(
                select(Patient).join(User, User.id == Patient.user_id).where(
                    User.email == KEEP_PATIENT_EMAIL
                )
            )
        ).scalar_one()

        # Clinical records first -- visits point at lab orders, queue entries
        # point at appointments, so nothing here can be deleted out of order.
        await db.execute(text("UPDATE visits SET lab_order_id = NULL"))
        await db.execute(delete(QueueEntry))
        await db.execute(delete(Appointment))
        await db.execute(delete(LabOrder))
        await db.execute(delete(Prescription))
        await db.execute(delete(Visit))
        await db.execute(text("DELETE FROM lab_results"))
        await db.execute(delete(Document))
        await db.execute(text("DELETE FROM file_objects"))
        await db.execute(delete(TriageSession))

        # Then the other doctors -- the only thing that actually has to be
        # unique for the walkthrough, because they are what booking chooses
        # between. Staff, admin and the other patient accounts stay: they cost
        # the demo nothing and the security/RBAC fixtures need them to exist.
        await db.execute(delete(Availability).where(Availability.doctor_id != doctor.id))
        await db.execute(delete(Doctor).where(Doctor.id != doctor.id))
        await db.execute(text("DELETE FROM notifications"))
        await db.execute(text("DELETE FROM audit_logs"))
        await db.commit()

        slots = (
            await db.execute(
                select(Availability).where(Availability.doctor_id == doctor.id)
            )
        ).scalars().all()

    print(f"kept doctor  {doctor.name} ({KEEP_DOCTOR_EMAIL}) specialties={doctor.specialties}")
    print(f"kept patient {patient.name} ({KEEP_PATIENT_EMAIL})")
    print(f"clinic {doctor.clinic_id} with {len(slots)} availability rows")
    if not slots:
        print("WARNING: no availability -- booking will find no slots")


if __name__ == "__main__":
    asyncio.run(main())
