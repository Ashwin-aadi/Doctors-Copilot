from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(prefix="/notify", tags=["notify"])


@router.get("")
async def list_notifications() -> list:
    raise not_implemented("notifications owned by pratyaksh")


@router.post("")
async def create_notification() -> dict:
    raise not_implemented("notifications owned by pratyaksh")


@router.post("/{notification_id}/read")
async def mark_read(notification_id: UUID) -> dict:
    raise not_implemented("notifications owned by pratyaksh")
