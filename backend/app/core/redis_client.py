"""Shared async Redis client for captcha challenges, refresh-token bookkeeping,
and rate limiting. One connection pool per process, created lazily so importing
this module never opens a socket at import time (tests can import freely even
with no Redis reachable).
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


class _LazyRedis:
    """Proxies attribute access to the lazily-constructed client, so callers can
    keep writing `redis_client.get(...)` without importing `get_redis()` everywhere.
    """

    def __getattr__(self, name: str):
        return getattr(get_redis(), name)


redis_client = _LazyRedis()
