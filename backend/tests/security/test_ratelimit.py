"""Tests for app.core.ratelimit: the Redis-backed limiter's key function and
the progressive login-lockout bookkeeping. Login-failure counting needs a
reachable Redis -- see docs/DECISIONS.md. The key-function selection logic
(user vs. IP) is pure and runs with no infra.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from starlette.requests import Request

from app.core.ratelimit import (
    MAX_CONSECUTIVE_LOGIN_FAILURES,
    _user_or_ip_key,
    clear_login_failures,
    is_login_locked,
    record_login_failure,
)
from app.core.security import create_access_token


def _fake_request(headers: dict[str, str] | None = None) -> Request:
    header_list = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "headers": header_list,
        "client": ("203.0.113.5", 12345),
        "scheme": "http",
        "server": ("testserver", 80),
        "query_string": b"",
        "root_path": "",
    }
    return Request(scope)


def test_key_func_falls_back_to_ip_when_no_bearer_token() -> None:
    request = _fake_request()
    assert _user_or_ip_key(request) == "203.0.113.5"


def test_key_func_uses_user_id_for_valid_access_token() -> None:
    user_id = UUID("00000000-0000-0000-0000-000000000101")
    token = create_access_token(user_id, "patient")
    request = _fake_request({"authorization": f"Bearer {token}"})
    assert _user_or_ip_key(request) == f"user:{user_id}"


def test_key_func_falls_back_to_ip_for_garbage_token() -> None:
    request = _fake_request({"authorization": "Bearer not-a-real-jwt"})
    assert _user_or_ip_key(request) == "203.0.113.5"


def test_key_func_falls_back_to_ip_for_refresh_typed_token() -> None:
    from app.core.security import create_refresh_token

    user_id = UUID("00000000-0000-0000-0000-000000000101")
    token = create_refresh_token(user_id, "patient")
    request = _fake_request({"authorization": f"Bearer {token}"})
    # A refresh token presented as a bearer must not be treated as an
    # authenticated identity for rate-limiting purposes.
    assert _user_or_ip_key(request) == "203.0.113.5"


def test_max_consecutive_login_failures_is_five() -> None:
    assert MAX_CONSECUTIVE_LOGIN_FAILURES == 5


# ---- Redis-backed round trips -----------------------------------------


@pytest.mark.asyncio
async def test_progressive_lockout_after_five_failures() -> None:
    email = "lockout-probe@demo.example"
    await clear_login_failures(email)
    try:
        for _ in range(MAX_CONSECUTIVE_LOGIN_FAILURES - 1):
            await record_login_failure(email)
            assert not await is_login_locked(email)
        await record_login_failure(email)
        assert await is_login_locked(email)
    finally:
        await clear_login_failures(email)


@pytest.mark.asyncio
async def test_clear_login_failures_unlocks_account() -> None:
    email = "lockout-probe-2@demo.example"
    for _ in range(MAX_CONSECUTIVE_LOGIN_FAILURES):
        await record_login_failure(email)
    assert await is_login_locked(email)
    await clear_login_failures(email)
    assert not await is_login_locked(email)


# ---- full API round trips (need Postgres + Redis) --------------------------
#
# Covered end to end in CI once seeded: 7 consecutive bad-password logins
# for the same account -> first 5 are 401 AUTH_INVALID_CREDENTIALS, the
# 6th and 7th are 429 RATE_LIMITED with a Retry-After header (the checkpoint
# P2.5 verify sequence: "401 401 401 401 401 429 429"). Written and
# reviewed against app/api/v1/auth.py's login() but not locally executed in
# this sandbox -- see docs/DECISIONS.md.
