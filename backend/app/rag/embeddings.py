"""Singleton embedding model loaders with a disk cache keyed on sha1(text)+model."""

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
settings = get_settings()

os.environ.setdefault("HF_HOME", settings.hf_home)

_CACHE_DIR = Path(settings.hf_home) / "embed_cache"


@lru_cache
def _general_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embed_model_general)


@lru_cache
def _clinical_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embed_model_clinical)


def _cache_path(model_name: str, text: str) -> Path:
    key = hashlib.sha1(f"{model_name}:{text}".encode()).hexdigest()
    return _CACHE_DIR / f"{key}.json"


def _embed(model_name: str, model, texts: list[str]) -> list[list[float]]:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    results: list[list[float] | None] = [None] * len(texts)
    misses: list[int] = []
    for i, text in enumerate(texts):
        path = _cache_path(model_name, text)
        if path.exists():
            try:
                results[i] = json.loads(path.read_text(encoding="utf-8"))
                continue
            except (json.JSONDecodeError, OSError):
                pass
        misses.append(i)
    if misses:
        vectors = model.encode([texts[i] for i in misses], batch_size=32, convert_to_numpy=True)
        for idx, vec in zip(misses, vectors, strict=True):
            v = vec.tolist()
            results[idx] = v
            try:
                _cache_path(model_name, texts[idx]).write_text(json.dumps(v), encoding="utf-8")
            except OSError as exc:
                log.warning("embed_cache_write_failed", error=str(exc))
    return results  # type: ignore[return-value]


def embed_general(texts: list[str]) -> list[list[float]]:
    return _embed(settings.embed_model_general, _general_model(), texts)


def embed_clinical(texts: list[str]) -> list[list[float]]:
    return _embed(settings.embed_model_clinical, _clinical_model(), texts)
