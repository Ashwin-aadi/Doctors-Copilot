from uuid import UUID

import pytest

from app.ml import summary as summary_module
from app.ml.schemas_ml import SummaryRequest
from app.schemas.ml import SoapSummary

SEEDED_PATIENT_ID = UUID("00000000-0000-0000-0000-000000000101")
SEEDED_VISIT_ID = UUID("00000000-0000-0000-0000-000000000301")


@pytest.mark.asyncio
async def test_build_summary_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_json_complete(prompt: str, *, schema, **kwargs):  # noqa: ARG001
        return SoapSummary(
            subjective="Patient reports fatigue and thirst consistent with the recorded history [1].",
            objective="HbA1c 9.2% is high against the reference range [2].",
            assessment="Differential includes poorly controlled diabetes given the HbA1c result.",
            plan="Recommend follow-up glucose monitoring and dietary counselling.",
            citations=[],
            confidence=0.0,
        )

    monkeypatch.setattr(summary_module, "json_complete", fake_json_complete)

    result = await summary_module.build_summary(
        SummaryRequest(patient_id=SEEDED_PATIENT_ID, visit_id=SEEDED_VISIT_ID)
    )

    assert len(result.subjective) > 20
    assert len(result.objective) > 20
    assert len(result.assessment) > 10
    assert len(result.plan) > 10
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_build_summary_strips_hallucinated_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_json_complete(prompt: str, *, schema, **kwargs):  # noqa: ARG001
        return SoapSummary(
            subjective="Patient reports fatigue [1].",
            # 42.7 never appears anywhere in the assembled context -- must be dropped.
            objective="HbA1c 9.2% is high [2]. The patient's temperature was 42.7 degrees.",
            assessment="Differential includes poorly controlled diabetes.",
            plan="Follow up in two weeks.",
            citations=[],
            confidence=0.0,
        )

    monkeypatch.setattr(summary_module, "json_complete", fake_json_complete)

    result = await summary_module.build_summary(
        SummaryRequest(patient_id=SEEDED_PATIENT_ID, visit_id=SEEDED_VISIT_ID)
    )

    assert "42.7" not in result.objective
    assert "9.2" in result.objective


def test_strip_hallucinated_numbers_keeps_grounded_sentences() -> None:
    context_numbers = {"9.2", "1"}
    text = "HbA1c is 9.2 percent [1]. The patient is 42 years old."
    stripped = summary_module._strip_hallucinated_numbers(text, context_numbers)
    assert "9.2" in stripped
    assert "42" not in stripped


def test_endemic_differentials_dengue_from_fever_and_low_platelets() -> None:
    from unittest.mock import MagicMock

    lab = MagicMock()
    lab.normalized_name = "platelet_count"
    lab.flag = "low"

    matches = summary_module._endemic_differentials("high fever and joint pain", [lab])
    assert "dengue" in matches
