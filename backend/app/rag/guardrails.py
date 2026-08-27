"""Four safety passes applied to every generated clinical or patient-facing
output.

1. `redact_pii`   -- names, phone numbers, emails, ABHA/Aadhaar-shaped ids and
                     record UUIDs are replaced with stable placeholders BEFORE
                     the text reaches the LLM, and put back afterwards. The
                     model never sees who the patient is.
2. `validate_citations` -- any sentence carrying a `[n]` marker that does not
                     resolve to a retrieved hit is dropped, not merely flagged.
3. `faithfulness` -- each claim sentence is scored by the cross-encoder against
                     the chunk it cites. Below 0.35 the sentence is removed; the
                     mean of what survives becomes the response `confidence`.
4. `emergency_intercept` -- ESI <= 2 or a red flag escalates the patient's queue
                     entry and prepends an emergency banner marker.

Everything here degrades safely: if the cross-encoder or the queue service is
unavailable, output is kept but confidence drops, never the other way round.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from uuid import UUID

from app.core.logging import get_logger
from app.rag.store import Hit

log = get_logger(__name__)

FAITHFULNESS_FLOOR = 0.35
EMERGENCY_BANNER = "[[EMERGENCY]]"
SCOPE_REFUSAL_MARKER = "SCOPE_REFUSAL"

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")
_CITATION = re.compile(r"\[(\d+)\]")

# --------------------------------------------------------------- pass 1: PII

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    # Indian mobile numbers, with or without the +91 country code.
    ("PHONE", re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{9}\b")),
    ("UUID", re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")),
    # ABHA (14 digits, usually spaced 2-4-4-4) and Aadhaar (12 digits, 4-4-4).
    ("ABHA", re.compile(r"\b\d{2}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")),
    ("AADHAAR", re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")),
]


@dataclass
class PiiMap:
    """Placeholder -> original value, for reinsertion after the LLM call."""

    values: dict[str, str] = field(default_factory=dict)

    def restore(self, text: str) -> str:
        for placeholder, original in self.values.items():
            text = text.replace(placeholder, original)
        return text


def redact_pii(text: str, *, names: list[str] | None = None) -> tuple[str, PiiMap]:
    """Strip identifiers out of `text`, returning the redacted text and a map.

    `names` lets a caller redact values the regexes cannot possibly know are
    identifying -- the patient's own name, the doctor's name.
    """

    mapping = PiiMap()
    counters: dict[str, int] = {}

    def _placeholder(kind: str, value: str) -> str:
        for existing, original in mapping.values.items():
            if original == value:
                return existing
        counters[kind] = counters.get(kind, 0) + 1
        token = f"<{kind}_{counters[kind]}>"
        mapping.values[token] = value
        return token

    for name in sorted(filter(None, names or []), key=len, reverse=True):
        pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
        if pattern.search(text):
            text = pattern.sub(_placeholder("NAME", name), text)

    for kind, pattern in _PII_PATTERNS:
        text = pattern.sub(lambda m, k=kind: _placeholder(k, m.group(0)), text)

    return text, mapping


# --------------------------------------------------------- pass 2: citations


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def cited_markers(text: str) -> set[int]:
    """The `[n]` markers a piece of text actually uses."""

    return {int(n) for n in _CITATION.findall(text)}


def validate_citations(text: str, hits: list[Hit]) -> str:
    """Drop every sentence whose `[n]` marker points outside the retrieved set.

    Sentences with no marker at all are kept -- they carry no citation claim.
    """

    allowed = set(range(1, len(hits) + 1))
    kept: list[str] = []
    for sentence in _split_sentences(text):
        markers = {int(m) for m in _CITATION.findall(sentence)}
        if markers and not markers.issubset(allowed):
            log.info("citation_stripped", sentence=sentence[:120], markers=sorted(markers))
            continue
        kept.append(sentence)
    return " ".join(kept)


# ------------------------------------------------------ pass 3: faithfulness


@lru_cache
def _cross_encoder():
    from sentence_transformers import CrossEncoder

    from app.core.config import get_settings

    return CrossEncoder(get_settings().rerank_model)


def _cited_chunk(sentence: str, hits: list[Hit]) -> str | None:
    markers = [int(m) for m in _CITATION.findall(sentence)]
    texts = [hits[n - 1].text for n in markers if 1 <= n <= len(hits)]
    return " ".join(texts) if texts else None


def faithfulness(text: str, hits: list[Hit]) -> float:
    """Mean cross-encoder support score across the text's cited sentences.

    Returns 0.0 when nothing is cited. When the scorer itself is unavailable it
    returns the floor rather than 1.0 -- callers keep the text but must not
    claim high confidence in it.
    """

    scored = _score_sentences(text, hits)
    if scored is None:
        return FAITHFULNESS_FLOOR
    if not scored:
        return 0.0
    return sum(score for _, score in scored) / len(scored)


def _score_sentences(text: str, hits: list[Hit]) -> list[tuple[str, float]] | None:
    pairs: list[tuple[str, str]] = []
    sentences: list[str] = []
    for sentence in _split_sentences(text):
        chunk = _cited_chunk(sentence, hits)
        if chunk is None:
            continue
        sentences.append(sentence)
        pairs.append((sentence, chunk))
    if not pairs:
        return []
    try:
        raw = _cross_encoder().predict(pairs)
    except Exception as exc:  # noqa: BLE001
        log.warning("faithfulness_scorer_unavailable", error=str(exc))
        return None
    return [(s, _normalize(float(v))) for s, v in zip(sentences, raw, strict=True)]


def _normalize(score: float) -> float:
    """Cross-encoder logits are unbounded; squash to 0..1 so the 0.35 floor
    means the same thing whichever rerank model is configured."""

    import math

    return 1.0 / (1.0 + math.exp(-score))


def filter_unfaithful(text: str, hits: list[Hit]) -> tuple[str, float]:
    """Remove poorly supported cited sentences and report mean support.

    Uncited sentences (greetings, the "discuss with your doctor" closer) are
    kept verbatim and excluded from the score.
    """

    scored = _score_sentences(text, hits)
    if scored is None:
        return text, FAITHFULNESS_FLOOR

    dropped = {s for s, score in scored if score < FAITHFULNESS_FLOOR}
    survivors = [score for _, score in scored if score >= FAITHFULNESS_FLOOR]

    kept = [s for s in _split_sentences(text) if s not in dropped]
    if dropped:
        log.info("unfaithful_sentences_dropped", count=len(dropped))

    confidence = sum(survivors) / len(survivors) if survivors else 0.0
    return " ".join(kept), confidence


# ---------------------------------------------------- pass 4: emergency path


async def emergency_intercept(
    *,
    severity_esi: int | None,
    red_flags: list[str] | None = None,
    queue_entry_id: UUID | None = None,
    text: str = "",
) -> tuple[str, bool]:
    """Escalate the queue entry and prepend an emergency banner marker.

    Returns `(text, escalated)`. Escalation failure never blocks the response:
    the banner is still shown to the patient, which is the part that actually
    protects them.
    """

    flags = [f for f in (red_flags or []) if f]
    is_emergency = (severity_esi is not None and severity_esi <= 2) or bool(flags)
    if not is_emergency:
        return text, False

    escalated = False
    if queue_entry_id is not None:
        try:
            from datetime import UTC, datetime

            from app.services.queueing.escalation import escalate_with_referral

            reason = flags[0] if flags else f"triage severity ESI {severity_esi}"
            await escalate_with_referral(queue_entry_id, reason, now=datetime.now(UTC))
            escalated = True
        except Exception as exc:  # noqa: BLE001
            log.warning("emergency_escalation_failed", entry=str(queue_entry_id), error=str(exc))

    banner = (
        f"{EMERGENCY_BANNER} This needs urgent medical attention. Go to the nearest "
        "casualty or emergency department now, or call 112 (108 for an ambulance)."
    )
    log.info(
        "emergency_intercepted",
        severity_esi=severity_esi,
        red_flags=len(flags),
        escalated=escalated,
    )
    return f"{banner}\n\n{text}".strip(), escalated


# ------------------------------------------------------------------ pipeline


def apply_all(text: str, hits: list[Hit]) -> tuple[str, float]:
    """Passes 2 and 3 in order, returning cleaned text and its confidence.

    Pass 1 runs before the LLM call (see `redact_pii`, whose `PiiMap.restore`
    puts the real values back afterwards) and pass 4 runs on the triage/queue
    path, so neither belongs in this post-generation pipeline.
    """

    return filter_unfaithful(validate_citations(text, hits), hits)
