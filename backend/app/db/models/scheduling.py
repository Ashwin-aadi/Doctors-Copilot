import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Time
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Clinic(Base, UUIDPKMixin):
    __tablename__ = "clinics"

    name: Mapped[str] = mapped_column(String(255))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    is_emergency_capable: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pin_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    # Facility tier: phc, chc, sdh, dh, private_clinic or private_hospital.
    facility_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Health-financing schemes the facility is empanelled under, e.g. pmjay.
    schemes: Mapped[list] = mapped_column(JSONB, default=list)


class Doctor(Base, UUIDPKMixin):
    __tablename__ = "doctors"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    specialties: Mapped[list] = mapped_column(JSONB, default=list)
    qualifications: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # National Medical Commission registration number.
    nmc_reg_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # State medical council that issued the registration.
    registration_council: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # ISO 639-1 codes for the languages the doctor consults in.
    languages: Mapped[list] = mapped_column(JSONB, default=list)
    # Consultation fee in INR.
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    clinic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinics.id"))


class Availability(Base, UUIDPKMixin):
    __tablename__ = "availabilities"

    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"))
    clinic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinics.id"))
    weekday: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    slot_minutes: Mapped[int] = mapped_column(Integer, default=15)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)


class Appointment(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "appointments"

    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"))
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"))
    clinic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinics.id"))
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="booked")


class QueueEntry(Base, UUIDPKMixin):
    __tablename__ = "queue_entries"

    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"))
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"))
    clinic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinics.id"))
    severity_esi: Mapped[int] = mapped_column(Integer)
    emergency: Mapped[bool] = mapped_column(Boolean, default=False)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="waiting")
