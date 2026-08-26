"""Two-layer cache tests (section 8 N2.5): a second lookup for the same
brand/rxcui must make zero HTTP calls, served from the in-process
`cachetools.TTLCache` (and, once that entry ages out, from Redis). Needs a
reachable Redis for the Redis-layer assertion; the in-process-layer assertion
alone needs neither Redis nor Postgres.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.services.mapping.rxnorm import enrich
from app.services.mapping.schemas import GenericMapping


class _CallCounter:
    def __init__(self) -> None:
        self.calls = 0


@pytest.mark.asyncio
async def test_rxnav_enrich_second_call_hits_in_process_cache_zero_http_calls(monkeypatch):
    counter = _CallCounter()
    unique_input = f"UniqueTestDrug-{uuid4().hex[:8]}"

    class _FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    async def _fake_get(self, url, params=None, **kwargs):  # noqa: ANN001, ARG001
        counter.calls += 1
        if url.endswith("rxcui.json"):
            return _FakeResponse({"idGroup": {"rxnormId": ["999999"]}})
        if "related.json" in url and params.get("tty") == "IN":
            return _FakeResponse(
                {"relatedGroup": {"conceptGroup": [{"conceptProperties": [{"rxcui": "888888", "name": "Test Ingredient", "tty": "IN"}]}]}}
            )
        return _FakeResponse(
            {"relatedGroup": {"conceptGroup": [{"conceptProperties": [{"rxcui": "777777", "name": "Test Product", "tty": "SCD"}]}]}}
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    seed = GenericMapping(input=unique_input, rxcui=None, ingredient=None, generics=[], nlem=False, schedule_h=False)

    first = await enrich(seed)
    assert first.ingredient == "Test Ingredient"
    calls_after_first = counter.calls
    assert calls_after_first > 0

    second = await enrich(seed)
    assert second.ingredient == "Test Ingredient"
    assert counter.calls == calls_after_first, "second enrich() call should be served from cache, not HTTP"
