"""Safety-gated generic substitution (section 8 N3.4).

The two gates the spec names explicitly get dedicated cases: a
penicillin-allergic patient is never offered amoxicillin, and a fixed-dose
combination (Combiflam) is never replaced by a single ingredient. Both are
asserted through the service rather than only over HTTP, so a failure points
at the rule rather than at the route.
"""

from __future__ import annotations

import datetime as dt
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.core.errors import ApiError
from app.db.models.clinical import Prescription, Visit
from app.db.models.patient import Patient
from app.db.session import SessionLocal
from app.services.mapping import substitution as sub
from app.services.mapping.schemas import GenericProduct
from tests.services.conftest import patient_id

NOW = dt.datetime(2026, 1, 12, 9, 0, tzinfo=dt.UTC)

_CREATED_PRESCRIPTIONS: list[object] = []
_CREATED_VISITS: list[object] = []


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    _CREATED_PRESCRIPTIONS.clear()
    _CREATED_VISITS.clear()
    yield
    async with SessionLocal() as session:
        if _CREATED_PRESCRIPTIONS:
            await session.execute(
                delete(Prescription).where(Prescription.id.in_(_CREATED_PRESCRIPTIONS))
            )
        if _CREATED_VISITS:
            await session.execute(delete(Visit).where(Visit.id.in_(_CREATED_VISITS)))
        await session.commit()
    _CREATED_PRESCRIPTIONS.clear()
    _CREATED_VISITS.clear()


async def _set_patient_history(
    *, patient: int, allergies: list[str], conditions: list[str], medications: list[str]
) -> None:
    async with SessionLocal() as session:
        row = await session.get(Patient, patient_id(patient))
        assert row is not None, "Chennai fixture patient missing"
        row.allergies = allergies
        row.conditions = conditions
        row.medications = medications
        await session.commit()


