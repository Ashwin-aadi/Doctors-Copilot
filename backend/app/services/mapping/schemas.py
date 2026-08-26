"""Brand->generic mapping response shapes (section 4.2). Both classes are
mine -- `app/services/mapping/` is an owned path -- so no subclassing dance
is needed here, unlike the scheduling/queueing schemas.
"""

from __future__ import annotations

from pydantic import BaseModel


class GenericProduct(BaseModel):
    name: str
    rxcui: str | None = None
    form: str | None = None
    strength: str | None = None
    tty: str | None = None
    jan_aushadhi_code: str | None = None
    mrp_inr: float | None = None
    price_inr: float | None = None
    nppa_ceiling_inr: float | None = None
    savings_pct: float | None = None


class GenericMapping(BaseModel):
    input: str
    rxcui: str | None = None
    ingredient: str | None = None
    generics: list[GenericProduct] = []
    nlem: bool = False
    schedule_h: bool = False
    source_url: str | None = None
    cached: bool = False
