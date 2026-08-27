"""Brand -> generic substitution with safety gating (section 8 N3.4).

For every prescribed item: resolve it to its generic candidates via the
offline-first India table, then put each candidate through the interaction
checker against the patient's current medications, allergies and conditions.
A candidate is *blocked*, with a stated reason, when it would:

1. produce a `major` interaction with something the patient already takes,
2. conflict with a recorded allergy,
3. be contraindicated by a recorded condition,
4. be Schedule H1 with no prescribing RMP attached to the visit, or
5. differ in ingredient set from the original -- a fixed-dose combination is
   never substituted by a single ingredient, and vice versa.

Rule 5 is checked first and locally, because it is the one failure mode that
must hold even when every network- and model-backed check is unavailable:
swapping Combiflam (ibuprofen + paracetamol) for plain paracetamol is a
silent under-dose, not a saving.

No LLM in this path. The interaction data comes from Virat's bundled
`app.ml.tools`; when that module is absent the response says the safety check
was unavailable and never claims a candidate is safe.
"""

from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select

from app.core.errors import ApiError
from app.core.logging import get_logger
from app.db.models.clinical import Prescription
from app.db.models.patient import Patient
from app.db.session import SessionLocal
from app.services.mapping.india_drugs import to_generic
from app.services.mapping.schemas import GenericProduct

log = get_logger(__name__)

_SAFETY_UNAVAILABLE_EN = "Safety check unavailable"
_SAFETY_UNAVAILABLE_HI = "सुरक्षा जांच उपलब्ध नहीं"

# Ingredient strings in the India table are written as "a + b" for
# fixed-dose combinations.
_INGREDIENT_SPLIT = re.compile(r"\s*\+\s*")


class BlockedOption(BaseModel):
    name: str
    rxcui: str | None = None
    reason: str
    severity: str
    source_url: str | None = None


class Substitution(BaseModel):
    # Echoed on every row so a caller that passed `visit_id` learns which
    # prescription was resolved -- there is no GET /prescriptions route and
    # `VisitOut` carries `lab_order_id` but not `prescription_id`, so this is
    # the only way a visit-scoped caller can find the id it needs to lock or
    # export. Optional to keep the model constructible without one.
    prescription_id: UUID | None = None
    original: str
    ingredient: str | None = None
    options: list[GenericProduct] = []
    blocked: list[BlockedOption] = []
    total_savings_inr: float | None = None
    reasons: list[str] = []
    reasons_hi: list[str] = []


def ingredient_set(ingredient: str | None) -> frozenset[str]:
    """Normalised ingredient set, so "Ibuprofen + Paracetamol" and
    "paracetamol + ibuprofen" compare equal but neither matches plain
    "paracetamol".
    """
    if not ingredient:
        return frozenset()
    return frozenset(
        part.strip().lower() for part in _INGREDIENT_SPLIT.split(ingredient) if part.strip()
    )


async def _check_interactions(
    patient_id: UUID, medications: list[str], allergies: list[str], conditions: list[str]
) -> dict | None:
    """Interaction report for `medications` in the context of this patient.

    Prefers `app.ml.safety.check_interactions`, which accepts allergies and
    conditions; `app.ml.tools.check_interactions` takes medications only, so
    it would silently return no allergy conflicts and the gate below would
    wave a penicillin substitute through for a penicillin-allergic patient.
    Falls back to the tools wrapper, then to `None`, which the caller renders
    as "safety check unavailable" rather than as "safe".
    """
    try:
        from app.ml.safety import check_interactions as _safety_check
        from app.ml.schemas_ml import InteractionRequest

        report = await _safety_check(
            InteractionRequest(
                medications=medications, allergies=allergies, conditions=conditions
            )
        )
        return report.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 -- fall through to the narrower tool
        log.warning("safety_check_degraded", error=str(exc))

    try:
        from app.ml.tools import check_interactions as _tools_check

        return await _tools_check(patient_id, medications)
    except Exception as exc:  # noqa: BLE001
        log.warning("safety_check_unavailable", error=str(exc))
        return None


