"""Primary, offline-first brand -> generic resolution (section 3, source
priority #1). Always tried before any network call: `india_drugs.csv`
(derived from NLEM 2022 + PMBJP/Jan Aushadhi product list + common
CDSCO-approved brands actually written on Indian prescriptions) is the
authoritative table for this project.

Resolution chain (section 8 N2.4):
1. Normalise the brand name (strip strength/form/-SR/-DS/Plus, case-fold),
   look up `india_drugs.csv`.
2. On hit -> ingredient(s), NLEM flag, Schedule H/H1 flag, Jan Aushadhi code
   + price, MRP; join `nppa_ceiling.csv`; compute `savings_pct` deterministically.
3. On miss and network up -> RxNav enrichment (`app.services.mapping.rxnorm.enrich`).
4. On miss and network down -> `ApiError("NOT_FOUND")` with a closest-ingredient
   suggestion (deterministic normalised edit distance, ties broken alphabetically).

No LLM anywhere in this path (autonomy contract rule 6).
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

from app.core.errors import ApiError
from app.services.mapping.schemas import GenericMapping, GenericProduct

_DATA_DIR = Path(__file__).resolve().parent / "data"
_DRUGS_CSV = _DATA_DIR / "india_drugs.csv"
_NPPA_CSV = _DATA_DIR / "nppa_ceiling.csv"

# Common Indian brand-name suffixes that don't change the underlying
# ingredient (sustained-release / combination-marketing tags) -- stripped
# during normalisation so "Pan-40", "Pan D", "Pan-SR" and "Pan" all resolve
# to the same catalogue entry as the bare "Pan".
_SUFFIX_RE = re.compile(
    r"\b(sr|ds|xl|xr|er|od|cv|lc|forte|plus|kid|redi|d|dt"
    r"|tablet|tablets|capsule|capsules|syrup|drops|drop|cream|ointment"
    r"|injection|inj|spray|inhaler|lotion|gel|shampoo)\b",
    re.IGNORECASE,
)
_STRENGTH_RE = re.compile(
    r"\d+(\.\d+)?\s*(mg|mcg|g|ml|iu|%|/\d+(\.\d+)?\s*(mg|mcg|ml))?\b", re.IGNORECASE
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_brand(name: str) -> str:
    n = name.strip().lower()
    n = _STRENGTH_RE.sub(" ", n)
    n = _SUFFIX_RE.sub(" ", n)
    n = _NON_ALNUM_RE.sub(" ", n).strip()
    return re.sub(r"\s+", " ", n)


@lru_cache(maxsize=1)
def _drug_rows() -> list[dict]:
    with _DRUGS_CSV.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def _nppa_index() -> dict[tuple[str, str], float]:
    if not _NPPA_CSV.exists():
        return {}
    with _NPPA_CSV.open(encoding="utf-8") as f:
        return {
            (row["ingredient"], row["strength"]): float(row["nppa_ceiling_inr"])
            for row in csv.DictReader(f)
            if row.get("nppa_ceiling_inr")
        }


@lru_cache(maxsize=1)
def _brand_index() -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    for row in _drug_rows():
        idx.setdefault(normalize_brand(row["brand"]), []).append(row)
    return idx


@lru_cache(maxsize=1)
def _rxcui_index() -> dict[str, dict]:
    return {row["rxcui"]: row for row in _drug_rows() if row.get("rxcui")}


def _generic_products(ingredient: str, group_rows: list[dict]) -> list[GenericProduct]:
    by_form_strength: dict[tuple[str, str], list[dict]] = {}
    for row in group_rows:
        by_form_strength.setdefault((row["form"], row["strength"]), []).append(row)

    nppa = _nppa_index()
    products: list[GenericProduct] = []
    for (form, strength), rows in sorted(by_form_strength.items()):
        mrps = [float(r["mrp_inr"]) for r in rows if r.get("mrp_inr") and float(r["mrp_inr"]) > 0]
        mrp = min(mrps) if mrps else None
        ja_row = next((r for r in rows if r.get("jan_aushadhi_code")), None)
        ceiling = nppa.get((ingredient, strength))

        if ceiling is not None:
            price = ceiling
        elif ja_row is not None and mrp is not None:
            # No DPCO ceiling on file for this ingredient/strength but it is
            # PMBJP-stocked -- Jan Aushadhi generics typically run well below
            # branded MRP; modelled as a fixed, deterministic fraction.
            price = round(mrp * 0.4, 2)
        else:
            price = None

        savings_pct = (
            round(100 * (mrp - price) / mrp, 1) if (mrp is not None and price is not None and mrp > 0) else None
        )

        rxcui = next((r["rxcui"] for r in rows if r.get("rxcui")), None)
        products.append(
            GenericProduct(
                name=rows[0]["generic_name"],
                rxcui=rxcui or None,
                form=form or None,
                strength=strength or None,
                tty=None,
                jan_aushadhi_code=ja_row["jan_aushadhi_code"] if ja_row else None,
                mrp_inr=mrp,
                price_inr=price,
                nppa_ceiling_inr=ceiling,
                savings_pct=savings_pct,
            )
        )
    return products


def _mapping_from_rows(input_label: str, matched_rows: list[dict]) -> GenericMapping:
    ingredient_key = matched_rows[0]["ingredient"]
    group = [r for r in _drug_rows() if r["ingredient"] == ingredient_key]
    nlem = any(r["nlem"].strip().lower() in ("1", "true", "yes") for r in group)
    schedule_h = any(r["schedule_h"].strip().lower() in ("1", "true", "yes") for r in group)
    rxcui = next((r["rxcui"] for r in matched_rows if r.get("rxcui")), None)

    return GenericMapping(
        input=input_label,
        rxcui=rxcui or None,
        ingredient=matched_rows[0]["generic_name"],
        generics=_generic_products(ingredient_key, group),
        nlem=nlem,
        schedule_h=schedule_h,
        source_url=None,
        cached=True,
    )


def closest_ingredient_suggestion(query: str) -> str | None:
    """Deterministic offline fallback (section 8 N2.4 step 4): the pack's
    generic name whose normalised form has the highest similarity ratio to
    the query, ties broken alphabetically (ascending sort key already puts
    the lexicographically-first name first; `max` with a `-ratio` primary key
    and `name` secondary key reproduces that without relying on sort
    stability).
    """
    names = sorted({row["generic_name"] for row in _drug_rows()})
    if not names:
        return None
    normalized_query = normalize_brand(query)
    best = min(
        names,
        key=lambda n: (-fuzz.ratio(normalized_query, normalize_brand(n)), n),
    )
    return best


async def to_generic(name: str | None = None, rxcui: str | None = None) -> GenericMapping:
    if rxcui:
        row = _rxcui_index().get(rxcui)
        if row is not None:
            return _mapping_from_rows(input_label=name or rxcui, matched_rows=[row])

    if name:
        key = normalize_brand(name)
        matched_rows = _brand_index().get(key)
        if matched_rows:
            return _mapping_from_rows(input_label=name, matched_rows=matched_rows)

    if not name and not rxcui:
        raise ApiError("VALIDATION_FAILED", "either name or rxcui must be provided", status_code=422)

    # Local table miss -- try RxNav enrichment (international, network-bound).
    # Assume the network can be down at any moment (autonomy contract rule 4):
    # any failure here just falls through to the offline suggestion path.
    try:
        from app.services.mapping.rxnorm import enrich

        seed = GenericMapping(
            input=name or rxcui or "", rxcui=rxcui, ingredient=None,
            generics=[], nlem=False, schedule_h=False, source_url=None, cached=False,
        )
        enriched = await enrich(seed)
        if enriched.generics or enriched.ingredient:
            return enriched
    except Exception:  # noqa: BLE001 -- any network/parse failure, not just httpx's
        pass

    suggestion = closest_ingredient_suggestion(name) if name else None
    raise ApiError(
        "NOT_FOUND",
        f"no generic mapping found for '{name or rxcui}'",
        status_code=404,
        details={"suggestion": suggestion} if suggestion else {},
    )
