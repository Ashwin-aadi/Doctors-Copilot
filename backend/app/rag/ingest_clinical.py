"""Populate the "clinical" collection: openFDA drug labels (pharmacology
backbone), PubMed abstracts (India-weighted specialty + disease searches),
and an India-first set of public guideline pages (ICMR/MoHFW/NCVBDC/NTEP/
NLEM/CDSCO/WHO). Every chunk carries `region: "IN" | "INTL"` so
`clinical_rag` can prefer Indian guidance at rerank time -- when an Indian
and an international source disagree on first-line management, the Indian
source wins; the international one is kept only as supporting pharmacology.

Falls back to a bundled `clinical_seed.jsonl` (chunks authored in our own
words, summarizing public label/guideline content) whenever live fetching
is unavailable or yields too little -- the collection must never be empty.
"""

import json
import re
from pathlib import Path

import httpx
import yaml

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rag.ingest_guidelines import _chunk_text
from app.rag.store import Chunk, VectorStore

log = get_logger(__name__)
settings = get_settings()

DATA_DIR = Path(__file__).parent / "data"
_FETCH_TIMEOUT = 20.0
_RATE_LIMIT_DELAY = 0.34  # ~3 req/s

SPECIALTIES = [
    "cardiology", "endocrinology", "pulmonology", "nephrology", "gastroenterology",
    "neurology", "infectious disease", "obstetrics", "pediatrics", "orthopedics",
    "dermatology", "psychiatry",
]
DISEASE_QUERIES = [
    "dengue India", "malaria India", "chikungunya India", "typhoid enteric fever India",
    "tuberculosis India ATT", "snakebite envenoming India", "rheumatic heart disease India",
]

CACHE_DIR = Path(__file__).resolve().parents[3] / "infra" / "corpus_cache"


async def _sleep_rate_limit() -> None:
    import asyncio

    await asyncio.sleep(_RATE_LIMIT_DELAY)


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


