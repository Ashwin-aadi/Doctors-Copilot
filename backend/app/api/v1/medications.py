"""Brand -> generic mapping endpoint. `?brand=` is kept as an alias of `?name=`
for backward compatibility with the CP1 stub signature; the section 4.2
interface is `GET /medications/generic?name=|rxcui=`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, get_current_user
from app.services.mapping.india_drugs import to_generic

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
