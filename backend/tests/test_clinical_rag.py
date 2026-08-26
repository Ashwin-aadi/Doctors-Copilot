"""Exercises the guardrail behaviour of clinical_rag.build_brief without
requiring live Postgres/Neo4j/Chroma/LLM: the DB/session dependency and the
retrieval + LLM calls are monkeypatched, so this runs offline in CI.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.db.models.clinical import Visit
from app.rag import clinical_rag
from app.rag.store import Hit
from app.schemas.copilot import CopilotBrief


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, visit, patient, labs):
        self._visit = visit
        self._patient = patient
        self._labs = labs

    async def get(self, model, id_):
        if model is Visit:
            return self._visit if id_ == self._visit.id else None
        from app.db.models.patient import Patient

        if model is Patient:
            return self._patient if id_ == self._patient.id else None
        return None

    async def execute(self, _stmt):
        return _FakeResult(self._labs)


def _make_visit(patient_id: UUID) -> Visit:
    return Visit(
        id=uuid4(),
        patient_id=patient_id,
        doctor_id=None,
        state="RESULTS_UPLOADED",
        triage_session_id=None,
        lab_order_id=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_zero_retrieval_hits_yields_zero_confidence(monkeypatch):
    from app.db.models.patient import Patient

    patient = Patient(id=uuid4(), user_id=uuid4(), name="Test Patient", conditions=[], allergies=[], medications=[])
    visit = _make_visit(patient.id)
    db = _FakeSession(visit, patient, labs=[])

    async def _empty_context(_pid):
        return {"conditions": [], "medications": [], "allergies": [], "recent_labs": []}

    monkeypatch.setattr(clinical_rag, "patient_context", _empty_context)
    monkeypatch.setattr(clinical_rag, "hybrid", lambda *a, **k: _async_return([]))
    monkeypatch.setattr(clinical_rag, "flag_labs", lambda *a, **k: _async_return([]))

    brief = await clinical_rag.build_brief(visit.id, db)
    assert isinstance(brief, CopilotBrief)
    assert brief.confidence == 0.0
    assert brief.citations == []


@pytest.mark.asyncio
async def test_unresolvable_citation_is_stripped_from_summary(monkeypatch):
    from app.db.models.patient import Patient
    from app.schemas.common import Citation

    patient = Patient(id=uuid4(), user_id=uuid4(), name="Test Patient", conditions=[], allergies=[], medications=[])
    visit = _make_visit(patient.id)
    db = _FakeSession(visit, patient, labs=[])

    hit = Hit(
        id="h1",
        text="Metformin is first-line therapy for type 2 diabetes.",
        score=0.9,
        metadata={
            "title": "Metformin guideline",
            "url": "internal://seed",
            "source": "seed",
            "section": "pharmacology",
            "doc_type": "guideline",
            "published": "2024",
            "region": "IN",
        },
    )

    async def _one_context(_pid):
        return {"conditions": [], "medications": [], "allergies": [], "recent_labs": []}

    class _RawBrief:
        summary = "Metformin is first-line [1]. This unsupported claim cites a phantom source [7]."
        differentials = ["type 2 diabetes"]
        recommended_procedures = ["HbA1c"]
        cautions = ["Fabricated caution citing nothing real [7]."]
        citations = [
            Citation(n=1, title="Metformin guideline", source="seed", url="internal://seed", snippet="..."),
            Citation(n=7, title="Nonexistent Source", source="seed", url="internal://nope", snippet="..."),
        ]
        confidence = 0.8

    monkeypatch.setattr(clinical_rag, "patient_context", _one_context)
    monkeypatch.setattr(clinical_rag, "hybrid", lambda *a, **k: _async_return([hit]))
    monkeypatch.setattr(clinical_rag, "flag_labs", lambda *a, **k: _async_return([]))

    async def _fake_json_complete(*a, **k):
        return _RawBrief()

    monkeypatch.setattr(clinical_rag, "json_complete", _fake_json_complete)

    brief = await clinical_rag.build_brief(visit.id, db)
    assert "[7]" not in brief.summary
    assert "[7]" not in " ".join(brief.cautions)
    assert len(brief.citations) == 1
    assert brief.citations[0].n == 1


async def _async_return(value):
    return value
