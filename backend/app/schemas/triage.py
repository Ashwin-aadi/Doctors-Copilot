from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Citation


class SuggestedLab(BaseModel):
    name: str
    loinc: str | None = None
    reason: str
    source: Literal["rule", "rag", "both"] = "rag"


class TriageMessageIn(BaseModel):
    session_id: UUID
    content: str


class TriageTurnOut(BaseModel):
    session_id: UUID
    assistant: str
    done: bool
    quick_replies: list[str] = []
    questions_asked: int


class TriageResult(BaseModel):
    session_id: UUID
    patient_id: UUID | None
    severity_esi: int = Field(ge=1, le=5)
    specialty: str
    red_flags: list[str]
    suggested_labs: list[SuggestedLab]
    rationale: str
    citations: list[Citation]
    confidence: float
