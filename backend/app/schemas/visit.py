from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel

from app.schemas.copilot import CopilotBrief
from app.schemas.document import DocumentOut
from app.schemas.ml import InteractionReport
from app.schemas.scheduling import QueueEntryOut
from app.schemas.triage import TriageResult


class VisitState(str, Enum):
    TRIAGED = "TRIAGED"
    LABS_SUGGESTED = "LABS_SUGGESTED"
    LABS_APPROVED = "LABS_APPROVED"
    RESULTS_UPLOADED = "RESULTS_UPLOADED"
    BRIEF_READY = "BRIEF_READY"
    CONSULTED = "CONSULTED"
    PRESCRIBED = "PRESCRIBED"


class VisitOut(BaseModel):
    id: UUID
    patient_id: UUID
    doctor_id: UUID | None
    state: VisitState
    triage: TriageResult | None
    lab_order_id: UUID | None
    documents: list[DocumentOut] = []
    brief: CopilotBrief | None
    safety: InteractionReport | None
    queue: QueueEntryOut | None
    updated_at: datetime
