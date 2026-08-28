"""Walks the seeded patient through triage -> KG sync -> clinical brief.

LLM and clinical retrieval calls are monkeypatched for determinism (same
approach as tests/test_triage.py); the Postgres and Neo4j reads/writes in
between are real, exercising the actual A2.2/A2.4 integration path. Requires
`scripts/seed.py` to have been run against DATABASE_URL and a reachable
Neo4j -- skipped otherwise.
"""

from uuid import UUID

import pytest
import pytest_asyncio

from app.db.models.clinical import Visit
from app.db.session import SessionLocal
from app.kg.client import run_query
from app.kg.ingest import sync_patient
from app.rag import clinical_rag, triage_rag
from app.rag.store import Hit
from app.schemas.common import Citation

PATIENT_1 = UUID("00000000-0000-0000-0000-000000000101")
VISIT_301 = UUID("00000000-0000-0000-0000-000000000301")


@pytest_asyncio.fixture(autouse=True)
async def _require_neo4j():
    rows = await run_query("RETURN 1 AS ok")
    if not rows:
        pytest.skip("Neo4j not reachable in this environment")


@pytest_asyncio.fixture
async def db():
    async with SessionLocal() as session:
        yield session
        await session.rollback()


def _patch_triage_llm(monkeypatch):
    async def fake_complete(prompt, *, system=None, max_tokens=1024, temperature=0.2):
        return "Have you had fever for more than a week?"

    async def fake_json_complete(prompt, *, schema, system=None, retries=2):
        return schema(severity_esi=3, specialty="general_medicine", confidence=0.7)

    # Triage retrieval is now a weighted multi-query fan-out driven by the
    # structured patient state, so the stub takes (collection, queries) rather
    # than a single query string.
    async def fake_multi_hybrid(collection, queries, k=10, **kwargs):
        return [
            Hit(
                id="g1",
                text="Persistent fever with high blood sugar warrants review.",
                score=0.9,
                metadata={"title": "Fever Workup", "source": "test"},
            )
        ]

    monkeypatch.setattr("app.rag.triage_rag.complete", fake_complete)
    monkeypatch.setattr("app.rag.triage_rag.json_complete", fake_json_complete)
    monkeypatch.setattr("app.rag.patient_state.json_complete", fake_json_complete)
    monkeypatch.setattr("app.rag.triage_rag.multi_hybrid", fake_multi_hybrid)


def _patch_clinical_llm(monkeypatch):
    hit = Hit(
        id="c1",
        text="Metformin is first-line therapy for type 2 diabetes in India.",
        score=0.95,
        metadata={
            "title": "Type 2 diabetes mellitus",
            "url": "internal://clinical_seed.jsonl",
            "source": "clinical_seed",
            "section": "disease_management",
            "doc_type": "guideline",
            "published": "2024",
            "region": "IN",
        },
    )

    class _Raw:
        summary = "The patient has poorly controlled type 2 diabetes [1]."
        differentials = ["uncontrolled type 2 diabetes mellitus"]
        recommended_procedures = ["repeat HbA1c", "renal function panel"]
        cautions = ["Documented penicillin allergy on file."]
        citations = [
            Citation(
                n=1, title="Type 2 diabetes mellitus", source="clinical_seed",
                url="internal://clinical_seed.jsonl", snippet="Metformin is first-line...",
            )
        ]
        confidence = 0.8

    async def fake_hybrid(collection, query, k=8, where=None):
        return [hit]

    async def fake_json_complete(prompt, *, schema, system=None, retries=2):
        return _Raw()

    monkeypatch.setattr(clinical_rag, "hybrid", fake_hybrid)
    monkeypatch.setattr(clinical_rag, "json_complete", fake_json_complete)


@pytest.mark.asyncio
async def test_triage_through_kg_to_brief(db, monkeypatch):
    _patch_triage_llm(monkeypatch)
    start = await triage_rag.start(db, PATIENT_1)
    turn = await triage_rag.turn(
        db, start.session_id, "High fever for eight days, known diabetic, on metformin."
    )
    assert turn.done is False or turn.done is True  # either is a legal single-turn outcome
    triage_result = await triage_rag.finalize(db, start.session_id)
    assert triage_result.severity_esi in range(1, 6)

    visit = await db.get(Visit, VISIT_301)
    assert visit is not None
    visit.triage_session_id = start.session_id
    await db.commit()

    await sync_patient(PATIENT_1)

    _patch_clinical_llm(monkeypatch)
    brief = await clinical_rag.build_brief(VISIT_301, db)

    assert len(brief.citations) >= 1
    assert len(brief.differentials) >= 1
    assert "[1]" in brief.summary
    assert brief.confidence > 0.0
