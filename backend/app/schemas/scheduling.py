from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.triage import TriageColour


class DoctorRanked(BaseModel):
    doctor_id: UUID
    name: str
    specialty: str
    clinic_id: UUID
    clinic_name: str
    distance_km: float
    next_slot: datetime
    queue_load: int
    rating: float
    fee: float = Field(description="Consultation fee in INR")
    nmc_reg_no: str | None = Field(
        default=None, description="National Medical Commission registration number"
    )
    score: float
    reasons: list[str]


class QueueEntryOut(BaseModel):
    id: UUID
    patient_id: UUID
    patient_name: str
    doctor_id: UUID
    clinic_id: UUID
    severity_esi: int
    triage_colour: TriageColour = Field(
        description="MoHFW casualty colour code derived from severity_esi"
    )
    emergency: bool
    position: int
    waited_minutes: int
    estimated_wait_minutes: int
    status: Literal["waiting", "in_consult", "done", "cancelled"]
    reasons: list[str]
