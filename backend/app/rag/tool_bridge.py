"""Bridge from RAG/orchestration code to Virat's `app.ml.tools` module: a
20s timeout plus a simple 3-failures/60s circuit breaker around every call,
so a slow or broken ML tool degrades the clinical brief rather than hanging
or 500ing the request.

TEMP-ADAPTER: `app.ml.tools` (flag_labs, extract_entities, check_interactions)
has not shipped yet. Until it does, every wrapped call below returns its
typed empty result exactly as it would with the breaker open. Remove this
adapter block once app/ml/tools.py exists -- the real functions.
"""

import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

import anyio

from app.core.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")

_TIMEOUT_SECONDS = 20.0
_FAILURE_THRESHOLD = 3
_RESET_SECONDS = 60.0

_failures: dict[str, list[float]] = {}


def _breaker_open(name: str) -> bool:
    now = time.monotonic()
    hits = [t for t in _failures.get(name, []) if now - t < _RESET_SECONDS]
    _failures[name] = hits
    return len(hits) >= _FAILURE_THRESHOLD


def _record_failure(name: str) -> None:
    _failures.setdefault(name, []).append(time.monotonic())


async def _guarded_call(name: str, fn: Callable[..., Awaitable[T]], fallback: T, *args, **kwargs) -> T:
    if _breaker_open(name):
        log.warning("tool_bridge_circuit_open", tool=name)
        return fallback
    try:
        with anyio.fail_after(_TIMEOUT_SECONDS):
            return await fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        _record_failure(name)
        log.warning("tool_bridge_call_failed", tool=name, error=str(exc))
        return fallback


try:
    from app.ml.tools import (
        check_interactions as _check_interactions,  # type: ignore[import-not-found]
    )
    from app.ml.tools import extract_entities as _extract_entities  # type: ignore[import-not-found]
    from app.ml.tools import flag_labs as _flag_labs  # type: ignore[import-not-found]
except ImportError:

    async def _flag_labs(*args, **kwargs) -> list[dict]:  # noqa: ARG001
        return []

    async def _extract_entities(*args, **kwargs) -> dict:  # noqa: ARG001
        return {"conditions": [], "medications": [], "allergens": []}

    async def _check_interactions(*args, **kwargs) -> dict:  # noqa: ARG001
        return {"pairs": [], "allergy_conflicts": [], "contraindications": []}


async def flag_labs(patient_id, labs: list[dict]) -> list[dict]:
    return await _guarded_call("flag_labs", _flag_labs, [], patient_id, labs)


async def extract_entities(text: str) -> dict:
    empty = {"conditions": [], "medications": [], "allergens": []}
    return await _guarded_call("extract_entities", _extract_entities, empty, text)


async def check_interactions(patient_id, medications: list[dict]) -> dict:
    empty = {"pairs": [], "allergy_conflicts": [], "contraindications": []}
    return await _guarded_call("check_interactions", _check_interactions, empty, patient_id, medications)
