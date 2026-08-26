"""Requires a running Neo4j (docker compose) and Postgres seeded via
scripts/seed.py -- skipped automatically when Neo4j is unreachable so the
rest of the suite still runs offline.
"""

from uuid import UUID

import pytest
import pytest_asyncio

from app.kg.client import run_query
from app.kg.ingest import sync_patient
from app.kg.queries import patient_context, patient_timeline

PATIENT_1 = UUID("00000000-0000-0000-0000-000000000101")


@pytest_asyncio.fixture(autouse=True)
async def _require_neo4j():
    rows = await run_query("RETURN 1 AS ok")
    if not rows:
        pytest.skip("Neo4j not reachable in this environment")


@pytest.mark.asyncio
async def test_sync_patient_populates_context():
    await sync_patient(PATIENT_1)
    context = await patient_context(PATIENT_1)
    assert context["conditions"], context
    assert "recent_labs" in context


@pytest.mark.asyncio
async def test_sync_patient_is_idempotent():
    await sync_patient(PATIENT_1)
    await sync_patient(PATIENT_1)
    context = await patient_context(PATIENT_1)
    names = [c["name"] for c in context["conditions"]]
    assert len(names) == len(set(names))


@pytest.mark.asyncio
async def test_patient_timeline_reflects_encounters():
    await sync_patient(PATIENT_1)
    timeline = await patient_timeline(PATIENT_1)
    assert isinstance(timeline, list)


@pytest.mark.asyncio
async def test_unreachable_graph_degrades_to_empty(monkeypatch):
    async def _boom(*args, **kwargs):
        raise ConnectionError("simulated graph outage")

    import app.kg.client as client_module

    monkeypatch.setattr(client_module, "_driver", lambda: (_ for _ in ()).throw(ConnectionError()))
    context = await patient_context(PATIENT_1)
    assert context == {"conditions": [], "medications": [], "allergies": [], "recent_labs": []}
