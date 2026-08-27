"""Brand -> generic mapping endpoint. `?brand=` is kept as an alias of `?name=`
for backward compatibility with the CP1 stub signature; the section 4.2
interface is `GET /medications/generic?name=|rxcui=`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, get_current_user, require_role
from app.core.errors import ApiError
from app.services.mapping.india_drugs import to_generic
from app.services.mapping.substitution import (
    Substitution,
    prescriptions_for_visit,
    substitutions_for_prescription,
)

router = APIRouter(prefix="/medications", tags=["medications"])


@router.get("/generic")
async def generic_lookup(
    name: str | None = None,
    rxcui: str | None = None,
    brand: str | None = None,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    mapping = await to_generic(name=name or brand, rxcui=rxcui)

    reasons: list[str] = []
    for product in mapping.generics:
        if product.jan_aushadhi_code and "Available at Jan Aushadhi Kendra" not in reasons:
            reasons.append("Available at Jan Aushadhi Kendra")
        if product.savings_pct and product.mrp_inr is not None and product.price_inr is not None:
            saved_inr = round(product.mrp_inr - product.price_inr)
            line = f"Saves ₹{saved_inr} ({product.savings_pct}%)"
            if line not in reasons:
                reasons.append(line)

    body = mapping.model_dump(mode="json")
    body["reasons"] = reasons
    return body


@router.get("/substitutions", response_model=list[Substitution])
async def substitutions(
    prescription_id: UUID | None = None,
    visit_id: UUID | None = None,
    user: CurrentUser = Depends(require_role("doctor", "staff")),
) -> list[Substitution]:
    """N3.4: safety-gated generic substitutes for every item on a
    prescription. Doctor/staff only -- the response names the patient's
    allergies and interactions by implication, and substitution is a
    prescribing decision.
    """
    if prescription_id is None and visit_id is None:
        raise ApiError(
            "VALIDATION_FAILED",
            "either prescription_id or visit_id is required",
            status_code=422,
        )

    if prescription_id is None:
        ids = await prescriptions_for_visit(visit_id)
        if not ids:
            raise ApiError(
                "NOT_FOUND", "no prescription on this visit yet", status_code=404
            )
        prescription_id = ids[-1]

    return await substitutions_for_prescription(prescription_id)
