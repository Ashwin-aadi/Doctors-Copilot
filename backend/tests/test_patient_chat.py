"""Patient chatbot tests.

Retrieval, the LLM and the database are all substituted, so these run offline.
What they pin down is the behaviour that actually protects a patient: no dose
advice, no reading someone else's records, no doctor-facing clinical corpus,
plain-language Indian copy, and a closing line pointing back at the doctor.
"""

from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.deps import CurrentUser, get_current_user
from app.db.models.patient import Patient
from app.db.session import get_db
from app.main import app
from app.rag import guardrails, patient_chat
from app.rag.store import Hit


def _patient(name: str = "Ramesh Kumar") -> Patient:
    return Patient(
        id=uuid4(),
        user_id=uuid4(),
        name=name,
        conditions=[],
        allergies=[],
        medications=[],
    )


class _FakeDb:
    """Only `_active_queue_entry` touches the DB on this path."""

    async def execute(self, _stmt):
        class _R:
            def scalar_one_or_none(self):
                return None

        return _R()

    async def get(self, _model, _id):
        return None


def _own_record_hits() -> list[Hit]:
    return [
        Hit(
            id="own1",
            text="Your creatinine result was 1.9 mg/dL, which is higher than the usual range.",
            score=0.9,
            metadata={
                "title": "Your creatinine result",
                "source": "doctors-copilot",
                "url": "",
                "doc_type": "patient_lab",
            },
        ),
        Hit(
            id="lay1",
            text=(
                "Creatinine is a waste product your muscles make. Healthy kidneys "
                "filter it out into the urine."
            ),
            score=0.8,
            metadata={
                "title": "What creatinine and eGFR mean",
                "source": "Doctor's Copilot patient guide",
                "url": "https://medlineplus.gov",
                "doc_type": "lay",
            },
        ),
    ]


def _patch_pipeline(monkeypatch, *, generated: str, collections: list | None = None):
    async def _fake_hybrid(collection, query, k=8, where=None):
        if collections is not None:
            collections.append(collection)
        if collection.startswith("patient_"):
            return _own_record_hits()[:1]
        return _own_record_hits()[1:]

    async def _fake_complete(prompt, *, system=None, max_tokens=1024, temperature=0.2):
        return generated

    monkeypatch.setattr(patient_chat, "hybrid", _fake_hybrid)
    monkeypatch.setattr(patient_chat, "complete", _fake_complete)
    # Keep faithfulness deterministic without downloading a cross-encoder.
    monkeypatch.setattr(guardrails, "_score_sentences", lambda text, hits: None)


# ------------------------------------------------------------ safety rules


@pytest.mark.parametrize(
    "message",
    [
        "should i stop my metformin?",
        "Can I take a double dose of paracetamol tonight?",
        "How many tablets of amoxicillin should I take?",
        "Please prescribe something for my fever",
        "should i increase my dose of insulin",
    ],
)
@pytest.mark.asyncio
async def test_dose_change_request_is_refused(monkeypatch, message):
    _patch_pipeline(monkeypatch, generated="should never be reached")

    text, citations, confidence = await patient_chat.answer(_FakeDb(), _patient(), message)

    assert "cannot advise you to start, stop or change any medicine" in text
    assert citations == []
    # The refusal must still route an unwell patient somewhere useful.
    assert "doctor" in text and "112" in text


@pytest.mark.asyncio
async def test_benign_question_is_not_treated_as_a_dose_request(monkeypatch):
    _patch_pipeline(
        monkeypatch,
        generated="Your creatinine is a little high [1]. Creatinine comes from muscles [2].",
    )
    text, _, _ = await patient_chat.answer(
        _FakeDb(), _patient(), "what does my high creatinine mean?"
    )
    assert "cannot advise you to start" not in text


@pytest.mark.asyncio
async def test_scope_refusal_marker_is_passed_through(monkeypatch):
    _patch_pipeline(
        monkeypatch,
        generated="SCOPE_REFUSAL I can only help with your own reports and general health information.",
    )
    text, citations, _ = await patient_chat.answer(
        _FakeDb(), _patient(), "who won the cricket match yesterday?"
    )
    assert text.startswith(guardrails.SCOPE_REFUSAL_MARKER)
    assert citations == []


@pytest.mark.asyncio
async def test_clinical_collection_is_never_queried(monkeypatch):
    seen: list[str] = []
    _patch_pipeline(monkeypatch, generated="Your creatinine is high [1].", collections=seen)

    await patient_chat.answer(_FakeDb(), _patient(), "what does my high creatinine mean?")

    assert "clinical" not in seen
    assert any(c.startswith("patient_") for c in seen)
    assert "lay" in seen


