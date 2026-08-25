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