async def _cached_get_json(client: httpx.AsyncClient, key: str, url: str, params: dict) -> dict | None:
    cache_file = _cache_path(key)
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    try:
        resp = await client.get(url, params=params, timeout=_FETCH_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        log.warning("clinical_fetch_failed", url=url, error=str(exc))
        return None
    try:
        cache_file.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass
    return data


_FDA_SECTIONS = [
    "indications_and_usage",
    "dosage_and_administration",
    "contraindications",
    "warnings_and_cautions",
    "drug_interactions",
]


async def _fetch_openfda_chunks(client: httpx.AsyncClient, max_pages: int = 6) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in range(max_pages):
        skip = page * 100
        data = await _cached_get_json(
            client,
            f"openfda_{skip}",
            f"{settings.openfda_base}/drug/label.json",
            {"search": "_exists_:indications_and_usage", "limit": 100, "skip": skip},
        )
        if not data:
            break
        results = data.get("results", [])
        if not results:
            break
        for idx, record in enumerate(results):
            openfda = record.get("openfda", {})
            brand = (openfda.get("brand_name") or ["unknown drug"])[0]
            record_key = record.get("id") or record.get("set_id") or f"{page}-{idx}"
            for section in _FDA_SECTIONS:
                values = record.get(section)
                if not values:
                    continue
                text = " ".join(values)[:3000]
                for j, piece in enumerate(_chunk_text(text)):
                    chunks.append(
                        Chunk(
                            id=f"fda-{record_key}-{section}-{j}".replace(" ", "_"),
                            text=piece,
                            metadata={
                                "source": "openfda",
                                "title": f"{brand} — {section.replace('_', ' ')}",
                                "url": f"{settings.openfda_base}/drug/label.json",
                                "section": section,
                                "doc_type": "fda_label",
                                "published": "2024",
                                "region": "INTL",
                            },
                        )
                    )
        await _sleep_rate_limit()
    return chunks


async def _fetch_pubmed_chunks(client: httpx.AsyncClient) -> list[Chunk]:
    chunks: list[Chunk] = []
    seen_pmids: set[str] = set()
    queries = [f"{s} guideline India" for s in SPECIALTIES] + DISEASE_QUERIES
    for i, term in enumerate(queries):
        search = await _cached_get_json(
            client,
            f"pubmed_search_{i}",
            f"{settings.pubmed_base}/esearch.fcgi",
            {"db": "pubmed", "term": term, "retmax": 20, "retmode": "json"},
        )
        if not search:
            continue
        ids = search.get("esearchresult", {}).get("idlist", [])
        if not ids:
            continue
        try:
            resp = await client.get(
                f"{settings.pubmed_base}/efetch.fcgi",
                params={"db": "pubmed", "id": ",".join(ids), "rettype": "abstract", "retmode": "text"},
                timeout=_FETCH_TIMEOUT,
            )
            resp.raise_for_status()
            raw = resp.text
        except httpx.HTTPError as exc:
            log.warning("pubmed_efetch_failed", term=term, error=str(exc))
            continue
        for pmid, abstract in zip(ids, re.split(r"\n\n(?=\d+\.)", raw), strict=False):
            if pmid in seen_pmids:
                continue
            seen_pmids.add(pmid)
            abstract = re.sub(r"\s+", " ", abstract).strip()
            if len(abstract) < 100:
                continue
            for k, piece in enumerate(_chunk_text(abstract)):
                chunks.append(
                    Chunk(
                        id=f"pubmed-{pmid}-{k}",
                        text=piece,
                        metadata={
                            "source": "pubmed",
                            "title": f"PubMed {pmid} — {term}",
                            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                            "section": "abstract",
                            "doc_type": "pubmed",
                            "published": "2024",
                            "region": "IN" if "India" in term else "INTL",
                        },
                    )
                )
        await _sleep_rate_limit()
    return chunks


async def _fetch_guideline_chunks(client: httpx.AsyncClient) -> list[Chunk]:
    path = DATA_DIR / "clinical_sources.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    chunks: list[Chunk] = []
    for i, src in enumerate(data.get("sources", [])):
        try:
            resp = await client.get(src["url"], timeout=_FETCH_TIMEOUT)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("clinical_guideline_fetch_failed", url=src["url"], error=str(exc))
            continue
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s+", " ", text).strip()
        for j, piece in enumerate(_chunk_text(text)):
            chunks.append(
                Chunk(
                    id=f"clinical-guideline-{i}-{j}",
                    text=piece,
                    metadata={
                        "source": "clinical_sources",
                        "title": src["title"],
                        "url": src["url"],
                        "section": src.get("section", "overview"),
                        "doc_type": "guideline",
                        "published": "2024",
                        "region": src.get("region", "IN"),
                    },
                )
            )
    return chunks


def _seed_chunks() -> list[Chunk]:
    path = DATA_DIR / "clinical_seed.jsonl"
    chunks: list[Chunk] = []
    if not path.exists():
        return chunks
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        chunks.append(
            Chunk(
                id=entry["id"],
                text=entry["text"],
                metadata={
                    "source": "clinical_seed",
                    "title": entry["title"],
                    "url": entry.get("url", "internal://clinical_seed.jsonl"),
                    "section": entry.get("section", "overview"),
                    "doc_type": entry.get("doc_type", "guideline"),
                    "published": entry.get("published", "2024"),
                    "region": entry.get("region", "IN"),
                },
            )
        )
    return chunks


MIN_CHUNKS = 2000


async def ingest() -> int:
    store = VectorStore()
    live_chunks: list[Chunk] = []
    async with httpx.AsyncClient() as client:
        for fetcher in (_fetch_openfda_chunks, _fetch_pubmed_chunks, _fetch_guideline_chunks):
            try:
                live_chunks += await fetcher(client)
            except httpx.HTTPError as exc:
                log.warning("clinical_fetcher_failed", fetcher=fetcher.__name__, error=str(exc))

    chunks = list(live_chunks)
    if len(chunks) < MIN_CHUNKS:
        log.warning(
            "clinical_offline_fallback",
            live_chunks=len(live_chunks),
            reason="live fetch yielded too few chunks; topping up with bundled clinical seed",
        )
        chunks += _seed_chunks()

    deduped: dict[str, Chunk] = {}
    for chunk in chunks:
        deduped[chunk.id] = chunk
    chunks = list(deduped.values())

    store.upsert("clinical", chunks)
    log.info("clinical_ingested", count=len(chunks), live=len(live_chunks))
    return len(chunks)


if __name__ == "__main__":
    import asyncio

    asyncio.run(ingest())
