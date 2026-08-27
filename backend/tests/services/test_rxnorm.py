"""Brand -> generic mapping tests. The CSV/normalisation/matching tests are
pure (no DB, no network). The API tests need a reachable Postgres + Redis
(same infra caveat as the rest of `tests/services/`).
"""

from __future__ import annotations

import csv
from pathlib import Path

import httpx
import pytest

from app.core.errors import ApiError
from app.services.mapping.india_drugs import (
    closest_ingredient_suggestion,
    normalize_brand,
    to_generic,
)

# Resolved from this file, not the working directory: `make test` runs
# pytest with `backend/` as cwd, so a repo-root-relative path never
# resolves. Mirrors how app/rag/triage_rag.py locates its own data dir.
_BACKEND = Path(__file__).resolve().parents[2]
_CSV_PATH = _BACKEND / "app/services/mapping/data/india_drugs.csv"


def test_india_drugs_csv_has_at_least_300_rows_and_named_brands():
    rows = list(csv.DictReader(open(_CSV_PATH, encoding="utf-8")))
    assert len(rows) >= 300, len(rows)
    brands = {r["brand"].strip().lower() for r in rows}
    for named in ["crocin", "dolo", "combiflam", "augmentin", "glycomet", "pan", "ecosprin", "thyronorm", "asthalin"]:
        assert named in brands or any(named in b for b in brands), named
    nlem_count = sum(1 for r in rows if r["nlem"].strip().lower() in ("1", "true", "yes"))
    assert nlem_count >= 80, nlem_count
    ja_count = sum(1 for r in rows if r["jan_aushadhi_code"].strip())
    assert ja_count >= 100, ja_count


def test_normalize_brand_strips_strength_and_form_suffixes():
    assert normalize_brand("Dolo 650") == normalize_brand("Dolo-650") == "dolo"
    assert normalize_brand("Pan-D") == normalize_brand("Pan 40mg") == "pan"
    assert normalize_brand("Asthalin Inhaler") == "asthalin"


def test_closest_ingredient_suggestion_is_deterministic():
    a = closest_ingredient_suggestion("Paracetemol")
    b = closest_ingredient_suggestion("Paracetemol")
    assert a == b == "Paracetamol"


@pytest.mark.asyncio
async def test_to_generic_crocin_resolves_to_paracetamol_nlem():
    mapping = await to_generic(name="Crocin")
    assert mapping.ingredient is not None
    assert "paracetamol" in mapping.ingredient.lower()
    assert mapping.generics
    assert mapping.nlem is True


@pytest.mark.asyncio
async def test_to_generic_dolo_650_has_price_and_positive_savings():
    mapping = await to_generic(name="Dolo 650")
    assert mapping.generics
    priced = [g for g in mapping.generics if g.price_inr is not None]
    assert priced
    assert any((g.savings_pct or 0) > 0 for g in priced)


@pytest.mark.asyncio
async def test_to_generic_unknown_brand_with_network_blocked_uses_local_fallback(monkeypatch):
    """Forces the network-down path: `httpx.AsyncClient.get` raises for any
    RxNav call, so an unknown brand must resolve via the local-CSV closest-
    ingredient suggestion (section 8 N2.4 step 4), never a network exception
    bubbling up as a 500.
    """

    async def _blocked_get(self, *args, **kwargs):  # noqa: ANN001, ARG001
        raise httpx.ConnectError("network blocked for offline test")

    monkeypatch.setattr(httpx.AsyncClient, "get", _blocked_get)

    with pytest.raises(ApiError) as exc_info:
        await to_generic(name="NotARealBrandXYZ123")

    assert exc_info.value.code == "NOT_FOUND"
    assert exc_info.value.details.get("suggestion")


@pytest.mark.asyncio
async def test_generic_lookup_api_crocin(client, auth_headers):
    resp = await client.get("/api/v1/medications/generic", params={"name": "Crocin"}, headers=auth_headers("patient"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "paracetamol" in (body["ingredient"] or "").lower()
    assert len(body["generics"]) >= 1
    assert body["nlem"] is True


@pytest.mark.asyncio
async def test_generic_lookup_api_dolo_650_shows_savings(client, auth_headers):
    resp = await client.get(
        "/api/v1/medications/generic", params={"name": "Dolo 650"}, headers=auth_headers("patient")
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["generics"][0]["price_inr"] is not None
    assert body["generics"][0]["savings_pct"] > 0
