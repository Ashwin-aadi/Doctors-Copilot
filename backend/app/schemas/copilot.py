from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import Citation


class CopilotBrief(BaseModel):
    visit_id: UUID
    summary: str
    differentials: list[str]
    recommended_procedures: list[str]
    cautions: list[str]
    citations: list[Citation]
    confidence: float
