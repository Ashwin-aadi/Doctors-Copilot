"""Guardrail pass tests. No DB, no network, no model download: the
cross-encoder is monkeypatched so faithfulness scoring is deterministic and
the suite runs offline in CI.
"""

import pytest

from app.rag import guardrails
from app.rag.store import Hit


def _hits() -> list[Hit]:
    return [
        Hit(
            id="h1",
            text="Dengue fever commonly causes a fall in the platelet count.",
            score=0.9,
            metadata={"title": "Dengue", "source": "MedlinePlus", "url": "https://x/1"},
        ),
        Hit(
            id="h2",
            text="Paracetamol is used to bring down fever and relieve pain.",
            score=0.8,
            metadata={"title": "Paracetamol", "source": "MedlinePlus", "url": "https://x/2"},
        ),
    ]


def _patch_scorer(monkeypatch, scores):
    """Force `_score_sentences` scoring by replacing the cross-encoder with a
    stub whose `predict` returns pre-set logits, one per scored pair."""

    class _Stub:
        def __init__(self, values):
            self._values = list(values)

        def predict(self, pairs):
            assert len(pairs) <= len(self._values), "more pairs than stubbed scores"
            return self._values[: len(pairs)]

    guardrails._cross_encoder.cache_clear()
    monkeypatch.setattr(guardrails, "_cross_encoder", lambda: _Stub(scores))


# ------------------------------------------------------------------ pass 1


def test_redact_pii_strips_phone_email_abha_and_uuid():
    text = (
        "Patient Ramesh Kumar, phone +91 98765 43210 no wait 9876543210, "
        "email ramesh.kumar@example.in, ABHA 12-3456-7890-1234, "
        "record 3fa85f64-5717-4562-b3fc-2c963f66afa6."
    )
    redacted, mapping = guardrails.redact_pii(text, names=["Ramesh Kumar"])

    assert "Ramesh Kumar" not in redacted
    assert "9876543210" not in redacted
    assert "ramesh.kumar@example.in" not in redacted
    assert "3fa85f64-5717-4562-b3fc-2c963f66afa6" not in redacted
    assert "12-3456-7890-1234" not in redacted
    assert "<NAME_1>" in redacted


def test_redact_pii_restores_original_values():
    text = "Contact Priya Sharma on 9812345678 or priya@example.in."
    redacted, mapping = guardrails.redact_pii(text, names=["Priya Sharma"])
    assert mapping.restore(redacted) == text


def test_redacted_prompt_is_what_reaches_the_llm(monkeypatch):
    """PII fixture must be absent from the captured LLM payload."""

    captured: dict = {}

    original = guardrails.redact_pii

    def _spy(text, *, names=None):
        redacted, mapping = original(text, names=names)
        captured["payload"] = redacted
        return redacted, mapping

    monkeypatch.setattr(guardrails, "redact_pii", _spy)

    redacted, _ = guardrails.redact_pii(
        "Ask Anita Desai (9876501234, anita@example.in) about her report.",
        names=["Anita Desai"],
    )
    assert "Anita Desai" not in captured["payload"]
    assert "9876501234" not in captured["payload"]
    assert "anita@example.in" not in captured["payload"]


def test_redact_pii_reuses_one_placeholder_per_value():
    text = "Call 9876501234. If no answer, call 9876501234 again."
    redacted, mapping = guardrails.redact_pii(text)
    assert redacted.count("<PHONE_1>") == 2
    assert len(mapping.values) == 1


# ------------------------------------------------------------------ pass 2


def test_validate_citations_strips_fabricated_citation():
    text = (
        "Dengue lowers the platelet count [1]. "
        "A weekly injection cures dengue in two days [7]. "
        "Paracetamol brings down fever [2]."
    )
    cleaned = guardrails.validate_citations(text, _hits())

    assert "[7]" not in cleaned
    assert "weekly injection" not in cleaned
    assert "[1]" in cleaned and "[2]" in cleaned


def test_validate_citations_keeps_uncited_sentences():
    text = "Please discuss this with your doctor. Dengue lowers platelets [1]."
    cleaned = guardrails.validate_citations(text, _hits())
    assert "discuss this with your doctor" in cleaned


def test_validate_citations_drops_sentence_with_any_bad_marker():
    text = "Dengue lowers platelets [1][9]."
    assert guardrails.validate_citations(text, _hits()) == ""


# ------------------------------------------------------------------ pass 3


