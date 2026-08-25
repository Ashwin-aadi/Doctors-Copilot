"""Populate the "guidelines" collection: ESI tiers + public MedlinePlus guideline
pages, topped up with a bundled offline symptom corpus when live fetching yields
too little content (network unavailable, pages moved, CI sandboxing, etc.)."""

import re
from pathlib import Path

import httpx
import yaml

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rag.store import Chunk, VectorStore

log = get_logger(__name__)
settings = get_settings()

DATA_DIR = Path(__file__).parent / "data"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
_FETCH_TIMEOUT = 20.0


def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks = []
    step = max(size - overlap, 1)
    for start in range(0, len(words), step):
        piece = " ".join(words[start : start + size])
        if piece:
            chunks.append(piece)
        if start + size >= len(words):
            break
    return chunks


def _esi_chunks() -> list[Chunk]:
    data = yaml.safe_load((DATA_DIR / "esi_rules.yaml").read_text(encoding="utf-8"))
    chunks: list[Chunk] = []
    for tier in data["tiers"]:
        text = (
            f"ESI {tier['esi']} — {tier['name']}. {tier['description'].strip()} "
            f"Examples: {'; '.join(tier['examples'])}."
        )
        chunks.append(
            Chunk(
                id=f"esi-{tier['esi']}",
                text=text,
                metadata={
                    "source": "esi_rules",
                    "title": f"ESI {tier['esi']} — {tier['name']}",
                    "url": "internal://esi_rules.yaml",
                    "section": "esi",
                    "doc_type": "esi_rules",
                    "published": "2024",
                },
            )
        )
    return chunks


def _symptom_corpus_chunks() -> list[Chunk]:
    data = yaml.safe_load((DATA_DIR / "symptom_corpus.yaml").read_text(encoding="utf-8"))
    chunks: list[Chunk] = []
    for entry in data["entries"]:
        chunks.append(
            Chunk(
                id=entry["id"],
                text=f"{entry['title']}. {entry['text'].strip()}",
                metadata={
                    "source": "symptom_corpus",
                    "title": entry["title"],
                    "url": "internal://symptom_corpus.yaml",
                    "section": entry.get("section", "general"),
                    "doc_type": "symptom_corpus",
                    "published": "2024",
                },
            )
        )
    return chunks


async def _fetch_guideline_source_chunks(client: httpx.AsyncClient) -> list[Chunk]:
    data = yaml.safe_load((DATA_DIR / "guideline_sources.yaml").read_text(encoding="utf-8"))
    chunks: list[Chunk] = []
    for i, src in enumerate(data["sources"]):
        try:
            resp = await client.get(src["url"], timeout=_FETCH_TIMEOUT)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("guideline_fetch_failed", url=src["url"], error=str(exc))
            continue
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s+", " ", text).strip()
        for j, piece in enumerate(_chunk_text(text)):
            chunks.append(
                Chunk(
                    id=f"guideline-{i}-{j}",
                    text=piece,
                    metadata={
                        "source": "guideline_sources",
                        "title": src["title"],
                        "url": src["url"],
                        "section": src.get("section", "overview"),
                        "doc_type": "guideline",
                        "published": "2024",
                    },
                )
            )
    return chunks


MIN_CHUNKS = 200


async def ingest() -> int:
    store = VectorStore()
    chunks = _esi_chunks()

    live_chunks: list[Chunk] = []
    async with httpx.AsyncClient() as client:
        try:
            live_chunks += await _fetch_guideline_source_chunks(client)
        except httpx.HTTPError as exc:
            log.warning("guideline_sources_fetch_failed", error=str(exc))
    chunks += live_chunks

    if len(chunks) < MIN_CHUNKS:
        log.warning(
            "guidelines_offline_fallback",
            live_chunks=len(live_chunks),
            reason="live fetch yielded too few chunks; topping up with bundled symptom corpus",
        )
        chunks += _symptom_corpus_chunks()

    store.upsert("guidelines", chunks)
    log.info("guidelines_ingested", count=len(chunks), live=len(live_chunks))
    return len(chunks)


if __name__ == "__main__":
    import asyncio

    asyncio.run(ingest())
