import pytest

from app.ml.ner import brand_to_generic, extract
from app.ml.registry import get_registry


@pytest.mark.asyncio
async def test_extract_drugs_conditions_negation_historical_allergy() -> None:
    bundle = await extract(
        "Patient denies chest pain. History of type 2 diabetes. "
        "On metformin 500 mg BD and aspirin 75 mg OD. Allergic to penicillin."
    )
    drug_names = {e.text.lower() for e in bundle.drugs}
    assert {"metformin", "aspirin"} <= drug_names
    assert any(e.negated for e in bundle.conditions)
    assert any(e.historical for e in bundle.conditions)
    assert any("penicillin" in e.text.lower() for e in bundle.allergens)


@pytest.mark.asyncio
async def test_dose_extraction() -> None:
    bundle = await extract("Started on aspirin 75 mg OD for secondary prevention.")
    aspirin = next(e for e in bundle.drugs if e.text.lower() == "aspirin")
    assert aspirin.dose is not None
    assert aspirin.dose.amount == 75
    assert aspirin.dose.unit == "mg"
    assert aspirin.dose.frequency == "OD"


@pytest.mark.asyncio
async def test_allergen_not_double_counted_as_drug() -> None:
    bundle = await extract("Allergic to penicillin. No known drug allergies otherwise.")
    drug_names = {e.text.lower() for e in bundle.drugs}
    assert "penicillin" not in drug_names


def test_brand_to_generic_resolves_indian_brands() -> None:
    assert brand_to_generic("Crocin") == "paracetamol"
    assert brand_to_generic("Glycomet") == "metformin"
    assert brand_to_generic("Augmentin") == "amoxicillin"


def test_brand_to_generic_passthrough_for_unknown() -> None:
    assert brand_to_generic("SomeUnknownBrandXYZ") == "someunknownbrandxyz"


@pytest.mark.asyncio
async def test_negation_and_historical_work_without_scispacy_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: CI has no en_core_sci_sm/en_ner_bc5cdr_md model data
    downloaded, so extract() falls back to the gazetteer tier. Negation and
    historical classification must still work there -- they used to depend
    on a spaCy Doc for token windows and silently no-op when neither
    scispaCy model loaded.
    """
    registry = get_registry()
    monkeypatch.setattr(registry, "bc5cdr", lambda: None)
    monkeypatch.setattr(registry, "sci_nlp", lambda: None)

    bundle = await extract(
        "Patient denies diabetes. History of asthma. On metformin 500 mg BD."
    )
    assert bundle.ner_tier == "gazetteer"
    by_text = {e.text.lower(): e for e in bundle.conditions}
    assert by_text["diabetes"].negated is True
    assert by_text["asthma"].negated is False
    assert by_text["asthma"].historical is True