@pytest.mark.asyncio
async def test_answer_always_closes_by_pointing_at_the_doctor(monkeypatch):
    _patch_pipeline(monkeypatch, generated="Your creatinine is higher than usual [1].")
    text, _, _ = await patient_chat.answer(_FakeDb(), _patient(), "explain my creatinine")
    assert "doctor" in text.lower()


@pytest.mark.asyncio
async def test_fabricated_citation_is_stripped_from_the_answer(monkeypatch):
    _patch_pipeline(
        monkeypatch,
        generated=(
            "Your creatinine is higher than usual [1]. "
            "Kidney failure is certain within a month [9]."
        ),
    )
    text, _, _ = await patient_chat.answer(_FakeDb(), _patient(), "explain my creatinine")

    assert "Kidney failure is certain" not in text
    assert "[9]" not in text


@pytest.mark.asyncio
async def test_no_retrieval_hits_yields_zero_confidence(monkeypatch):
    async def _empty(collection, query, k=8, where=None):
        return []

    monkeypatch.setattr(patient_chat, "hybrid", _empty)

    text, citations, confidence = await patient_chat.answer(
        _FakeDb(), _patient(), "what does my report say?"
    )
    assert confidence == 0.0
    assert citations == []
    assert "could not find anything in your records" in text


@pytest.mark.asyncio
async def test_emergency_question_gets_the_emergency_banner(monkeypatch):
    _patch_pipeline(monkeypatch, generated="Your creatinine is higher than usual [1].")

    text, _, _ = await patient_chat.answer(
        _FakeDb(), _patient(), "I have chest pain and I am sweating, what should I do?"
    )

    assert text.startswith(guardrails.EMERGENCY_BANNER)
    assert "112" in text and "108" in text
    assert "911" not in text


@pytest.mark.asyncio
async def test_patient_name_is_never_sent_to_the_llm(monkeypatch):
    captured: dict = {}

    async def _fake_hybrid(collection, query, k=8, where=None):
        return _own_record_hits()[:1]

    async def _fake_complete(prompt, *, system=None, max_tokens=1024, temperature=0.2):
        captured["prompt"] = prompt
        return "Your creatinine is higher than usual [1]."

    monkeypatch.setattr(patient_chat, "hybrid", _fake_hybrid)
    monkeypatch.setattr(patient_chat, "complete", _fake_complete)
    monkeypatch.setattr(guardrails, "_score_sentences", lambda text, hits: None)

    await patient_chat.answer(_FakeDb(), _patient("Sunita Devi"), "explain my creatinine")

    assert "Sunita Devi" not in captured["prompt"]


@pytest.mark.asyncio
async def test_chat_stream_emits_token_citation_and_done(monkeypatch):
    _patch_pipeline(monkeypatch, generated="Your creatinine is higher than usual [1].")

    events = [
        event async for event in patient_chat.chat_stream(_FakeDb(), _patient(), "my creatinine?")
    ]
    kinds = [event["event"] for event in events]

    assert kinds[0] == "token"
    assert kinds[-1] == "done"
    assert "citation" in kinds
    assert 0.0 <= events[-1]["data"]["confidence"] <= 1.0


# --------------------------------------------------------------- API layer


@pytest.mark.asyncio
async def test_cross_patient_read_is_forbidden(monkeypatch):
    """A patient asking about somebody else's id gets a 403, not their data."""

    me = _patient()
    someone_else = uuid4()

    async def _override_user():
        return CurrentUser(id=me.user_id, role="patient")

    async def _override_db():
        yield _FakeDb()

    async def _fake_resolve(_db, user_id):
        return me if user_id == me.user_id else None

    monkeypatch.setattr("app.api.v1.chat.resolve_patient_for_user", _fake_resolve)
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat/patient",
                json={"message": "show me the report", "patient_id": str(someone_else)},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_FORBIDDEN"


@pytest.mark.asyncio
async def test_anonymous_caller_is_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/chat/patient", json={"message": "hello"})

    assert response.status_code == 401
    assert response.json()["error"]["code"].startswith("AUTH")


@pytest.mark.asyncio
async def test_sse_stream_is_event_stream_content_type(monkeypatch):
    me = _patient()
    _patch_pipeline(monkeypatch, generated="Your creatinine is higher than usual [1].")

    async def _override_user():
        return CurrentUser(id=me.user_id, role="patient")

    async def _override_db():
        yield _FakeDb()

    async def _fake_resolve(_db, _user_id):
        return me

    monkeypatch.setattr("app.api.v1.chat.resolve_patient_for_user", _fake_resolve)
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat/patient", json={"message": "what does my creatinine mean?"}
            )
            body = response.text
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: token" in body
    assert "event: done" in body


def test_patient_collection_name_is_per_patient():
    pid = UUID("00000000-0000-0000-0000-000000000101")
    from app.rag.ingest_patient import patient_collection

    assert patient_collection(pid) == f"patient_{pid}"
