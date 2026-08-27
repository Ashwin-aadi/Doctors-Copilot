"""App lifespan plus the Redis pub/sub fabric behind the WebSocket routes.

State changes are published as JSON on a Redis channel by whoever made the
change (`app.services.visit`, the queue service), and `/ws/visit/{id}` and
`/ws/queue/{clinic_id}` subscribe and fan out. Going through Redis rather than
an in-process registry means the streams keep working with more than one
uvicorn worker, which is how the production compose file runs.

Publishing is best-effort: a state transition must never fail because Redis is
briefly unavailable, so `publish` logs and swallows.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import orjson
from fastapi import FastAPI

from app.core.logging import configure_logging, get_logger
from app.core.redis_client import get_redis

logger = get_logger("lifespan")
log = get_logger(__name__)

VISIT_CHANNEL = "visit.updated"
QUEUE_CHANNEL = "queue.updated"


def visit_channel(visit_id: str) -> str:
    return f"{VISIT_CHANNEL}:{visit_id}"


def queue_channel(clinic_id: str) -> str:
    return f"{QUEUE_CHANNEL}:{clinic_id}"


async def publish(channel: str, payload: dict[str, Any]) -> None:
    """Publish on the channel and, when the payload identifies one, its
    per-entity channel too -- so a socket can subscribe to a single visit
    without filtering the firehose."""

    message = orjson.dumps(payload).decode()
    targets = [channel]
    if channel == VISIT_CHANNEL and payload.get("visit_id"):
        targets.append(visit_channel(str(payload["visit_id"])))
    if channel == QUEUE_CHANNEL and payload.get("clinic_id"):
        targets.append(queue_channel(str(payload["clinic_id"])))

    try:
        redis = get_redis()
        for target in targets:
            await redis.publish(target, message)
    except Exception as exc:  # noqa: BLE001
        log.warning("event_publish_failed", channel=channel, error=str(exc))


@asynccontextmanager
async def subscribe(channel: str):
    """Async context manager yielding a pubsub handle subscribed to `channel`."""

    pubsub = get_redis().pubsub()
    await pubsub.subscribe(channel)
    try:
        yield pubsub
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except Exception as exc:  # noqa: BLE001
            log.warning("pubsub_close_failed", channel=channel, error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info("startup")
    yield
    logger.info("shutdown")