def test_faithfulness_returns_zero_when_nothing_is_cited(monkeypatch):
    _patch_scorer(monkeypatch, [])
    assert guardrails.faithfulness("No citations at all here.", _hits()) == 0.0


def test_filter_unfaithful_drops_low_scoring_sentence(monkeypatch):
    # Logits -> sigmoid: +4.0 ~ 0.98 (kept), -4.0 ~ 0.018 (below the 0.35 floor).
    _patch_scorer(monkeypatch, [4.0, -4.0])
    text = "Dengue lowers the platelet count [1]. Paracetamol cures dengue [2]."

    cleaned, confidence = guardrails.filter_unfaithful(text, _hits())

    assert "Paracetamol cures dengue" not in cleaned
    assert "Dengue lowers the platelet count" in cleaned
    assert confidence > guardrails.FAITHFULNESS_FLOOR


def test_filter_unfaithful_zero_confidence_when_all_sentences_dropped(monkeypatch):
    _patch_scorer(monkeypatch, [-5.0, -5.0])
    cleaned, confidence = guardrails.filter_unfaithful(
        "Claim one [1]. Claim two [2].", _hits()
    )
    assert confidence == 0.0
    assert cleaned.strip() == ""


def test_scorer_failure_keeps_text_at_the_floor(monkeypatch):
    class _Broken:
        def predict(self, pairs):
            raise RuntimeError("model not downloaded")

    guardrails._cross_encoder.cache_clear()
    monkeypatch.setattr(guardrails, "_cross_encoder", lambda: _Broken())

    text = "Dengue lowers the platelet count [1]."
    cleaned, confidence = guardrails.filter_unfaithful(text, _hits())

    assert cleaned == text
    assert confidence == guardrails.FAITHFULNESS_FLOOR


def test_apply_all_runs_citation_then_faithfulness(monkeypatch):
    _patch_scorer(monkeypatch, [4.0])
    text = "Dengue lowers platelets [1]. Fabricated claim [8]."
    cleaned, confidence = guardrails.apply_all(text, _hits())

    assert "Fabricated claim" not in cleaned
    assert "Dengue lowers platelets" in cleaned
    assert 0.0 < confidence <= 1.0


# ------------------------------------------------------------------ pass 4


@pytest.mark.asyncio
async def test_emergency_intercept_passes_through_non_emergency():
    text, escalated = await guardrails.emergency_intercept(
        severity_esi=4, red_flags=[], text="Your report looks stable."
    )
    assert escalated is False
    assert guardrails.EMERGENCY_BANNER not in text


@pytest.mark.asyncio
async def test_emergency_intercept_banners_low_esi():
    text, escalated = await guardrails.emergency_intercept(
        severity_esi=2, text="Your report shows a low platelet count."
    )
    assert text.startswith(guardrails.EMERGENCY_BANNER)
    assert "112" in text and "108" in text
    assert escalated is False  # no queue entry supplied


@pytest.mark.asyncio
async def test_emergency_intercept_banners_red_flag_without_esi():
    text, _ = await guardrails.emergency_intercept(
        severity_esi=None, red_flags=["coughing blood"], text="Body text."
    )
    assert guardrails.EMERGENCY_BANNER in text


@pytest.mark.asyncio
async def test_emergency_intercept_escalates_queue_entry(monkeypatch):
    from uuid import uuid4

    entry_id = uuid4()
    called: dict = {}

    async def _fake_escalate(eid, reason, *, now):
        called["entry_id"] = eid
        called["reason"] = reason
        return None

    import app.services.queueing.escalation as escalation

    monkeypatch.setattr(escalation, "escalate_with_referral", _fake_escalate)

    text, escalated = await guardrails.emergency_intercept(
        severity_esi=1, red_flags=["chest pain"], queue_entry_id=entry_id, text="Body."
    )

    assert escalated is True
    assert called["entry_id"] == entry_id
    assert called["reason"] == "chest pain"


@pytest.mark.asyncio
async def test_emergency_banner_survives_escalation_failure(monkeypatch):
    from uuid import uuid4

    async def _boom(eid, reason, *, now):
        raise RuntimeError("queue service down")

    import app.services.queueing.escalation as escalation

    monkeypatch.setattr(escalation, "escalate_with_referral", _boom)

    text, escalated = await guardrails.emergency_intercept(
        severity_esi=1, queue_entry_id=uuid4(), text="Body."
    )

    assert escalated is False
    assert guardrails.EMERGENCY_BANNER in text
