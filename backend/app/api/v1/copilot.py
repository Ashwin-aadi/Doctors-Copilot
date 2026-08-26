from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.db.session import get_db
from app.rag.clinical_rag import build_brief
from app.schemas.copilot import CopilotBrief

router = APIRouter(prefix="/copilot", tags=["copilot"])


class BriefIn(BaseModel):
    visit_id: UUID


@router.post("/brief", response_model=CopilotBrief)
async def build_brief_route(
    body: BriefIn,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("doctor")),
) -> CopilotBrief:
    return await build_brief(body.visit_id, db)
