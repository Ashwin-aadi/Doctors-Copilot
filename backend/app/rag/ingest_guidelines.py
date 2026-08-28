"""Populate the "guidelines" collection: ESI tiers with their MoHFW colour mapping,
plus an India-first set of public guideline pages (Indian government and programme
sources, WHO material for the Indian disease burden, then MedlinePlus for general
symptom coverage), topped up with a bundled offline symptom corpus when live
fetching yields too little content (network unavailable, pages moved, CI
sandboxing, etc.). Every chunk carries a `region` of "IN" or "INTL" so retrieval
can prefer Indian guidance."""

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


# Script and style bodies survive naive tag-stripping, and site navigation,
# cookie banners and analytics snippets survive everything. Left in, they become
# retrievable chunks: the "Leptospirosis" page was ingested as three chunks of
# JavaScript, so no query could ever retrieve leptospirosis guidance no matter
# how well it was constructed. Thin-content pages -- which uncommon conditions
# tend to have -- are hit hardest by this, which is a large part of why
# retrieval kept landing on the same few common diseases.
_NON_CONTENT = re.compile(
    r"<(script|style|noscript|svg|head)\b[^>]*>.*?</\1\s*>|<!--.*?-->",
    re.IGNORECASE | re.DOTALL,
)


_STOPWORDS = frozenset(
    "the of and to in is are for with a an or be that this it as on by from can may".split()
)
MIN_PROSE_WORDS = 40
MIN_STOPWORD_RATIO = 0.12
MAX_SYMBOL_RATIO = 0.10


def _clean_html(raw: str) -> str:
    """Strip non-content elements, then tags, then collapse whitespace."""
    import html as html_module

    text = _NON_CONTENT.sub(" ", raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def is_prose(text: str) -> bool:
    """Reject boilerplate that survived cleaning: code, menus, link soup.

    Real guideline prose has a high proportion of common function words and few
    braces or semicolons. Both thresholds are deliberately loose -- the aim is to
    drop obvious machine text, not to police writing style.
    """
    words = text.split()
    if len(words) < MIN_PROSE_WORDS:
        return False
    lowered = [w.strip(".,;:()[]\"'").lower() for w in words]
    stopword_ratio = sum(1 for w in lowered if w in _STOPWORDS) / len(words)
    symbol_ratio = sum(1 for c in text if c in "{}<>|=;_\\/") / max(len(text), 1)
    return stopword_ratio >= MIN_STOPWORD_RATIO and symbol_ratio <= MAX_SYMBOL_RATIO


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
        colour = tier["colour"]
        text = (
            f"ESI {tier['esi']} — {tier['name']} (MoHFW casualty colour: {colour}). "
            f"{tier['description'].strip()} Examples: {'; '.join(tier['examples'])}."
        )
        chunks.append(
            Chunk(
                id=f"esi-{tier['esi']}",
                text=text,
                metadata={
                    "source": "esi_rules",
                    "title": f"ESI {tier['esi']} — {tier['name']} ({colour})",
                    "url": "internal://esi_rules.yaml",
                    "section": "esi",
                    "doc_type": "esi_rules",
                    "published": "2024",
                    "region": "IN",
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
                    "region": "IN",
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
        text = _clean_html(resp.text)
        kept = 0
        for j, piece in enumerate(_chunk_text(text)):
            if not is_prose(piece):
                continue
            kept += 1
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
                        "region": src.get("region", "INTL"),
                    },
                )
            )
        if kept == 0:
            log.warning("guideline_source_yielded_no_prose", url=src["url"], title=src["title"])
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

    # The curated corpus is ingested ALWAYS, not only when the network fails.
    # It is the only source that covers the less-common Indian differential --
    # leptospirosis, scrub typhus, organophosphate poisoning, heat stroke,
    # severe anaemia in pregnancy -- as clean clinical prose. Treating it as a
    # fallback meant that on a successful fetch the corpus lost exactly the
    # conditions the triage engine most needs to be able to surface.
    curated = _symptom_corpus_chunks()
    chunks += curated

    if len(chunks) < MIN_CHUNKS:
        log.warning(
            "guidelines_corpus_thin",
            live_chunks=len(live_chunks),
            curated_chunks=len(curated),
        )

    # Rebuild rather than merge, so chunks rejected by the quality filter on this
    # run cannot survive from a previous one under their old ids.
    store.reset("guidelines")
    store.upsert("guidelines", chunks)
    log.info(
        "guidelines_ingested",
        count=len(chunks),
        live=len(live_chunks),
        curated=len(curated),
    )
    return len(chunks)


if __name__ == "__main__":
    import asyncio

    asyncio.run(ingest())
