"""Rate limiting & progressive account lockout (CLAUDE.md P2.5).

`limiter` is a `slowapi.Limiter` backed by Redis (`settings.redis_url`), so
counts survive across worker processes/restarts the same way the captcha
and refresh-token bookkeeping already do. The key function resolves to the
caller's user id when a valid bearer token is present, falling back to the
client IP otherwise -- this makes an un-decorated route's registered
`default_limits` behave as "N/min/user" for authenticated calls and
"N/min/IP" for anonymous ones (register/login, before a token exists) in
one function, matching both flavours CLAUDE.md's limit table asks for
without two separate limiter instances.

Per-route stricter limits (login, register, this checkpoint's own
`POST /files`) are applied directly with `@limiter.limit(...)` where the
route lives in an owned file. Where the route lives in a file this
checkpoint does not own (`POST /documents/upload`, `/chat/patient`),
`limiter` is exported here for that file's owner to decorate with --
adding the decorator to their file myself would violate the "never edit
their files" rule, so it's noted to them in docs/DECISIONS.md instead.

Progressive lockout (5 consecutive failed logins -> 15 minute account
lock) is tracked separately, keyed by *email* rather than IP/user id, so
it survives an attacker rotating source IPs and blocks the account
regardless of who's asking.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import get_settings
from app.core.redis_client import redis_client

_LOGIN_FAILURE_PREFIX = "auth:login:fail:"
_LOGIN_LOCK_PREFIX = "auth:login:lock:"
MAX_CONSECUTIVE_LOGIN_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60


def _user_or_ip_key(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        try:
            from app.core.security import decode_token

            claims = decode_token(token)
            if claims.get("typ") == "access" and claims.get("sub"):
                return f"user:{claims['sub']}"
        except Exception:
            pass
    return get_remote_address(request)


def _storage_uri() -> str:
    return get_settings().redis_url


limiter = Limiter(
    key_func=_user_or_ip_key,
    storage_uri=_storage_uri(),
    default_limits=["120/minute"],
    headers_enabled=True,
)


async def record_login_failure(email: str) -> int:
    """Increment the per-email failure counter (TTL'd to the lockout window
    so it self-resets after a period with no failures); lock the account
    once the threshold is hit. Returns the new failure count."""
    key = f"{_LOGIN_FAILURE_PREFIX}{email}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, LOGIN_LOCKOUT_SECONDS)
    if count >= MAX_CONSECUTIVE_LOGIN_FAILURES:
        await redis_client.set(f"{_LOGIN_LOCK_PREFIX}{email}", "1", ex=LOGIN_LOCKOUT_SECONDS)
    return count


async def clear_login_failures(email: str) -> None:
    await redis_client.delete(f"{_LOGIN_FAILURE_PREFIX}{email}")
    await redis_client.delete(f"{_LOGIN_LOCK_PREFIX}{email}")


async def is_login_locked(email: str) -> bool:
    return bool(await redis_client.exists(f"{_LOGIN_LOCK_PREFIX}{email}"))


async def login_lock_retry_after(email: str) -> int:
    ttl = await redis_client.ttl(f"{_LOGIN_LOCK_PREFIX}{email}")
    return ttl if ttl and ttl > 0 else LOGIN_LOCKOUT_SECONDS
