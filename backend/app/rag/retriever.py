"""Hybrid BM25 + dense retrieval with RRF fusion and cross-encoder rerank."""

from functools import lru_cache

from rank_bm25 import BM25Okapi

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rag.store import Hit, VectorStore

log = get_logger(__name__)
settings = get_settings()

_RRF_K = 60
_CANDIDATES = 40

_bm25_cache: dict[str, tuple[int, BM25Okapi | None, list[str], list[str], list[dict]]] = {}


@lru_cache
def _cross_encoder():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(settings.rerank_model)


def _bm25_index(collection: str):
    store = VectorStore()
    coll = store._collection(collection)  # noqa: SLF001
    count = coll.count()
    cached = _bm25_cache.get(collection)
    if cached and cached[0] == count:
        return cached[1:]
    if count == 0:
        empty: tuple[int, None, list, list, list] = (0, None, [], [], [])
        _bm25_cache[collection] = empty
        return empty[1:]
    data = coll.get(include=["documents", "metadatas"])
    ids = data["ids"]
    docs = data["documents"]
    metas = data["metadatas"]
    tokenized = [d.lower().split() for d in docs]
    bm25 = BM25Okapi(tokenized)
    entry = (count, bm25, ids, docs, metas)
    _bm25_cache[collection] = entry
    return entry[1:]


def _bm25_search(collection: str, query: str, k: int) -> list[Hit]:
    bm25, ids, docs, metas = _bm25_index(collection)
    if bm25 is None:
        return []
    scores = bm25.get_scores(query.lower().split())
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [Hit(id=ids[i], text=docs[i], score=float(scores[i]), metadata=dict(metas[i])) for i in ranked]


def _rrf_fuse(*ranked_lists: list[Hit]) -> list[Hit]:
    scores: dict[str, float] = {}
    by_id: dict[str, Hit] = {}
    for ranked in ranked_lists:
        for rank, hit in enumerate(ranked):
            scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            by_id.setdefault(hit.id, hit)
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [by_id[hit_id] for hit_id, _ in fused]


def _rerank(query: str, hits: list[Hit], k: int) -> list[Hit]:
    if not hits:
        return []
    try:
        encoder = _cross_encoder()
        pairs = [(query, h.text) for h in hits]
        scores = encoder.predict(pairs)
        ranked = sorted(zip(hits, scores, strict=True), key=lambda hs: hs[1], reverse=True)
        return [Hit(id=h.id, text=h.text, score=float(s), metadata=h.metadata) for h, s in ranked[:k]]
    except Exception as exc:  # noqa: BLE001
        log.warning("rerank_failed", error=str(exc))
        return hits[:k]


async def hybrid(collection: str, query: str, k: int = 8, where: dict | None = None) -> list[Hit]:
    store = VectorStore()
    dense_hits = store.query(collection, query, k=_CANDIDATES, where=where)
    bm25_hits = _bm25_search(collection, query, _CANDIDATES)
    if where:
        allowed = {h.id for h in dense_hits}
        bm25_hits = [h for h in bm25_hits if h.id in allowed]
    fused = _rrf_fuse(dense_hits, bm25_hits)[:_CANDIDATES]
    return _rerank(query, fused, k)


# --------------------------------------------------------------------------
# Multi-query retrieval.
#
# A single query vector over a whole transcript is dominated by whatever tokens
# repeat most, which for any febrile presentation are the generic ones. The
# functions below fan out over several weighted queries, fuse them, then rescore
# on evidence the patient actually gave -- rewarding chunks that speak to a
# discriminating feature and penalising chunks whose whole case rests on a
# feature the patient explicitly denied.
# --------------------------------------------------------------------------

_MAX_PER_SOURCE = 2
_DISCRIMINATOR_BONUS = 0.22
_DENIED_PENALTY = 0.30


def _weighted_rrf(ranked_lists: list[tuple[list[Hit], float]]) -> list[Hit]:
    scores: dict[str, float] = {}
    by_id: dict[str, Hit] = {}
    for ranked, weight in ranked_lists:
        for rank, hit in enumerate(ranked):
            scores[hit.id] = scores.get(hit.id, 0.0) + weight / (_RRF_K + rank + 1)
            by_id.setdefault(hit.id, hit)
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [Hit(id=i, text=by_id[i].text, score=s, metadata=by_id[i].metadata) for i, s in fused]


def _diversify(hits: list[Hit], k: int, max_per_source: int = _MAX_PER_SOURCE) -> list[Hit]:
    """Cap how many chunks any one document may contribute to the final context.

    Without this, a corpus with several dengue chunks returns several dengue
    chunks and the differential has nothing else to reason over -- the retrieval
    half of common-disease bias.
    """
    seen: dict[str, int] = {}
    kept: list[Hit] = []
    overflow: list[Hit] = []
    for hit in hits:
        key = hit.metadata.get("title") or hit.metadata.get("url") or hit.id
        if seen.get(key, 0) < max_per_source:
            seen[key] = seen.get(key, 0) + 1
            kept.append(hit)
        else:
            overflow.append(hit)
        if len(kept) >= k:
            return kept[:k]
    return (kept + overflow)[:k]


def rescore_with_evidence(
    hits: list[Hit],
    *,
    discriminator_terms: list[str],
    denied_terms: list[str],
) -> list[Hit]:
    """Nudge fused scores by the patient's own discriminating and denied features."""
    if not hits:
        return hits
    top = max(h.score for h in hits) or 1.0
    adjusted: list[Hit] = []
    for hit in hits:
        text = hit.text.lower()
        bonus = sum(_DISCRIMINATOR_BONUS for term in discriminator_terms if term.lower() in text)
        penalty = sum(_DENIED_PENALTY for term in denied_terms if term.lower() in text)
        score = (hit.score / top) + bonus - penalty
        adjusted.append(Hit(id=hit.id, text=hit.text, score=score, metadata=hit.metadata))
    return sorted(adjusted, key=lambda h: h.score, reverse=True)


async def multi_hybrid(
    collection: str,
    queries: list[tuple[str, float]],
    k: int = 10,
    *,
    where: dict | None = None,
    discriminator_terms: list[str] | None = None,
    denied_terms: list[str] | None = None,
    rerank_query: str | None = None,
    max_per_source: int = _MAX_PER_SOURCE,
) -> list[Hit]:
    """Weighted multi-query hybrid retrieval with evidence rescoring and diversity."""
    if not queries:
        return []
    store = VectorStore()
    ranked_lists: list[tuple[list[Hit], float]] = []
    for text, weight in queries:
        dense = store.query(collection, text, k=_CANDIDATES, where=where)
        sparse = _bm25_search(collection, text, _CANDIDATES)
        if where:
            allowed = {h.id for h in dense}
            sparse = [h for h in sparse if h.id in allowed]
        ranked_lists.append((dense, weight))
        ranked_lists.append((sparse, weight))

    fused = _weighted_rrf(ranked_lists)[:_CANDIDATES]
    reranked = _rerank(rerank_query or queries[0][0], fused, _CANDIDATES)
    rescored = rescore_with_evidence(
        reranked,
        discriminator_terms=discriminator_terms or [],
        denied_terms=denied_terms or [],
    )
    result = _diversify(rescored, k, max_per_source=max_per_source)
    log.info(
        "multi_hybrid",
        collection=collection,
        queries=len(queries),
        candidates=len(fused),
        returned=len(result),
        sources=[h.metadata.get("title", "")[:40] for h in result],
    )
    return result
