"""Clinical NER: drugs, conditions, allergens with negation/historical status.

Pipeline: scispaCy `en_core_sci_sm` (generic biomedical entities, used only
to backfill spans bc5cdr misses) + `en_ner_bc5cdr_md` (CHEMICAL/DISEASE,
primary tier) -> merge overlapping spans by longest-match then higher
per-tier confidence -> cue-window negation/historical/allergy-context
classification (falls back to the same cue lists documented in
`ml/data/negation_cues.yaml` when negex isn't available) -> dose regex on
drug entities -> Indian brand-to-generic resolution -> RxCUI linking.

Falls back through the registry's tiers (bc5cdr/sci_nlp -> HF biomedical-ner
-> gazetteer) so extraction never raises for a missing model.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import yaml

from app.ml.registry import get_registry
from app.ml.schemas_ml import AllergenEntity, ConditionEntity, DoseInfo, DrugEntity, EntityBundle

DATA_DIR = Path(__file__).resolve().parents[3] / "ml" / "data"

DOSE_RE = re.compile(
    r"(?P<amount>\d+\.?\d*)\s*(?P<unit>mg|mcg|g|ml|iu|units?)\b"
    r"(?:\s*(?P<freq>od|bd|tds|qid|q\d+h|daily|twice daily|prn))?",
    re.IGNORECASE,
)

ALLERGY_CUES = [
    "allergic to", "allergy to", "allergies:", "allergies to", "adverse reaction to",
    "hypersensitive to", "hypersensitivity to",
]
HISTORICAL_CUES = [
    "history of", "h/o", "past history of", "previously", "discontinued", "stopped", "prior",
]
CONDITION_STOPWORDS = {"allergic", "allergy", "allergies"}
NEGATION_WINDOW = 6

BC5CDR_CONFIDENCE = 0.9
SCI_NLP_CONFIDENCE = 0.7
GAZETTEER_CONFIDENCE = 0.55


def _load_negation_cues() -> dict[str, list[str]]:
    path = DATA_DIR / "negation_cues.yaml"
    if not path.exists():
        return {"pre_cues": [], "post_cues": [], "termination_cues": []}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_BRAND_MAP: dict[str, str] | None = None
_RXCUI_MAP: dict[str, str] | None = None


def _load_brand_map() -> dict[str, str]:
    global _BRAND_MAP
    if _BRAND_MAP is not None:
        return _BRAND_MAP
    mapping: dict[str, str] = {}
    path = DATA_DIR / "india_brands.csv"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                mapping[row["brand"].strip().lower()] = row["ingredient"].strip().lower()
    _BRAND_MAP = mapping
    return mapping


def _load_rxcui_map() -> dict[str, str]:
    global _RXCUI_MAP
    if _RXCUI_MAP is not None:
        return _RXCUI_MAP
    mapping: dict[str, str] = {}
    path = DATA_DIR / "rxcui_lookup.csv"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("rxcui"):
                    mapping[row["name"].strip().lower()] = row["rxcui"].strip()
    _RXCUI_MAP = mapping
    return mapping


def brand_to_generic(name: str) -> str:
    """First ingredient of a combo, or the name itself if not a known brand."""
    ingredient = _load_brand_map().get(name.strip().lower())
    if ingredient is None:
        return name.strip().lower()
    return ingredient.split("+")[0].strip()


def resolve_rxcui(generic_name: str) -> str | None:
    key = generic_name.strip().lower()
    try:
        from app.services.mapping.rxnorm import lookup_rxcui  # type: ignore[import-not-found]

        rxcui = lookup_rxcui(key)
        if rxcui:
            return rxcui
    except Exception:  # noqa: BLE001 - optional teammate module, may not exist yet
        pass
    return _load_rxcui_map().get(key)


class _Span:
    __slots__ = ("start_char", "end_char", "start_tok", "end_tok", "text", "label", "confidence")

    def __init__(self, start_char, end_char, start_tok, end_tok, text, label, confidence):
        self.start_char = start_char
        self.end_char = end_char
        self.start_tok = start_tok
        self.end_tok = end_tok
        self.text = text
        self.label = label
        self.confidence = confidence


def _looks_like_dose_or_noise(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) <= 3 and stripped.isupper():
        return True  # dose-frequency abbreviations: BD, OD, TDS, QID
    return False


def _spans_from_doc(doc: Any, label_map: dict[str, str], confidence: float) -> list[_Span]:
    spans = []
    for ent in doc.ents:
        label = label_map.get(ent.label_)
        if label is None or _looks_like_dose_or_noise(ent.text):
            continue
        spans.append(
            _Span(ent.start_char, ent.end_char, ent.start, ent.end, ent.text, label, confidence)
        )
    return spans


def _merge_spans(spans: list[_Span]) -> list[_Span]:
    """Longest-match first, then higher confidence; drop char-overlaps."""
    ordered = sorted(spans, key=lambda s: (-(s.end_char - s.start_char), -s.confidence))
    kept: list[_Span] = []
    for span in ordered:
        if any(not (span.end_char <= k.start_char or span.start_char >= k.end_char) for k in kept):
            continue
        kept.append(span)
    return sorted(kept, key=lambda s: s.start_char)


def _window_text(doc: Any, start_tok: int, tokens_before: int = NEGATION_WINDOW) -> str:
    lo = max(0, start_tok - tokens_before)
    return doc[lo:start_tok].text.lower()


def _has_cue(window: str, cues: list[str]) -> bool:
    return any(cue in window for cue in cues)


def _cue_window(doc: Any, span: _Span, tokens_before: int = NEGATION_WINDOW) -> str:
    """Pre-entity token window plus the entity's own text.

    A merged span can absorb the cue phrase itself (e.g. a broader NER model
    tags "History of type 2 diabetes" as one entity), so cue lookup has to
    cover the entity text too, not just what precedes it.
    """
    pre = _window_text(doc, span.start_tok, tokens_before)
    return f"{pre} {span.text.lower()}"


def _classify_negation(doc: Any, span: _Span, negation_cues: dict[str, list[str]]) -> bool:
    window = _cue_window(doc, span)
    pre_cues = negation_cues.get("pre_cues", [])
    if not _has_cue(window, pre_cues):
        return False
    termination_cues = negation_cues.get("termination_cues", [])
    # If a termination word appears between the cue and the entity, treat as cancelled.
    last_cue_pos = max((window.rfind(c) for c in pre_cues if c in window), default=-1)
    tail = window[last_cue_pos:] if last_cue_pos >= 0 else window
    return not _has_cue(tail, termination_cues)


def _classify_historical(doc: Any, span: _Span) -> bool:
    return _has_cue(_cue_window(doc, span), HISTORICAL_CUES)


def _classify_allergy_context(doc: Any, span: _Span) -> bool:
    pre = _window_text(doc, span.start_tok, tokens_before=5)
    return _has_cue(pre, ALLERGY_CUES)


def _extract_dose(text: str, span: _Span, next_start: int | None) -> DoseInfo | None:
    window_end = next_start if next_start is not None else min(len(text), span.end_char + 40)
    window = text[span.end_char : window_end]
    match = DOSE_RE.search(window)
    if not match:
        return None
    return DoseInfo(
        amount=float(match.group("amount")),
        unit=match.group("unit").lower(),
        frequency=(match.group("freq") or "").upper() or None,
    )


async def extract(text: str) -> EntityBundle:
    registry = get_registry()
    negation_cues = _load_negation_cues()

    spans: list[_Span] = []
    tier = "unavailable"

    bc5cdr = registry.bc5cdr()
    if bc5cdr is not None:
        doc = bc5cdr(text)
        spans.extend(_spans_from_doc(doc, {"CHEMICAL": "drug", "DISEASE": "condition"}, BC5CDR_CONFIDENCE))
        tier = "bc5cdr"

    sci_nlp = registry.sci_nlp()
    doc_for_windows = None
    if sci_nlp is not None:
        doc_for_windows = sci_nlp(text)
        spans.extend(_spans_from_doc(doc_for_windows, {"ENTITY": "condition"}, SCI_NLP_CONFIDENCE))
        if tier == "unavailable":
            tier = "sci_nlp"
    if doc_for_windows is None:
        # Reuse bc5cdr's doc for token windows if scispaCy small model unavailable.
        doc_for_windows = bc5cdr(text) if bc5cdr is not None else None

    if not spans:
        gazetteer = registry.gazetteer_ner()
        if gazetteer is not None:
            tier = "gazetteer"
            lowered = text.lower()
            for word_list, label in (
                (gazetteer.drugs, "drug"),
                (gazetteer.conditions, "condition"),
                (gazetteer.allergens, "allergen"),
            ):
                for term in word_list:
                    idx = lowered.find(term.lower())
                    if idx == -1:
                        continue
                    spans.append(
                        _Span(idx, idx + len(term), 0, 0, text[idx : idx + len(term)], label, GAZETTEER_CONFIDENCE)
                    )

    merged = _merge_spans(spans)

    drugs: list[DrugEntity] = []
    conditions: list[ConditionEntity] = []
    allergens: list[AllergenEntity] = []

    for i, span in enumerate(merged):
        next_start = merged[i + 1].start_char if i + 1 < len(merged) else None
        if doc_for_windows is not None:
            negated = _classify_negation(doc_for_windows, span, negation_cues)
            historical = _classify_historical(doc_for_windows, span)
            in_allergy_context = _classify_allergy_context(doc_for_windows, span)
        else:
            negated = False
            historical = False
            in_allergy_context = False

        if span.label == "condition":
            lowered = span.text.strip().lower()
            if lowered in CONDITION_STOPWORDS:
                continue
            conditions.append(
                ConditionEntity(
                    text=span.text,
                    start=span.start_char,
                    end=span.end_char,
                    negated=negated,
                    historical=historical,
                    confidence=span.confidence,
                )
            )
        elif span.label == "drug":
            generic = brand_to_generic(span.text)
            rxcui = resolve_rxcui(generic)
            if in_allergy_context:
                allergens.append(
                    AllergenEntity(
                        text=span.text,
                        start=span.start_char,
                        end=span.end_char,
                        generic_name=generic,
                        rxcui=rxcui,
                        negated=negated,
                        confidence=span.confidence,
                    )
                )
            else:
                drugs.append(
                    DrugEntity(
                        text=span.text,
                        start=span.start_char,
                        end=span.end_char,
                        generic_name=generic,
                        rxcui=rxcui,
                        dose=_extract_dose(text, span, next_start),
                        negated=negated,
                        historical=historical,
                        confidence=span.confidence,
                    )
                )
        elif span.label == "allergen":
            generic = brand_to_generic(span.text)
            allergens.append(
                AllergenEntity(
                    text=span.text,
                    start=span.start_char,
                    end=span.end_char,
                    generic_name=generic,
                    rxcui=resolve_rxcui(generic),
                    negated=negated,
                    confidence=span.confidence,
                )
            )

    return EntityBundle(drugs=drugs, conditions=conditions, allergens=allergens, ner_tier=tier)
