from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.errors import not_implemented
from app.schemas.copilot import CopilotBrief

router = APIRouter(prefix="/copilot", tags=["copilot"])


class BriefIn(BaseModel):
    visit_id: UUID


@router.post("/brief", response_model=CopilotBrief)
async def build_brief(body: BriefIn) -> CopilotBrief:
    raise not_implemented("clinical copilot brief lands in A2.4")