def _block_for_candidate(
    candidate: GenericProduct, report: dict, current_medications: list[str]
) -> BlockedOption | None:
    """The first disqualifying finding for this candidate, or None.

    Only `major` interactions block. Moderate and minor ones are real but are
    a prescribing judgement for the doctor, not grounds for the system to
    withhold a cheaper equivalent of a drug already prescribed.
    """
    name_l = candidate.name.lower()
    candidate_parts = ingredient_set(candidate.name)

    def _mentions(value: str | None) -> bool:
        if not value:
            return False
        v = value.lower()
        return v in name_l or name_l in v or bool(candidate_parts & ingredient_set(value))

    for conflict in report.get("allergy_conflicts", []):
        if _mentions(conflict.get("drug")):
            return BlockedOption(
                name=candidate.name,
                rxcui=candidate.rxcui,
                reason=f"Allergy to {conflict.get('allergen')}: {conflict.get('rationale', '')}".strip(),
                severity="allergy",
                source_url=conflict.get("source"),
            )

    for contra in report.get("contraindications", []):
        if _mentions(contra.get("drug")):
            return BlockedOption(
                name=candidate.name,
                rxcui=candidate.rxcui,
                reason=f"Contraindicated in {contra.get('condition')}: {contra.get('rationale', '')}".strip(),
                severity="contraindication",
                source_url=contra.get("source"),
            )

    current_l = {m.lower() for m in current_medications}
    for pair in report.get("pairs", []):
        if pair.get("severity") != "major":
            continue
        a, b = pair.get("drug_a", ""), pair.get("drug_b", "")
        if not (_mentions(a) or _mentions(b)):
            continue
        other = b if _mentions(a) else a
        # only block when the *other* half is something the patient is
        # actually on -- a major pair between two candidates for the same
        # prescription line is not a real co-administration
        if other.lower() not in current_l and not any(other.lower() in m for m in current_l):
            continue
        return BlockedOption(
            name=candidate.name,
            rxcui=candidate.rxcui,
            reason=f"Major interaction with {other}: {pair.get('mechanism', '')}".strip(),
            severity="major",
            source_url=pair.get("url"),
        )

    return None


async def substitutions_for_prescription(
    prescription_id: UUID, *, has_prescribing_rmp: bool | None = None
) -> list[Substitution]:
    """One `Substitution` per prescribed item.

    `has_prescribing_rmp` defaults to whether the prescription has an
    `approved_by` -- under the Drugs & Cosmetics Rules a Schedule H1 product
    may only be dispensed against a registered practitioner's prescription,
    so an unapproved draft cannot offer H1 substitutes.
    """
    async with SessionLocal() as session:
        prescription = await session.get(Prescription, prescription_id)
        if prescription is None:
            raise ApiError("NOT_FOUND", "prescription not found", status_code=404)
        patient = await session.get(Patient, prescription.patient_id)
        items = list(prescription.items or [])
        approved_by = prescription.approved_by

    if has_prescribing_rmp is None:
        has_prescribing_rmp = approved_by is not None

    allergies = [str(a) for a in (patient.allergies or [])] if patient else []
    conditions = [str(c) for c in (patient.conditions or [])] if patient else []
    current_medications = [str(m) for m in (patient.medications or [])] if patient else []

    out: list[Substitution] = []
    for item in items:
        name = item.get("name") if isinstance(item, dict) else str(item)
        if not name:
            continue
        line = await _substitute_one(
            name,
            patient_id=prescription.patient_id,
            allergies=allergies,
            conditions=conditions,
            current_medications=current_medications,
            has_prescribing_rmp=has_prescribing_rmp,
        )
        line.prescription_id = prescription_id
        out.append(line)
    return out


