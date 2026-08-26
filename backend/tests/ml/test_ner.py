import pytest

from app.ml.ner import brand_to_generic, extract


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
