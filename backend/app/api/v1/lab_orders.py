from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(prefix="/lab-orders", tags=["lab-orders"])


@router.post("/recommend")
async def recommend_lab_order() -> dict:
    raise not_implemented("lab order recommendation owned by niyati")


@router.get("/{lab_order_id}")
async def get_lab_order(lab_order_id: UUID) -> dict:
    raise not_implemented("lab order fetch owned by niyati")
