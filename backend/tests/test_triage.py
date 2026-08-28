"""Unit/integration tests for the A1.4 pre-assessment triage RAG flow.

LLM calls are monkeypatched so these tests are deterministic and do not require
a configured GROQ_API_KEY or network access. Requires a reachable Postgres per
DATABASE_URL (the same database migrations run against).
"""

import pytest
import pytest_asyncio

from app.db.session import SessionLocal
from app.rag import triage_rag
from app.rag.store import Hit
from app.schemas.triage import TriageResult, colour_for_esi


@pytest_asyncio.fixture
async def db():
    async with SessionLocal() as session:
        yield session
        await session.rollback()


def _patch_llm(monkeypatch, question: str = "How long has this been going on?"):
    async def fake_complete(prompt, *, system=None, max_tokens=1024, temperature=0.2):
        return question

    async def fake_json_complete(prompt, *, schema, system=None, retries=2):
        return schema()

    async def fake_multi_hybrid(collection, queries, k=10, **kwargs):
        return [
            Hit(
                id="g1",
                text="Chest pain radiating to the arm suggests a cardiac cause.",
                score=0.9,
                metadata={"title": "Chest Pain", "source": "test"},
            )
        ]

    monkeypatch.setattr("app.rag.triage_rag.complete", fake_complete)
    monkeypatch.setattr("app.rag.triage_rag.json_complete", fake_json_complete)
    monkeypatch.setattr("app.rag.patient_state.json_complete", fake_json_complete)
    monkeypatch.setattr("app.rag.triage_rag.multi_hybrid", fake_multi_hybrid)


async def test_start_creates_session_and_asks_one_question(db, monkeypatch):
    _patch_llm(monkeypatch)
    out = await triage_rag.start(db, None)
    assert out.questions_asked == 1
    assert out.done is False
    assert out.assistant


async def test_red_flag_short_circuits_and_finalizes(db, monkeypatch):
    _patch_llm(monkeypatch)
    start_out = await triage_rag.start(db, None)
    turn_out = await triage_rag.turn(
        db, start_out.session_id, "crushing chest pain radiating to left arm, sweating"
    )
    assert turn_out.done is True

    result = await triage_rag.get_result(db, start_out.session_id)
    assert isinstance(result, TriageResult)
    assert result.severity_esi <= 2
    assert result.red_flags
    # An ESI 1-2 patient must show up as red on the casualty board.
    assert result.triage_colour == "red"


async def test_benign_conversation_does_not_trigger_red_flag(db, monkeypatch):
    _patch_llm(monkeypatch)
    start_out = await triage_rag.start(db, None)
    turn_out = await triage_rag.turn(db, start_out.session_id, "mild soreness in my shoulder")
    assert turn_out.done is False
    assert turn_out.questions_asked == 2


async def test_max_questions_caps_conversation(db, monkeypatch):
    _patch_llm(monkeypatch)
    start_out = await triage_rag.start(db, None)
    session_id = start_out.session_id

    done = False
    turns_taken = 0
    for i in range(triage_rag.MAX_QUESTIONS + 2):
        out = await triage_rag.turn(db, session_id, f"answer number {i}, no new symptoms")
        turns_taken += 1
        if out.done:
            done = True
            break

    assert done is True
    assert turns_taken <= triage_rag.MAX_QUESTIONS
    result = await triage_rag.get_result(db, session_id)
    assert result.session_id == session_id


def test_regex_red_flag_detects_known_patterns():
    assert triage_rag._regex_red_flag("crushing chest pain radiating to the left arm")
    assert triage_rag._regex_red_flag("worst headache of my life")
    assert triage_rag._regex_red_flag("suicidal thoughts")
    assert triage_rag._regex_red_flag("mild stomach ache for two days") is None


@pytest.mark.parametrize(
    "statement",
    [
        # Phrased the way patients actually phrase it, in varying word order —
        # the earlier patterns required a fixed "X with fever" form and missed these.
        "day 5 of fever, now bleeding gums and severe abdominal pain",
        "my gums are bleeding since morning",
        "black stools this morning",
        "persistent vomiting for two days",
        "vomiting blood",
        "snakebite while working in the field",
        "drooping eyelid and cannot swallow properly",
        "he consumed pesticide an hour ago",
        "frothing at the mouth",
        "neck stiffness with fever",
        "convulsions with fever in my child",
        "heavy bleeding in pregnancy",
        "dog bite on the hand",
    ],
)
def test_regex_red_flag_detects_india_prevalent_emergencies(statement):
    assert triage_rag._regex_red_flag(statement) is not None


@pytest.mark.parametrize(
    "statement",
    [
        "mild stomach ache for two days",
        "slight bleeding from a cut on my finger",
        "routine follow up for blood pressure",
        "i have a mild cough and runny nose",
        "vomited once last night, feeling better now",
    ],
)
def test_regex_red_flag_does_not_over_fire_on_benign_statements(statement):
    assert triage_rag._regex_red_flag(statement) is None


@pytest.mark.parametrize(
    ("esi", "colour"),
    [(1, "red"), (2, "red"), (3, "yellow"), (4, "green"), (5, "green")],
)
def test_esi_maps_to_mohfw_casualty_colour(esi, colour):
    assert colour_for_esi(esi) == colour


async def test_finalize_result_not_found_before_finalizing(db, monkeypatch):
    _patch_llm(monkeypatch)
    start_out = await triage_rag.start(db, None)
    from app.core.errors import ApiError

    with pytest.raises(ApiError):
        await triage_rag.get_result(db, start_out.session_id)
