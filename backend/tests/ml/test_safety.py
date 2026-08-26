import pytest

from app.ml.safety import _allergy_conflict, check_interactions
from app.ml.schemas_ml import InteractionRequest


@pytest.mark.asyncio
async def test_warfarin_aspirin_major_interaction_with_url() -> None:
    report = await check_interactions(
        InteractionRequest(medications=["warfarin", "aspirin", "amoxicillin"])
    )
    assert len(report.pairs) >= 1
    top = report.pairs[0]
    assert top.severity == "major"
    assert top.url


@pytest.mark.asyncio
async def test_penicillin_amoxicillin_allergy_conflict() -> None:
    report = await check_interactions(
        InteractionRequest(medications=["amoxicillin"], allergies=["penicillin"])
    )
    assert len(report.allergy_conflicts) >= 1
    assert report.allergy_conflicts[0].drug == "amoxicillin"


@pytest.mark.asyncio
async def test_full_request_shape() -> None:
    report = await check_interactions(
        InteractionRequest(
            medications=["warfarin", "aspirin", "amoxicillin"],
            allergies=["penicillin"],
            conditions=["peptic ulcer"],
        )
    )
    assert report.pairs[0].severity == "major"
    assert len(report.allergy_conflicts) >= 1
    assert report.pairs[0].url


def test_allergy_conflict_direct_match() -> None:
    conflict = _allergy_conflict("penicillin", "penicillin")
    assert conflict is not None


def test_allergy_conflict_none_when_unrelated() -> None:
    assert _allergy_conflict("peanut", "metformin") is None


@pytest.mark.asyncio
async def test_no_interaction_for_unrelated_drugs() -> None:
    report = await check_interactions(InteractionRequest(medications=["paracetamol"]))
    assert report.pairs == []
