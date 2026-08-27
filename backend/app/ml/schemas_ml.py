"""Pydantic models owned by the V2/V3 ML surface (NER, safety, labs, summary).

Kept separate from `app.schemas.ml` (Ashwin's frozen request/response
contracts for the `/ml/*` routes) since these are internal shapes used
between `app/ml/*.py` modules and, in the lab-flagging case, an additive
subclass of a schema I don't own -- see `LabResultExtended` below.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.document import LabResultOut


class DoseInfo(BaseModel):
    amount: float | None = None
    unit: str | None = None
    frequency: str | None = None


class DrugEntity(BaseModel):
    text: str
    start: int
    end: int
    generic_name: str
    rxcui: str | None = None
    dose: DoseInfo | None = None
    negated: bool = False
    historical: bool = False
    confidence: float = 0.8


class ConditionEntity(BaseModel):
    text: str
    start: int
    end: int
    negated: bool = False
    historical: bool = False
    confidence: float = 0.8


class AllergenEntity(BaseModel):
    text: str
    start: int
    end: int
    generic_name: str
    rxcui: str | None = None
    negated: bool = False
    confidence: float = 0.8


class EntityBundle(BaseModel):
    drugs: list[DrugEntity] = []
    conditions: list[ConditionEntity] = []
    allergens: list[AllergenEntity] = []
    ner_tier: str = "unavailable"


class LabResultExtended(LabResultOut):
    """Additive subclass -- do not fold fields back into Ashwin's LabResultOut."""

    trend: Literal["rising", "falling", "stable"] | None = None


class EntityRequest(BaseModel):
    text: str


class InteractionRequest(BaseModel):
    medications: list[str] = []
    allergies: list[str] = []
    conditions: list[str] = []


class LabFlagInput(BaseModel):
    test_name: str
    normalized_name: str
    value: float | str
    unit: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None
    confidence: float = 1.0
    page: int = 1
    observed_at: str | None = None


class LabFlagRequest(BaseModel):
    patient_id: UUID
    results: list[LabFlagInput]


class SummaryRequest(BaseModel):
    patient_id: UUID
    visit_id: UUID


class MedSuggestRequest(BaseModel):
    conditions: list[str]
    current_medications: list[str] = []
    allergies: list[str] = []
    renal_impairment: bool = False
    hepatic_impairment: bool = False
