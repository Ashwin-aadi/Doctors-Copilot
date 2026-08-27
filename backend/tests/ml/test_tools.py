import inspect
from uuid import uuid4

import pytest

from app.ml import tools
from app.ml.schemas_ml import EntityBundle, MedSuggestRequest, SummaryRequest
from app.schemas.ml import SoapSummary


def test_all_tool_functions_are_coroutines() -> None:
    for name in (
        "extract_entities",
        "check_interactions",
        "flag_labs",
        "suggest_medications",
        "build_summary",
    ):
        assert inspect.iscoroutinefunction(getattr(tools, name)), name


def test_tool_schemas_cover_required_tools() -> None:
    assert set(tools.TOOL_SCHEMAS) >= {"check_interactions", "flag_labs"}


@pytest.mark.asyncio
async def test_extract_entities_never_raises_on_dependency_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(text: str):  # noqa: ARG001
        raise RuntimeError("ner pipeline down")

    monkeypatch.setattr(tools, "_extract_entities_impl", boom)
    result = await tools.extract_entities("aspirin 75 mg")
    assert isinstance(result, EntityBundle)
    assert result.drugs == []


@pytest.mark.asyncio
async def test_check_interactions_matches_tool_bridge_call_convention() -> None:
    result = await tools.check_interactions(uuid4(), ["warfarin", "aspirin"])
    assert isinstance(result, dict)
    assert {"pairs", "allergy_conflicts", "contraindications"} <= set(result)
    assert len(result["pairs"]) >= 1


@pytest.mark.asyncio
async def test_check_interactions_typed_empty_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(req):  # noqa: ARG001
        raise RuntimeError("db down")

    monkeypatch.setattr(tools, "_check_interactions_impl", boom)
    result = await tools.check_interactions(uuid4(), ["warfarin"])
    assert result == {"pairs": [], "allergy_conflicts": [], "contraindications": []}


@pytest.mark.asyncio
async def test_flag_labs_matches_tool_bridge_call_convention() -> None:
    labs = [{"test_name": "Creatinine", "normalized_name": "creatinine", "value": 3.1, "unit": "mg/dL"}]
    result = await tools.flag_labs(uuid4(), labs)
    assert isinstance(result, list)
    assert result[0]["flag"] in ("critical", "high")


@pytest.mark.asyncio
async def test_flag_labs_typed_empty_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(db, patient_id, results):  # noqa: ARG001
        raise RuntimeError("db down")

    monkeypatch.setattr(tools, "_flag_labs_impl", boom)
    result = await tools.flag_labs(uuid4(), [{"test_name": "Hb", "value": 12.0}])
    assert result == []


@pytest.mark.asyncio
async def test_suggest_medications_typed_empty_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(req):  # noqa: ARG001
        raise RuntimeError("kb down")

    monkeypatch.setattr(tools, "_suggest_medications_impl", boom)
    result = await tools.suggest_medications(MedSuggestRequest(conditions=["diabetes"]))
    assert result == []


@pytest.mark.asyncio
async def test_build_summary_typed_empty_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(req):  # noqa: ARG001
        raise RuntimeError("llm down")

    monkeypatch.setattr(tools, "_build_summary_impl", boom)
    result = await tools.build_summary(SummaryRequest(patient_id=uuid4(), visit_id=uuid4()))
    assert isinstance(result, SoapSummary)
    assert result.subjective == ""
