"""Audit log query endpoint (checkpoint P2.4). Read-only by design -- the
table itself is append-only (see
alembic/versions/c7e2a9f01b3d_audit_log_append_only.py), and this router
exposes no mutation route at all.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.db.models.audit import AuditLog
from app.db.session import get_db

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", dependencies=[Depends(require_role("doctor", "admin"))])
async def list_audit(
    entity: str | None = None,
    entity_id: str | None = None,
    actor_id: UUID | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = select(AuditLog)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if from_:
        stmt = stmt.where(AuditLog.ts >= from_)
    if to:
        stmt = stmt.where(AuditLog.ts <= to)

    stmt = stmt.order_by(AuditLog.ts.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)

    return [
        {
            "id": row.id,
            "actor_id": row.actor_id,
            "role": row.role,
            "action": row.action,
            "entity": row.entity,
            "entity_id": row.entity_id,
            "ip": row.ip,
            "user_agent": row.user_agent,
            "diff_hash": row.diff_hash,
            "ts": row.ts,
        }
        for row in result.scalars().all()
    ]
