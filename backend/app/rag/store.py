"""Chroma-backed vector store shared across triage, clinical, and patient-chat RAG."""

from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rag.embeddings import embed_clinical, embed_general

log = get_logger(__name__)
settings = get_settings()

REQUIRED_METADATA_KEYS = {"source", "title", "url", "section", "doc_type", "published"}


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Hit:
    id: str
    text: str
    score: float
    metadata: dict = field(default_factory=dict)


def _embed_fn(collection: str, texts: list[str]) -> list[list[float]]:
    return embed_clinical(texts) if collection == "clinical" else embed_general(texts)


@lru_cache
def _client():
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    return chromadb.PersistentClient(
        path=settings.chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


class VectorStore:
    def _collection(self, collection: str):
        return _client().get_or_create_collection(name=collection)

    def upsert(self, collection: str, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        for chunk in chunks:
            missing = REQUIRED_METADATA_KEYS - chunk.metadata.keys()
            if missing:
                raise ValueError(f"chunk {chunk.id} missing metadata keys: {missing}")
        vectors = _embed_fn(collection, [c.text for c in chunks])
        coll = self._collection(collection)
        coll.upsert(
            ids=[c.id for c in chunks],
            embeddings=vectors,
            documents=[c.text for c in chunks],
            metadatas=[
                {k: ("" if v is None else v) for k, v in c.metadata.items()} for c in chunks
            ],
        )

    def query(self, collection: str, text: str, k: int = 8, where: dict | None = None) -> list[Hit]:
        coll = self._collection(collection)
        if coll.count() == 0:
            return []
        vector = _embed_fn(collection, [text])[0]
        res = coll.query(
            query_embeddings=[vector],
            n_results=min(k, coll.count()),
            where=where,
        )
        hits: list[Hit] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for i, doc, meta, dist in zip(ids, docs, metas, dists, strict=True):
            hits.append(Hit(id=i, text=doc, score=1.0 - dist, metadata=dict(meta)))
        return hits

    def reset(self, collection: str) -> None:
        """Drop a collection so an ingest is a rebuild rather than a merge.

        Upsert alone leaves stale chunks behind whenever chunk ids shift -- for
        example when a content-quality filter starts rejecting boilerplate, the
        boilerplate already in the store would survive under its old ids.
        """
        try:
            _client().delete_collection(name=collection)
        except Exception as exc:  # noqa: BLE001
            log.info("collection_reset_skipped", collection=collection, error=str(exc))

    def count(self, collection: str) -> int:
        return self._collection(collection).count()
