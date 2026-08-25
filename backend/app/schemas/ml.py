from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Citation


class InteractionPair(BaseModel):
    drug_a: str
    rxcui_a: str | None
    drug_b: str
    rxcui_b: str | None
    severity: Literal["major", "moderate", "minor"]
    mechanism: str
    evidence_source: str
    url: str | None = None


class AllergyConflict(BaseModel):
    allergen: str
    drug: str
    rxcui: str | None
    rationale: str
    source: str


class Contraindication(BaseModel):
    drug: str
    condition: str
    rationale: str
    source: str


class InteractionReport(BaseModel):
    pairs: list[InteractionPair]
    allergy_conflicts: list[AllergyConflict]
    contraindications: list[Contraindication]
    generated_at: datetime


class SoapSummary(BaseModel):
    subjective: str
    objective: str
    assessment: str
    plan: str
    citations: list[Citation]
    confidence: float


class MedCandidate(BaseModel):
    name: str
    rxcui: str | None
    ingredient: str
    indication_match: float
    safety_flags: list[str]
    rationale: str
    source_url: str | None = None
