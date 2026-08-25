from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented
from app.schemas.visit import VisitOut

router = APIRouter(prefix="/visits", tags=["visits"])


@router.get("/{visit_id}", response_model=VisitOut)
async def get_visit(visit_id: UUID) -> VisitOut:
    raise not_implemented("visit assembly lands in A3.4")


@router.post("/{visit_id}/advance", response_model=VisitOut)
async def advance_visit(visit_id: UUID) -> VisitOut:
    raise not_implemented("visit state machine lands in A3.4")
