from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Citation

# Indian casualty and OPD counters triage by colour, not by number. The numeric
# ESI value stays the machine-readable field; the colour is what staff and patients
# actually see on the queue board.
TriageColour = Literal["red", "yellow", "green"]


def colour_for_esi(severity_esi: int) -> TriageColour:
    """Map an ESI 1-5 severity onto the MoHFW/AIIMS three-colour casualty code."""
    if severity_esi <= 2:
        return "red"
    if severity_esi == 3:
        return "yellow"
    return "green"


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
    triage_colour: TriageColour
    specialty: str
    red_flags: list[str]
    suggested_labs: list[SuggestedLab]
    rationale: str
    citations: list[Citation]
    confidence: float
