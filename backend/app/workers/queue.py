"""RQ queue used to background document OCR/parse jobs.

Queue name ("copilot") matches the `make worker` target (`rq worker -u
$REDIS_URL copilot`), so anything enqueued here is picked up without extra
configuration.
"""

from __future__ import annotations

from uuid import UUID

from redis import Redis
from rq import Queue

from app.core.config import get_settings

QUEUE_NAME = "copilot"

_redis: Redis | None = None
_queue: Queue | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url)
    return _redis


def get_queue() -> Queue:
    global _queue
    if _queue is None:
        _queue = Queue(QUEUE_NAME, connection=get_redis())
    return _queue


def enqueue_process_document(document_id: UUID) -> None:
    from app.workers.ocr_worker import process_document

    get_queue().enqueue(process_document, str(document_id))
