"""Secondary RxNav enrichment (section 3, source priority #3) -- international
ingredient/product normalisation only, consulted purely when the local
`india_drugs.csv` table has no hit. RxNav products are never given an Indian
₹ price or presented as an Indian brand (`GenericProduct.mrp_inr`/`price_inr`/
`jan_aushadhi_code` stay `None` on every RxNav-sourced product) -- that would
misrepresent an international catalogue entry as something stocked at a Jan
Aushadhi Kendra.

Two-layer cache per section 8 N2.4: an in-process `cachetools.TTLCache` (1h)
backed by Redis (`rxnorm:{key}`, 7 days), so a second lookup for the same
brand/rxcui makes zero HTTP calls even across process restarts.
"""

from __future__ import annotations

import httpx
from cachetools import TTLCache

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis_client import redis_client
from app.services.mapping.schemas import GenericMapping, GenericProduct

log = get_logger(__name__)

_TTL_CACHE: TTLCache = TTLCache(maxsize=1024, ttl=3600)  # 1 hour, in-process
_REDIS_TTL_SECONDS = 7 * 24 * 3600  # 7 days
_REDIS_PREFIX = "rxnorm"


def _cache_key(mapping: GenericMapping) -> str:
    return f"{_REDIS_PREFIX}:{(mapping.rxcui or '').strip().lower()}:{mapping.input.strip().lower()}"


async def _redis_get(key: str) -> GenericMapping | None:
    try:
        raw = await redis_client.get(key)
    except Exception as exc:  # noqa: BLE001 -- Redis unreachable is not fatal here
        log.warning("rxnorm_redis_get_failed", error=str(exc))
        return None
    if not raw:
        return None
    try:
        return GenericMapping.model_validate_json(raw)
    except Exception:  # noqa: BLE001
        return None


async def _redis_set(key: str, mapping: GenericMapping) -> None:
    try:
        await redis_client.set(key, mapping.model_dump_json(), ex=_REDIS_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        log.warning("rxnorm_redis_set_failed", error=str(exc))


async def _rxcui_for_name(client: httpx.AsyncClient, base: str, name: str) -> str | None:
    resp = await client.get(f"{base}/rxcui.json", params={"name": name, "search": "2"})
    resp.raise_for_status()
    ids = (resp.json().get("idGroup") or {}).get("rxnormId") or []
    return ids[0] if ids else None


async def _related_by_tty(client: httpx.AsyncClient, base: str, rxcui: str, tty: str) -> list[dict]:
    resp = await client.get(f"{base}/rxcui/{rxcui}/related.json", params={"tty": tty})
    resp.raise_for_status()
    groups = (resp.json().get("relatedGroup") or {}).get("conceptGroup") or []
    out: list[dict] = []
    for group in groups:
        out.extend(group.get("conceptProperties") or [])
    return out


async def enrich(mapping: GenericMapping) -> GenericMapping:
    """Frozen interface: `enrich(mapping: GenericMapping) -> GenericMapping`.
    `mapping.input`/`mapping.rxcui` seed the lookup; RXCUI -> ingredient
    (TTY=IN) -> product set (TTY=SCD, the generic/clinical-drug forms --
    branded SBD entries are dropped, since this function's whole purpose is
    surfacing generic equivalents).
    """
    key = _cache_key(mapping)
    if key in _TTL_CACHE:
        return _TTL_CACHE[key]

    cached = await _redis_get(key)
    if cached is not None:
        _TTL_CACHE[key] = cached
        return cached

    settings = get_settings()
    base = settings.rxnav_base

    async with httpx.AsyncClient(timeout=10.0) as client:
        rxcui = mapping.rxcui
        if rxcui is None and mapping.input:
            rxcui = await _rxcui_for_name(client, base, mapping.input)
        if rxcui is None:
            return mapping

        ingredient_concepts = await _related_by_tty(client, base, rxcui, "IN")
        ingredient_name = ingredient_concepts[0]["name"] if ingredient_concepts else None
        ingredient_rxcui = ingredient_concepts[0]["rxcui"] if ingredient_concepts else rxcui

        product_concepts = await _related_by_tty(client, base, ingredient_rxcui, "SCD+SBD")

    generics = [
        GenericProduct(
            name=p.get("name", ""),
            rxcui=p.get("rxcui"),
            form=None,
            strength=None,
            tty=p.get("tty"),
            jan_aushadhi_code=None,
            mrp_inr=None,
            price_inr=None,
            nppa_ceiling_inr=None,
            savings_pct=None,
        )
        for p in product_concepts
        if p.get("tty") == "SCD"
    ]

    result = mapping.model_copy(
        update={
            "rxcui": rxcui,
            "ingredient": ingredient_name or mapping.ingredient,
            "generics": generics or mapping.generics,
            "source_url": f"{base}/rxcui/{rxcui}",
            "cached": False,
        }
    )

    _TTL_CACHE[key] = result
    await _redis_set(key, result)
    return result