async def _prescription(*, patient: int, items: list[str], approved: bool = True):
    async with SessionLocal() as session:
        visit = Visit(
            id=uuid4(),
            patient_id=patient_id(patient),
            doctor_id=None,
            state="PRESCRIBED",
            # Visit declares created_at/updated_at with no default, so a
            # hand-built row has to supply them; pinning them to the fixture
            # clock keeps the setup free of wall-clock reads.
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(visit)
        await session.flush()
        rx = Prescription(
            id=uuid4(),
            visit_id=visit.id,
            patient_id=patient_id(patient),
            items=[{"name": name} for name in items],
            approved_by=None,
            locked=False,
        )
        session.add(rx)
        await session.commit()
        _CREATED_VISITS.append(visit.id)
        _CREATED_PRESCRIPTIONS.append(rx.id)
        return rx.id, visit.id


# --- ingredient-set equivalence (local gate, always on) --------------------


def test_ingredient_set_splits_fixed_dose_combinations():
    assert sub.ingredient_set("Ibuprofen + Paracetamol") == {"ibuprofen", "paracetamol"}
    assert sub.ingredient_set("Paracetamol + Ibuprofen") == {"ibuprofen", "paracetamol"}
    assert sub.ingredient_set("Paracetamol") == {"paracetamol"}
    assert sub.ingredient_set(None) == frozenset()


def test_a_combination_is_not_equivalent_to_its_single_ingredients():
    combo = sub.ingredient_set("Ibuprofen + Paracetamol")
    assert combo != sub.ingredient_set("Paracetamol")
    assert combo != sub.ingredient_set("Ibuprofen")


# --- the allergy gate ------------------------------------------------------


def test_block_for_candidate_blocks_on_an_allergy_conflict():
    candidate = GenericProduct(name="Amoxicillin", strength="500mg", form="tablet")
    report = {
        "pairs": [],
        "allergy_conflicts": [
            {
                "allergen": "penicillin",
                "drug": "Amoxicillin",
                "rationale": "beta-lactam cross-reactivity",
                "source": "https://example.org/label",
            }
        ],
        "contraindications": [],
    }
    block = sub._block_for_candidate(candidate, report, current_medications=[])
    assert block is not None
    assert block.severity == "allergy"
    assert "penicillin" in block.reason.lower()


def test_block_for_candidate_blocks_on_a_contraindication():
    candidate = GenericProduct(name="Metformin")
    report = {
        "pairs": [],
        "allergy_conflicts": [],
        "contraindications": [
            {
                "drug": "Metformin",
                "condition": "chronic kidney disease",
                "rationale": "lactic acidosis risk at reduced eGFR",
                "source": "https://example.org/label",
            }
        ],
    }
    block = sub._block_for_candidate(candidate, report, current_medications=[])
    assert block is not None
    assert block.severity == "contraindication"


def test_only_major_interactions_block_and_only_against_current_medications():
    candidate = GenericProduct(name="Warfarin")
    major_with_current = {
        "pairs": [
            {
                "drug_a": "Warfarin",
                "drug_b": "Aspirin",
                "severity": "major",
                "mechanism": "additive bleeding risk",
                "url": "https://example.org/i",
            }
        ],
        "allergy_conflicts": [],
        "contraindications": [],
    }
    assert sub._block_for_candidate(candidate, major_with_current, ["Aspirin"]) is not None
    # the patient is not on aspirin -- nothing to interact with
    assert sub._block_for_candidate(candidate, major_with_current, ["Metformin"]) is None

    moderate = {
        "pairs": [
            {
                "drug_a": "Warfarin",
                "drug_b": "Aspirin",
                "severity": "moderate",
                "mechanism": "monitor INR",
                "url": "https://example.org/i",
            }
        ],
        "allergy_conflicts": [],
        "contraindications": [],
    }
    assert sub._block_for_candidate(candidate, moderate, ["Aspirin"]) is None


# --- end to end through the service ---------------------------------------


@pytest.mark.asyncio
async def test_penicillin_allergic_patient_is_never_offered_amoxicillin():
    """`has_prescribing_rmp=True` deliberately: Augmentin is Schedule H, so
    without a prescriber the H1 gate would block every candidate first and
    this case would pass without the allergy gate ever running. Forcing the
    prescriber present makes the allergy check the only thing standing
    between the patient and an amoxicillin product.
    """
    await _set_patient_history(
        patient=1, allergies=["penicillin"], conditions=[], medications=[]
    )
    rx_id, _visit = await _prescription(patient=1, items=["Augmentin"])

    result = await sub.substitutions_for_prescription(rx_id, has_prescribing_rmp=True)
    assert result

    offered = [o.name.lower() for line in result for o in line.options]
    assert not any("amoxicillin" in name for name in offered), (
        "a penicillin-allergic patient was offered an amoxicillin product"
    )
    # the withholding is explained, not silent, and names the allergy
    blocked = [b for line in result for b in line.blocked]
    assert blocked
    assert all(b.reason for b in blocked)
    assert any(b.severity == "allergy" for b in blocked), (
        "blocked for the wrong reason -- the allergy gate did not fire"
    )


@pytest.mark.asyncio
async def test_a_combination_product_is_screened_by_each_ingredient():
    """Regression: the allergy matcher compares an allergen against one
    generic name, so submitting "Amoxicillin + Clavulanic acid" whole matched
    nothing. Components have to be screened individually.
    """
    await _set_patient_history(
        patient=8, allergies=["penicillin"], conditions=[], medications=[]
    )
    rx_id, _visit = await _prescription(patient=8, items=["Augmentin"])

    result = await sub.substitutions_for_prescription(rx_id, has_prescribing_rmp=True)
    line = result[0]

    assert line.options == [], "no penicillin-class option may survive the gate"
    assert any("penicillin" in b.reason.lower() for b in line.blocked)


@pytest.mark.asyncio
async def test_schedule_h1_needs_a_prescriber_on_the_visit():
    await _set_patient_history(patient=1, allergies=[], conditions=[], medications=[])
    rx_id, _visit = await _prescription(patient=1, items=["Augmentin"])

    # no approved_by on the draft -> no registered prescriber attached
    result = await sub.substitutions_for_prescription(rx_id, has_prescribing_rmp=False)
    line = result[0]
    assert line.options == []
    assert any(b.severity == "schedule_h1" for b in line.blocked)

    # with a prescriber and no allergy, the same product is offerable
    allowed = await sub.substitutions_for_prescription(rx_id, has_prescribing_rmp=True)
    assert allowed[0].options


@pytest.mark.asyncio
async def test_a_fixed_dose_combination_is_never_swapped_for_one_ingredient():
    await _set_patient_history(patient=2, allergies=[], conditions=[], medications=[])
    rx_id, _visit = await _prescription(patient=2, items=["Combiflam"])

    result = await sub.substitutions_for_prescription(rx_id)
    line = result[0]

    original = sub.ingredient_set(line.ingredient)
    assert len(original) > 1, "precondition: Combiflam resolves to a combination"
    for option in line.options:
        assert sub.ingredient_set(option.name) == original, (
            f"{option.name} is not ingredient-equivalent to {line.ingredient}"
        )


@pytest.mark.asyncio
async def test_savings_and_jan_aushadhi_flags_are_surfaced_for_a_plain_generic():
    await _set_patient_history(patient=3, allergies=[], conditions=[], medications=[])
    rx_id, _visit = await _prescription(patient=3, items=["Dolo 650"])

    result = await sub.substitutions_for_prescription(rx_id)
    line = result[0]

    assert line.ingredient
    assert line.reasons and line.reasons_hi
    if line.options and line.total_savings_inr is not None:
        assert line.total_savings_inr > 0


@pytest.mark.asyncio
async def test_an_unmapped_brand_reports_no_equivalent_rather_than_failing():
    await _set_patient_history(patient=4, allergies=[], conditions=[], medications=[])
    rx_id, _visit = await _prescription(patient=4, items=["Zzzqq Nonexistent 999"])

    result = await sub.substitutions_for_prescription(rx_id)
    assert result[0].options == []
    assert result[0].reasons


@pytest.mark.asyncio
async def test_missing_prescription_is_not_found():
    with pytest.raises(ApiError) as exc:
        await sub.substitutions_for_prescription(uuid4())
    assert exc.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_safety_check_outage_never_claims_a_candidate_is_safe(monkeypatch):
    await _set_patient_history(patient=5, allergies=[], conditions=[], medications=[])
    rx_id, _visit = await _prescription(patient=5, items=["Dolo 650"])

    async def _down(*_args, **_kwargs):
        return None

    monkeypatch.setattr(sub, "_check_interactions", _down)

    result = await sub.substitutions_for_prescription(rx_id)
    line = result[0]
    if line.options:
        assert "Safety check unavailable" in line.reasons
        assert line.reasons_hi


@pytest.mark.asyncio
async def test_output_is_deterministic_across_calls():
    await _set_patient_history(patient=6, allergies=[], conditions=[], medications=[])
    rx_id, _visit = await _prescription(patient=6, items=["Dolo 650", "Combiflam"])

    first = await sub.substitutions_for_prescription(rx_id)
    second = await sub.substitutions_for_prescription(rx_id)
    assert [s.model_dump(mode="json") for s in first] == [
        s.model_dump(mode="json") for s in second
    ]


@pytest.mark.asyncio
async def test_every_row_echoes_the_prescription_id():
    """A caller that passed `visit_id` has no other way to learn which
    prescription was resolved -- there is no GET /prescriptions route and
    `VisitOut` carries `lab_order_id` but not `prescription_id`.
    """
    await _set_patient_history(patient=6, allergies=[], conditions=[], medications=[])
    rx_id, visit_id = await _prescription(patient=6, items=["Dolo 650", "Combiflam"])

    result = await sub.substitutions_for_prescription(rx_id)
    assert result
    assert all(line.prescription_id == rx_id for line in result)

    resolved = await sub.prescriptions_for_visit(visit_id)
    assert resolved == [rx_id]


@pytest.mark.asyncio
async def test_prescriptions_for_visit_resolves_the_latest_prescription():
    await _set_patient_history(patient=7, allergies=[], conditions=[], medications=[])
    rx_id, visit_id = await _prescription(patient=7, items=["Dolo 650"])
    assert await sub.prescriptions_for_visit(visit_id) == [rx_id]
