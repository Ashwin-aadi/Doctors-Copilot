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


@pytest_asyncio.fixture
async def patient_conditions():
    """Set the patient's conditions in Postgres and restore them afterwards.

    The graph must mirror the record, so a test about the graph has to own what
    the record says -- asserting on whatever happens to be in Neo4j already is
    how stale projections pass for real evidence.
    """
    from app.db.models.patient import Patient
    from app.db.session import SessionLocal

    async def _set(value):
        async with SessionLocal() as db:
            patient = await db.get(Patient, PATIENT_1)
            previous = patient.conditions
            patient.conditions = value
            await db.commit()
            return previous

    original = await _set([{"name": "type 2 diabetes mellitus", "since": "2021-03-01"}])
    yield
    await _set(original)


@pytest.mark.asyncio
async def test_sync_patient_populates_context(patient_conditions):
    await sync_patient(PATIENT_1)
    context = await patient_context(PATIENT_1)
    assert [c["name"] for c in context["conditions"]] == ["type 2 diabetes mellitus"]
    assert "recent_labs" in context


@pytest.mark.asyncio
async def test_sync_patient_drops_what_postgres_no_longer_has(patient_conditions):
    """A condition removed from the record must leave the graph on the next
    sync. MERGE alone only ever adds, which left the copilot brief reasoning
    about diagnoses and drugs the patient no longer had."""
    from app.db.models.patient import Patient
    from app.db.session import SessionLocal

    await sync_patient(PATIENT_1)
    assert (await patient_context(PATIENT_1))["conditions"]

    async with SessionLocal() as db:
        patient = await db.get(Patient, PATIENT_1)
        patient.conditions = []
        await db.commit()

    await sync_patient(PATIENT_1)
    assert (await patient_context(PATIENT_1))["conditions"] == []


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
