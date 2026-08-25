import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Visit(Base, UUIDPKMixin):
    __tablename__ = "visits"

    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"))
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(32), default="TRIAGED")
    triage_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("triage_sessions.id"), nullable=True
    )
    lab_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lab_orders.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TriageSession(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "triage_sessions"

    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=True
    )
    transcript: Mapped[list] = mapped_column(JSONB, default=list)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class LabResult(Base, UUIDPKMixin):
    __tablename__ = "lab_results"

    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"))
    test_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255))
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    flag: Mapped[str] = mapped_column(String(16), default="unknown")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LabOrder(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "lab_orders"

    visit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("visits.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"))
    items: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)


class Prescription(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "prescriptions"

    visit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("visits.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"))
    items: Mapped[list] = mapped_column(JSONB, default=list)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)


class Medication(Base, UUIDPKMixin):
    __tablename__ = "medications"

    name: Mapped[str] = mapped_column(String(255))
    rxcui: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    ingredient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    form: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_generic: Mapped[bool] = mapped_column(Boolean, default=False)
