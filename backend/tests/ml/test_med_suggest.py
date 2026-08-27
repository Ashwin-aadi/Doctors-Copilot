import pytest

from app.ml.med_suggest import suggest_medications
from app.ml.schemas_ml import MedSuggestRequest


@pytest.mark.asyncio
async def test_diabetes_suggestions_exclude_amoxicillin_and_carry_source() -> None:
    candidates = await suggest_medications(
        MedSuggestRequest(
            conditions=["type 2 diabetes"],
            current_medications=["warfarin"],
            allergies=["penicillin"],
        )
    )
    assert len(candidates) >= 3
    names = {c.name.lower() for c in candidates}
    assert "amoxicillin" not in names
    assert candidates[0].source_url

    for candidate in candidates:
        assert "decision support requiring doctor approval" in candidate.rationale.lower()


@pytest.mark.asyncio
async def test_no_candidates_for_unknown_condition() -> None:
    candidates = await suggest_medications(
        MedSuggestRequest(conditions=["xyzzyplotomycosis nonexistentiasis"])
    )
    assert candidates == []


@pytest.mark.asyncio
async def test_candidates_sorted_by_indication_match_desc() -> None:
    candidates = await suggest_medications(MedSuggestRequest(conditions=["diabetes"]))
    scores = [c.indication_match for c in candidates]
    assert scores == sorted(scores, reverse=True)
