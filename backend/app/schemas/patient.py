from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PatientIn(BaseModel):
    name: str
    dob: date | None = None
    sex: str | None = None
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    state: str | None = Field(default=None, description="Indian state or union territory")
    pin_code: str | None = Field(default=None, description="6-digit postal PIN code")
    abha_id: str | None = Field(
        default=None, description="Ayushman Bharat Health Account ID, 14 digits"
    )
    conditions: list[str] = []
    allergies: list[str] = []
    medications: list[str] = []


class PatientOut(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    dob: date | None = None
    sex: str | None = None
    state: str | None = None
    pin_code: str | None = None
    abha_id: str | None = None
    conditions: list[str] = []
    allergies: list[str] = []
    medications: list[str] = []
    consent_at: datetime | None = None
