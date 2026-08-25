from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


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
    fee: float
    score: float
    reasons: list[str]


class QueueEntryOut(BaseModel):
    id: UUID
    patient_id: UUID
    patient_name: str
    doctor_id: UUID
    clinic_id: UUID
    severity_esi: int
    emergency: bool
    position: int
    waited_minutes: int
    estimated_wait_minutes: int
    status: Literal["waiting", "in_consult", "done", "cancelled"]
    reasons: list[str]
