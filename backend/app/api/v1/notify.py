"""Notification query endpoints (checkpoint P3.2). Creation happens only via
`app/services/notify.py::notify()`, called by other routers -- there is no
public `POST /notify` since a client can't originate its own notification."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user
from app.core.errors import ApiError
from app.db.models.audit import Notification
from app.db.session import get_db

router = APIRouter(prefix="/notify", tags=["notify"])


def _serialize(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "payload": n.payload,
        "read_at": n.read_at,
        "created_at": n.created_at,
    }


@router.get("")
async def list_notifications(
    unread: bool = False,
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    limit = max(1, min(limit, 200))
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return [_serialize(n) for n in result.scalars().all()]


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)

    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(notification)
    return _serialize(notification)


@router.post("/read-all")
async def mark_all_read(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()
    return {"status": "ok"}
