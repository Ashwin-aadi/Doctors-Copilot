from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ClinicalEntry(BaseModel):
    """One condition, allergy or medication on a patient record.

    Stored as JSONB, so both shapes exist in the wild: the flat `"penicillin"`
    an intake form produces, and the structured `{"name": "penicillin",
    "severity": "moderate"}` the knowledge graph and the copilot brief need. A
    bare string is coerced into `{"name": ...}` on the way in, so neither
    producer breaks and every consumer sees one shape.
    """

    name: str
    since: str | None = Field(default=None, description="ISO date the condition was recorded")
    severity: str | None = Field(default=None, description="Allergy severity, when known")
    dose: str | None = Field(default=None, description="e.g. '500mg BD'")
    rxcui: str | None = Field(default=None, description="RxNorm concept id, when mapped")

    @model_validator(mode="before")
    @classmethod
    def _accept_bare_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"name": value}
        return value


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
    conditions: list[ClinicalEntry] = []
    allergies: list[ClinicalEntry] = []
    medications: list[ClinicalEntry] = []


class PatientOut(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    dob: date | None = None
    sex: str | None = None
    state: str | None = None
    pin_code: str | None = None
    abha_id: str | None = None
    conditions: list[ClinicalEntry] = []
    allergies: list[ClinicalEntry] = []
    medications: list[ClinicalEntry] = []
    consent_at: datetime | None = None
