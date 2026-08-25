from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class PatientIn(BaseModel):
    name: str
    dob: date | None = None
    sex: str | None = None
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    conditions: list[str] = []
    allergies: list[str] = []
    medications: list[str] = []


class PatientOut(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    dob: date | None = None
    sex: str | None = None
    conditions: list[str] = []
    allergies: list[str] = []
    medications: list[str] = []
    consent_at: datetime | None = None
