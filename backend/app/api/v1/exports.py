from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/{export_type}/{entity_id}.pdf")
async def export_pdf(export_type: str, entity_id: UUID) -> dict:
    raise not_implemented("pdf export owned by pratyaksh")
