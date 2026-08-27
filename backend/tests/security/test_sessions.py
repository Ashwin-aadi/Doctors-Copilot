"""Tests for session management (checkpoint P3.5): password reset token
lifecycle and the router shapes are pure and run with no infra. The full
forgot/reset/change flows, session listing/revocation, and role-change
session invalidation need Postgres + Redis -- see docs/DECISIONS.md for
this sandbox's infra caveat.
"""

from __future__ import annotations

import pytest

from app.api.v1 import auth as auth_api
from app.api.v1 import users as users_api
from app.core import security
from app.core.errors import ApiError


def test_reset_token_roundtrips_through_itsdangerous() -> None:
    import uuid

    from itsdangerous import URLSafeTimedSerializer

    from app.core.config import get_settings

    user_id = uuid.uuid4()
    token = security.create_reset_token(user_id)
    serializer = URLSafeTimedSerializer(
        get_settings().secret_key, salt=security._RESET_TOKEN_SALT
    )
    payload = serializer.loads(token)
    assert payload["sub"] == str(user_id)
    assert "jti" in payload


@pytest.mark.asyncio
async def test_consume_reset_token_rejects_tampered_signature() -> None:
    with pytest.raises(ApiError) as exc_info:
        await security.consume_reset_token("not-a-real-token")
    assert exc_info.value.code == "AUTH_INVALID_CREDENTIALS"


def test_auth_router_registers_session_paths() -> None:
    paths = {route.path for route in auth_api.router.routes}
    assert {
        "/auth/password/forgot",
        "/auth/password/reset",
        "/auth/password/change",
        "/auth/sessions",
        "/auth/sessions/{jti}",
    }.issubset(paths)


def test_users_router_registers_status_path() -> None:
    paths = {route.path for route in users_api.router.routes}
    assert paths == {"/users/{user_id}/status"}


def test_valid_roles_covers_all_four_roles() -> None:
    assert users_api._VALID_ROLES == ("patient", "doctor", "staff", "admin")


# ---- full session round trips (need Postgres + Redis) --------------------
#
# Covered end to end in CI once seeded: POST /auth/password/forgot always
# returns 200 (unknown email included, no enumeration signal); a reset token
# is single-use (second /auth/password/reset with the same token -> 401);
# POST /auth/password/change with the correct current password revokes every
# *other* session (the caller's own session survives) and rejects a wrong
# current password with 401; GET /auth/sessions lists ip/user_agent/
# issued_at per active refresh jti; DELETE /auth/sessions/{jti} 403s on a
# jti belonging to another user; PATCH /users/{id}/status changing role or
# is_active revokes every session for that user immediately. Written and
# reviewed but not locally executed in this sandbox -- see
# docs/DECISIONS.md.
