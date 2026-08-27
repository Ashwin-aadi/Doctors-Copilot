"""Admin user management (checkpoint P3.5's "role change or deactivation
revokes every session immediately" requirement). Minimal by design -- this
checkpoint doesn't ask for a full user-management surface, just the one
mutation that has a security consequence (an ex-admin's still-valid refresh
tokens must stop working the moment their role/active flag changes)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.deps import CurrentUser, require_role
from app.core.errors import ApiError
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/users", tags=["users"])

_VALID_ROLES = ("patient", "doctor", "staff", "admin")


class UserStatusPatch(BaseModel):
    role: str | None = None
    is_active: bool | None = None


@router.patch("/{user_id}/status")
async def update_user_status(
    user_id: UUID,
    body: UserStatusPatch,
    _admin: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, user_id)
    if user is None:
        raise ApiError("NOT_FOUND", "user not found", status_code=404)

    if body.role is not None and body.role not in _VALID_ROLES:
        raise ApiError("VALIDATION_FAILED", "invalid role", status_code=422)

    changed = False
    if body.role is not None and body.role != user.role:
        user.role = body.role
        changed = True
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        changed = True

    await db.commit()
    if changed:
        await security.revoke_all_sessions(user.id)

    return {"id": user.id, "role": user.role, "is_active": user.is_active}
