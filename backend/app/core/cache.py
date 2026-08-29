"""Redis-backed cache for results that are expensive to compute and stable
once computed -- the clinical brief above all.

Two rules the callers depend on:

* **Fail open.** A cache miss and a dead Redis must look the same to the
  caller. Losing the cache should make the app slow, never broken.
* **Key on the inputs, not the clock.** A brief is invalidated by a new lab
  result, not by a timer, so callers build a fingerprint of what the result was
  derived from and let the TTL be a backstop rather than the mechanism.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import orjson

from app.core.logging import get_logger
from app.core.redis_client import get_redis

log = get_logger(__name__)

T = TypeVar("T")


def fingerprint(*parts: Any) -> str:
    """A short, stable digest of whatever the result was derived from."""
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


async def get_json(key: str) -> Any | None:
    try:
        raw = await get_redis().get(key)
    except Exception as exc:  # noqa: BLE001
        log.warning("cache_unavailable", op="get", key=key, error=str(exc))
        return None
    if raw is None:
        return None
    try:
        return orjson.loads(raw)
    except orjson.JSONDecodeError:
        # A poisoned entry is a miss, not an error the caller should see.
        return None


async def set_json(key: str, value: Any, *, ttl_seconds: int) -> None:
    try:
        await get_redis().set(key, orjson.dumps(value), ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        log.warning("cache_unavailable", op="set", key=key, error=str(exc))


async def cached_json(
    key: str,
    *,
    ttl_seconds: int,
    produce: Callable[[], Awaitable[T]],
    dump: Callable[[T], Any],
    load: Callable[[Any], T],
) -> T:
    """Return the cached value for `key`, or produce, store and return it."""
    hit = await get_json(key)
    if hit is not None:
        try:
            return load(hit)
        except Exception as exc:  # noqa: BLE001
            # The stored shape predates a schema change: rebuild rather than
            # fail the request on an entry we wrote ourselves.
            log.warning("cache_shape_stale", key=key, error=str(exc))
    value = await produce()
    await set_json(key, dump(value), ttl_seconds=ttl_seconds)
    return value


async def invalidate(*keys: str) -> None:
    if not keys:
        return
    try:
        await get_redis().delete(*keys)
    except Exception as exc:  # noqa: BLE001
        log.warning("cache_unavailable", op="delete", error=str(exc))