async def _substitute_one(
    name: str,
    *,
    patient_id: UUID,
    allergies: list[str],
    conditions: list[str],
    current_medications: list[str],
    has_prescribing_rmp: bool,
) -> Substitution:
    reasons_en: list[str] = []
    reasons_hi: list[str] = []

    try:
        mapping = await to_generic(name=name)
    except ApiError:
        return Substitution(
            original=name,
            reasons=["No generic equivalent on file"],
            reasons_hi=["कोई जेनेरिक विकल्प नहीं मिला"],
        )

    original_parts = ingredient_set(mapping.ingredient)

    candidates = list(mapping.generics)
    options: list[GenericProduct] = []
    blocked: list[BlockedOption] = []

    # Gate 1 (local, always available): exact ingredient-set equivalence.
    equivalent: list[GenericProduct] = []
    for candidate in candidates:
        if original_parts and ingredient_set(candidate.name) != original_parts:
            blocked.append(
                BlockedOption(
                    name=candidate.name,
                    rxcui=candidate.rxcui,
                    reason=(
                        f"Not equivalent to {mapping.ingredient} - "
                        "a combination is never swapped for a single ingredient"
                    ),
                    severity="not_equivalent",
                )
            )
            continue
        equivalent.append(candidate)

    # Gate 2 (local): Schedule H1 needs a registered prescriber on the visit.
    prescribable: list[GenericProduct] = []
    for candidate in equivalent:
        if mapping.schedule_h and not has_prescribing_rmp:
            blocked.append(
                BlockedOption(
                    name=candidate.name,
                    rxcui=candidate.rxcui,
                    reason="Schedule H1 - needs a registered practitioner's prescription",
                    severity="schedule_h1",
                )
            )
            continue
        prescribable.append(candidate)

    # Gate 3: interaction / allergy / contraindication screening.
    #
    # Each candidate is screened by its individual ingredient components as
    # well as by its full product name. The allergy matcher compares an
    # allergen against a single generic name, so a fixed-dose combination
    # ("Amoxicillin + Clavulanic acid") submitted whole matches nothing and a
    # penicillin-allergic patient would be handed an amoxicillin product.
    # Splitting the combination here is what makes the gate actually fire.
    report = None
    if prescribable:
        screened: list[str] = [*current_medications]
        for candidate in prescribable:
            screened.append(candidate.name)
            screened.extend(sorted(ingredient_set(candidate.name)))
        # de-duplicate while keeping a deterministic order
        seen: set[str] = set()
        medications = [m for m in screened if not (m.lower() in seen or seen.add(m.lower()))]

        report = await _check_interactions(
            patient_id,
            medications=medications,
            allergies=allergies,
            conditions=conditions,
        )

    if report is None:
        # Never claim these are safe -- surface them with the caveat instead.
        options = list(prescribable)
        if options:
            reasons_en.append(_SAFETY_UNAVAILABLE_EN)
            reasons_hi.append(_SAFETY_UNAVAILABLE_HI)
    else:
        for candidate in prescribable:
            block = _block_for_candidate(candidate, report, current_medications)
            if block is not None:
                blocked.append(block)
                continue
            options.append(candidate)

    total_savings = None
    savings = [
        c.mrp_inr - c.price_inr
        for c in options
        if c.mrp_inr is not None and c.price_inr is not None and c.mrp_inr > c.price_inr
    ]
    if savings:
        total_savings = round(sum(savings), 2)
        reasons_en.append(f"Saves up to Rs {round(max(savings))} per pack")
        reasons_hi.append(f"प्रति पैक {round(max(savings))} रुपये तक की बचत")

    if any(c.jan_aushadhi_code for c in options):
        reasons_en.append("Available at Jan Aushadhi Kendra")
        reasons_hi.append("जन औषधि केंद्र पर उपलब्ध")

    if mapping.nlem:
        reasons_en.append("On the National List of Essential Medicines")
        reasons_hi.append("राष्ट्रीय आवश्यक दवा सूची में शामिल")

    if blocked and not reasons_en:
        reasons_en.append("Some substitutes were withheld on safety grounds")
        reasons_hi.append("कुछ विकल्प सुरक्षा कारणों से रोके गए")

    # Deterministic output ordering -- ties broken by name, never by dict order.
    options.sort(key=lambda c: (c.price_inr if c.price_inr is not None else float("inf"), c.name))
    blocked.sort(key=lambda b: (b.severity, b.name))

    return Substitution(
        original=name,
        ingredient=mapping.ingredient,
        options=options,
        blocked=blocked,
        total_savings_inr=total_savings,
        reasons=reasons_en,
        reasons_hi=reasons_hi,
    )


async def prescriptions_for_visit(visit_id: UUID) -> list[UUID]:
    """Prescription ids attached to a visit, oldest first -- lets the route
    accept `?visit_id=` as well as `?prescription_id=`.
    """
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Prescription.id)
                .where(Prescription.visit_id == visit_id)
                .order_by(Prescription.created_at, Prescription.id)
            )
        ).scalars().all()
    return list(rows)
