"""Auth dependency.

TEMP-ADAPTER: real JWT issuance lands with Pratyaksh's `app/core/security.py`
and `/auth/login` (see backend/tests/conftest.py's `auth_headers` fixture,
which already emits the `Bearer test-{role}-token` placeholder this resolves
against a seeded user of that role). Until then, `get_current_user` accepts
only that placeholder so routes can require auth today without blocking on
login being merged. Remove this file's placeholder branch -- and switch to
decoding a real access token -- once `/auth/login` exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.models.user import User
from app.db.session import get_db

_TOKEN_PREFIX = "test-"
_TOKEN_SUFFIX = "-token"


@dataclass
class CurrentUser:
    id: UUID
    role: str


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError("AUTH_INVALID_CREDENTIALS", "missing bearer token", status_code=401)

    token = authorization.removeprefix("Bearer ").strip()
    if not (token.startswith(_TOKEN_PREFIX) and token.endswith(_TOKEN_SUFFIX)):
        raise ApiError("AUTH_INVALID_CREDENTIALS", "unrecognized token", status_code=401)

    role = token[len(_TOKEN_PREFIX) : -len(_TOKEN_SUFFIX)] or "doctor"
    result = await db.execute(select(User).where(User.role == role).limit(1))
    user = result.scalar_one_or_none()
    if user is None:
        raise ApiError(
            "AUTH_FORBIDDEN", f"no seeded user with role={role!r} (run make seed)", status_code=403
        )
    return CurrentUser(id=user.id, role=user.role)
