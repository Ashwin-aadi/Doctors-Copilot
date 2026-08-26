"""Lazy singleton access to every pretrained model, with an explicit
availability check and the §3 fallback chain baked into each getter.

Nothing here trains anything. Each getter downloads/loads on first use,
caches the instance on the Registry, and logs which tier of the fallback
chain it landed on (once, at first load).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
ML_DATA_DIR = REPO_ROOT / "ml" / "data"
CACHE_DIR = REPO_ROOT / "ml" / ".cache"

os.environ.setdefault("HF_HOME", str(CACHE_DIR))
os.environ.setdefault("TRANSFORMERS_CACHE", str(CACHE_DIR))


class OcrEngine:
    """Thin handle identifying which OCR tier is active."""

    def __init__(self, name: str, handle: Any = None) -> None:
        self.name = name
        self.handle = handle


class GazetteerNer:
    """Tier-3 NER fallback: rapidfuzz match against a seed drug/condition list."""

    def __init__(self, seed: dict[str, list[str]]) -> None:
        self.drugs = seed.get("drugs", [])
        self.conditions = seed.get("conditions", [])
        self.allergens = seed.get("allergens", [])


class Registry:
    def __init__(self) -> None:
        self._ocr_engine: OcrEngine | None = None
        self._sci_nlp: Any = None
        self._sci_nlp_unavailable = False
        self._bc5cdr: Any = None
        self._bc5cdr_unavailable = False
        self._hf_ner: Any = None
        self._hf_ner_unavailable = False
        self._gazetteer_ner: GazetteerNer | None = None
        self._logged: set[str] = set()

    def _log_once(self, key: str, **kwargs: Any) -> None:
        if key in self._logged:
            return
        self._logged.add(key)
        logger.info("ml.registry.tier_selected", component=key, **kwargs)

    # ---- OCR: PaddleOCR -> pytesseract -> PyMuPDF embedded-text layer ----
    def ocr_engine(self) -> OcrEngine:
        if self._ocr_engine is not None:
            return self._ocr_engine

        try:
            from paddleocr import PaddleOCR

            handle = PaddleOCR(lang="en", use_angle_cls=True, show_log=False)
            self._ocr_engine = OcrEngine("paddle", handle)
            self._log_once("ocr", tier="paddle")
            return self._ocr_engine
        except Exception as exc:  # noqa: BLE001
            logger.warning("ml.registry.ocr_tier_failed", tier="paddle", error=str(exc))

        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            self._ocr_engine = OcrEngine("tesseract", pytesseract)
            self._log_once("ocr", tier="tesseract")
            return self._ocr_engine
        except Exception as exc:  # noqa: BLE001
            logger.warning("ml.registry.ocr_tier_failed", tier="tesseract", error=str(exc))

        try:
            import fitz  # pymupdf

            self._ocr_engine = OcrEngine("pymupdf", fitz)
            self._log_once("ocr", tier="pymupdf")
            return self._ocr_engine
        except Exception as exc:  # noqa: BLE001
            logger.error("ml.registry.ocr_unavailable", error=str(exc))
            self._ocr_engine = OcrEngine("unavailable", None)
            return self._ocr_engine

    # ---- Biomedical NER tier 1: scispaCy en_core_sci_sm (+ negspacy) ----
    def sci_nlp(self) -> Any:
        if self._sci_nlp is not None or self._sci_nlp_unavailable:
            return self._sci_nlp
        try:
            import spacy

            nlp = spacy.load("en_core_sci_sm")
            try:

                nlp.add_pipe("negex", config={"chunk_prefix": ["no", "denies", "without"]})
            except Exception as exc:  # noqa: BLE001
                logger.warning("ml.registry.negex_unavailable", error=str(exc))
            self._sci_nlp = nlp
            self._log_once("sci_nlp", tier="en_core_sci_sm")
        except Exception as exc:  # noqa: BLE001
            logger.warning("ml.registry.sci_nlp_unavailable", error=str(exc))
            self._sci_nlp_unavailable = True
        return self._sci_nlp

    def bc5cdr(self) -> Any:
        if self._bc5cdr is not None or self._bc5cdr_unavailable:
            return self._bc5cdr
        try:
            import spacy

            self._bc5cdr = spacy.load("en_ner_bc5cdr_md")
            self._log_once("bc5cdr", tier="en_ner_bc5cdr_md")
        except Exception as exc:  # noqa: BLE001
            logger.warning("ml.registry.bc5cdr_unavailable", error=str(exc))
            self._bc5cdr_unavailable = True
        return self._bc5cdr

    # ---- Biomedical NER tier 2: HF d4data/biomedical-ner-all ----
    def hf_ner(self) -> Any:
        if self._hf_ner is not None or self._hf_ner_unavailable:
            return self._hf_ner
        try:
            from transformers import pipeline

            self._hf_ner = pipeline(
                "token-classification",
                model="d4data/biomedical-ner-all",
                aggregation_strategy="simple",
            )
            self._log_once("hf_ner", tier="d4data/biomedical-ner-all")
        except Exception as exc:  # noqa: BLE001
            logger.warning("ml.registry.hf_ner_unavailable", error=str(exc))
            self._hf_ner_unavailable = True
        return self._hf_ner

    # ---- Biomedical NER tier 3: gazetteer + rapidfuzz (always available) ----
    def gazetteer_ner(self) -> GazetteerNer | None:
        if self._gazetteer_ner is not None:
            return self._gazetteer_ner
        try:
            import rapidfuzz  # noqa: F401

            seed_path = ML_DATA_DIR / "ner_gazetteer_seed.yaml"
            seed = yaml.safe_load(seed_path.read_text()) if seed_path.exists() else {}
            self._gazetteer_ner = GazetteerNer(seed)
            self._log_once("gazetteer_ner", tier="rapidfuzz+seed")
        except Exception as exc:  # noqa: BLE001
            logger.error("ml.registry.gazetteer_ner_unavailable", error=str(exc))
        return self._gazetteer_ner

    def available(self) -> dict[str, bool]:
        ocr = self.ocr_engine()
        ner_tier_available = (
            self.sci_nlp() is not None
            or self.hf_ner() is not None
            or self.gazetteer_ner() is not None
        )
        return {
            "ocr": ocr.name != "unavailable",
            "ocr_paddle": ocr.name == "paddle",
            "ocr_tesseract": ocr.name == "tesseract",
            "ocr_pymupdf": ocr.name == "pymupdf",
            "sci_nlp": self._sci_nlp is not None,
            "bc5cdr": self._bc5cdr is not None,
            "hf_ner": self._hf_ner is not None,
            "gazetteer_ner": self._gazetteer_ner is not None,
            "ner": ner_tier_available,
        }

    def warm_up(self) -> dict[str, bool]:
        """Called from FastAPI startup to pre-load models once."""
        self.ocr_engine()
        self.sci_nlp()
        self.hf_ner()
        self.gazetteer_ner()
        return self.available()


_registry: Registry | None = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry
