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


# --- Pre-assessment reasoning detail (additive; every field defaulted) --------
# These expose the structured state and differential the pipeline reasons over,
# so a doctor can see WHY a triage level was assigned and check it against what
# the patient actually said. Existing consumers are unaffected.


class FindingOut(BaseModel):
    """One clinical concept as asserted by the patient, with its evidence."""

    name: str
    label: str
    category: str = "other"
    status: Literal["present", "absent", "unknown"] = "unknown"
    specificity: float = 0.4
    severity: str | None = None
    evidence: str = ""


class PatientStateOut(BaseModel):
    """The structured state every pipeline stage was given."""

    chief_complaint: str = ""
    duration_days: float | None = None
    present: list[FindingOut] = []
    absent: list[FindingOut] = []
    unknown: list[FindingOut] = []
    discriminating_features: list[str] = []


class DifferentialItem(BaseModel):
    """A condition worth considering, with what supports and opposes it."""

    condition: str
    likelihood: Literal["consider", "possible", "likely"] = "consider"
    supporting: list[str] = []
    against: list[str] = []
    discriminating_tests: list[str] = []
    citation_numbers: list[int] = []


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
    # Additive reasoning detail.
    differentials: list[DifferentialItem] = []
    patient_state: PatientStateOut | None = None
    uncertainty: list[str] = []
    consistency_notes: list[str] = []
