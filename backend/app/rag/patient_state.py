"""Structured patient state: the single source of truth for the triage pipeline.

Every downstream stage -- retrieval, differential, red flags, ESI, rationale --
reads from a `PatientState` rather than from free text. That is the whole point:
the previous pipeline handed one raw transcript blob to one LLM call, so there
was nothing a red flag could be checked against and nothing to stop the model
inventing a finding.

State is built in two passes that are deliberately unequal in authority:

1. A deterministic lexicon pass over the patient's own turns, using
   `app.rag.negation` for scope. This decides `present` / `absent` / `unknown`
   and it is not overrulable.
2. An LLM pass that may only *add* findings, and only when it supplies a
   verbatim quote from the patient. A finding whose quote is not present in the
   patient's own words is dropped as a hallucination; a finding that contradicts
   pass 1 is discarded.

Bare "yes"/"no" answers are resolved against the question that was asked, so
"Any difficulty breathing?" -> "no" records dyspnoea as ABSENT rather than
leaving it unknown (or, as before, matching the phrase inside the question).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.llm.gateway import json_complete
from app.llm.prompts import STATE_EXTRACT_SYSTEM
from app.rag.negation import Polarity, polarity_at

log = get_logger(__name__)

_DATA_DIR = Path(__file__).parent / "data"
_LEXICON = yaml.safe_load((_DATA_DIR / "clinical_features.yaml").read_text(encoding="utf-8"))

GENERIC_SPECIFICITY = 0.25
DISCRIMINATING_SPECIFICITY = 0.60


class FeatureDef(BaseModel):
    name: str
    label: str
    category: str
    patterns: list[str]
    specificity: float = 0.4
    suggests: list[str] = []


FEATURES: dict[str, FeatureDef] = {
    f["name"]: FeatureDef(**f) for f in _LEXICON["features"]
}

_COMPILED: dict[str, list[re.Pattern[str]]] = {
    name: [re.compile(p, re.IGNORECASE) for p in f.patterns] for name, f in FEATURES.items()
}

RED_FLAG_RULES: list[dict] = _LEXICON["red_flags"]
URGENT_RULES: list[dict] = _LEXICON["urgent_rules"]
COMMON_BIAS: dict = _LEXICON["common_condition_bias"]

_AFFIRMATIVE = re.compile(
    r"^\s*(yes|yeah|yep|ya|haan|han|ji|ji haan|correct|right|true|sahi|bilkul)\b[\s.!,]*$",
    re.IGNORECASE,
)
_NEGATIVE = re.compile(
    r"^\s*(no|nope|nah|nahi|nahin|never|none|nil|not really|no it'?s not|negative)\b[\s.!,]*$",
    re.IGNORECASE,
)
_UNKNOWN_ANSWER = re.compile(
    r"^\s*(i )?(don'?t know|do not know|not sure|unsure|no idea|cannot say|can'?t say|maybe|pata nahi)\b[\s.!,]*$",
    re.IGNORECASE,
)

_DURATION = re.compile(
    r"(?:(?:for|since|about|around|nearly|almost|past|last)\s+)?"
    r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an|couple of|few)\s*"
    r"(hour|hr|day|din|week|hafta|month|mahina|year)s?",
    re.IGNORECASE,
)
_WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "couple of": 2, "few": 3,
}
_UNIT_DAYS = {
    "hour": 1 / 24, "hr": 1 / 24, "day": 1.0, "din": 1.0, "week": 7.0,
    "hafta": 7.0, "month": 30.0, "mahina": 30.0, "year": 365.0,
}

_SEVERITY_WORDS = re.compile(
    r"\b(mild|slight|little|moderate|severe|intense|terrible|unbearable|excruciating|worst|very bad|high)\b",
    re.IGNORECASE,
)


class Finding(BaseModel):
    """One clinical concept, with how it was asserted and where that came from."""

    name: str
    label: str
    category: str = "other"
    status: Polarity = "unknown"
    specificity: float = 0.4
    severity: str | None = None
    evidence: str = ""
    turn: int = -1
    source: str = "lexicon"

    @property
    def discriminating(self) -> bool:
        return self.status == "present" and self.specificity >= DISCRIMINATING_SPECIFICITY


class PatientState(BaseModel):
    """Everything the pipeline is permitted to treat as known about the patient."""

    chief_complaint: str = ""
    findings: list[Finding] = Field(default_factory=list)
    duration_days: float | None = None
    patient_words: str = ""
    turns_answered: int = 0

    # -------------------------------------------------------------- accessors
    def get(self, name: str) -> Finding | None:
        return next((f for f in self.findings if f.name == name), None)

    def status(self, name: str) -> Polarity:
        found = self.get(name)
        return found.status if found else "unknown"

    def is_present(self, name: str) -> bool:
        return self.status(name) == "present"

    def is_absent(self, name: str) -> bool:
        return self.status(name) == "absent"

    @property
    def present(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "present"]

    @property
    def absent(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "absent"]

    @property
    def unknown(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "unknown"]

    @property
    def discriminators(self) -> list[Finding]:
        """Present findings that actually narrow a differential, most specific first."""
        return sorted(
            (f for f in self.present if f.specificity >= DISCRIMINATING_SPECIFICITY),
            key=lambda f: f.specificity,
            reverse=True,
        )

    @property
    def generic(self) -> list[Finding]:
        return [f for f in self.present if f.specificity <= GENERIC_SPECIFICITY]

    def summary_lines(self) -> list[str]:
        """Compact, unambiguous rendering for prompt insertion."""
        lines: list[str] = []
        if self.chief_complaint:
            lines.append(f"Chief complaint: {self.chief_complaint}")
        if self.duration_days is not None:
            lines.append(f"Duration: {self.duration_days:g} day(s)")
        for f in sorted(self.present, key=lambda f: -f.specificity):
            sev = f" ({f.severity})" if f.severity else ""
            lines.append(f"PRESENT: {f.label}{sev}")
        for f in self.absent:
            lines.append(f"EXPLICITLY DENIED: {f.label}")
        for f in self.unknown:
            lines.append(f"NOT ASSESSED / UNCERTAIN: {f.label}")
        return lines

    def as_prompt_block(self) -> str:
        return "\n".join(self.summary_lines()) or "No findings recorded."


# ------------------------------------------------------------ pass 1: lexicon


def _question_features(question: str) -> list[str]:
    """Which lexicon features an assistant question is asking about."""
    hits: list[str] = []
    for name, patterns in _COMPILED.items():
        if any(p.search(question) for p in patterns):
            hits.append(name)
    return hits


def _parse_duration(text: str) -> float | None:
    best: float | None = None
    for match in _DURATION.finditer(text):
        raw, unit = match.group(1).lower(), match.group(2).lower()
        value = _WORD_NUMBERS.get(raw)
        if value is None:
            try:
                value = int(raw)
            except ValueError:
                continue
        days = value * _UNIT_DAYS[unit]
        if best is None or days > best:
            best = days
    return best


def _severity_near(text: str, span: tuple[int, int]) -> str | None:
    window = text[max(0, span[0] - 40) : span[1] + 20]
    match = _SEVERITY_WORDS.search(window)
    return match.group(1).lower() if match else None


def _resolve_matches(content: str) -> list[tuple[str, tuple[int, int], Polarity]]:
    """Match every feature in one utterance, resolving overlaps by specificity.

    Feature phrases nest: "blood in vomit" contains "vomit", "chronic cough"
    contains "cough". Without this step, "no blood in vomit" recorded plain
    `vomiting` as ABSENT and wiped out an earlier "yes, I vomited".

    Suppression is scoped to the case that actually matters -- polarity. A
    contained feature is dropped only when the phrase containing it is DENIED,
    because the denial belongs to the specific phrase and not to its parts. When
    the containing phrase is asserted, both are true: "fever going up each day"
    is stepladder fever *and* fever, and dropping the latter used to lose the
    duration rules that key off it.
    """
    raw: list[tuple[str, tuple[int, int], Polarity, float, int]] = []
    for name, patterns in _COMPILED.items():
        spec = FEATURES[name]
        for pattern in patterns:
            match = pattern.search(content)
            if match is None:
                continue
            span = match.span()
            raw.append((name, span, polarity_at(content, span), spec.specificity, span[1] - span[0]))
            break

    # Longest match first, then most specific: those win their span.
    raw.sort(key=lambda r: (r[4], r[3]), reverse=True)
    kept: list[tuple[str, tuple[int, int], Polarity]] = []
    claimed: list[tuple[tuple[int, int], Polarity]] = []
    for name, span, status, _specificity, _length in raw:
        container = next(
            (
                claimed_status
                for (start, end), claimed_status in claimed
                if start <= span[0] and span[1] <= end
            ),
            None,
        )
        if container == "absent":
            log.debug("feature_match_suppressed_by_denied_container", feature=name, span=span)
            continue
        claimed.append((span, status))
        kept.append((name, span, status))
    return kept


def _upsert(findings: dict[str, Finding], candidate: Finding) -> None:
    """Merge a candidate into the accumulating state.

    Later turns win over earlier ones, because a patient correcting themselves
    ("actually yes, a little") should update the record. A definite assertion
    (present/absent) always wins over `unknown` regardless of order.
    """
    existing = findings.get(candidate.name)
    if existing is None:
        findings[candidate.name] = candidate
        return
    if candidate.status == "unknown" and existing.status != "unknown":
        return
    if candidate.turn >= existing.turn:
        candidate.severity = candidate.severity or existing.severity
        findings[candidate.name] = candidate


def extract_deterministic(transcript: list[dict]) -> PatientState:
    """Lexicon + negation pass over the patient's turns. Never uses the LLM."""
    findings: dict[str, Finding] = {}
    patient_turns: list[str] = []
    chief_complaint = ""
    duration: float | None = None
    last_question = ""

    for index, turn in enumerate(transcript):
        content = (turn.get("content") or "").strip()
        role = turn.get("role")
        if role == "assistant":
            last_question = content
            continue
        if not content:
            continue
        patient_turns.append(content)
        if not chief_complaint:
            chief_complaint = content[:240]

        found_duration = _parse_duration(content)
        if found_duration is not None and (duration is None or found_duration > duration):
            duration = found_duration

        # A bare yes/no/unknown answers the previous question, not itself.
        answer_polarity: Polarity | None = None
        if _NEGATIVE.match(content):
            answer_polarity = "absent"
        elif _AFFIRMATIVE.match(content):
            answer_polarity = "present"
        elif _UNKNOWN_ANSWER.match(content):
            answer_polarity = "unknown"

        if answer_polarity is not None and last_question:
            for name in _question_features(last_question):
                spec = FEATURES[name]
                _upsert(
                    findings,
                    Finding(
                        name=name,
                        label=spec.label,
                        category=spec.category,
                        status=answer_polarity,
                        specificity=spec.specificity,
                        evidence=f"Q: {last_question[:120]} / A: {content[:40]}",
                        turn=index,
                        source="answer",
                    ),
                )
            continue

        for name, span, status in _resolve_matches(content):
            spec = FEATURES[name]
            _upsert(
                findings,
                Finding(
                    name=name,
                    label=spec.label,
                    category=spec.category,
                    status=status,
                    specificity=spec.specificity,
                    severity=_severity_near(content, span) if status == "present" else None,
                    evidence=content[max(0, span[0] - 40) : span[1] + 40].strip(),
                    turn=index,
                    source="lexicon",
                ),
            )

    return PatientState(
        chief_complaint=chief_complaint,
        findings=list(findings.values()),
        duration_days=duration,
        patient_words="\n".join(patient_turns),
        turns_answered=len(patient_turns),
    )


# ---------------------------------------------------------------- pass 2: LLM


class _LlmFinding(BaseModel):
    label: str = ""
    status: Polarity = "unknown"
    evidence_quote: str = ""


class _LlmState(BaseModel):
    chief_complaint: str = ""
    findings: list[_LlmFinding] = []


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def _quote_is_grounded(quote: str, patient_words: str) -> bool:
    """A quote counts as grounded only if the patient actually said it.

    Compared on normalised text so punctuation and casing do not matter, but
    the words themselves must be contiguous in the patient's own turns. This is
    the single check that stops the model contributing invented symptoms.
    """
    quote_norm = " ".join(_normalise(quote).split())
    if len(quote_norm) < 4:
        return False
    return quote_norm in " ".join(_normalise(patient_words).split())


async def _extract_llm(state: PatientState) -> list[Finding]:
    """Ask the model for findings the lexicon has no pattern for.

    Everything it returns is filtered: quote must be verbatim, and a feature the
    deterministic pass already decided cannot be changed.
    """
    if not state.patient_words.strip():
        return []
    prompt = (
        "Patient's own words, turn by turn:\n"
        f"{state.patient_words}\n\n"
        "Findings already extracted deterministically (do not repeat or contradict "
        "these):\n"
        f"{state.as_prompt_block()}\n\n"
        "List any ADDITIONAL clinical findings the patient stated. For each, give "
        "the status and a verbatim quote copied character-for-character from the "
        "patient's words above."
    )
    try:
        raw = await json_complete(prompt, schema=_LlmState, system=STATE_EXTRACT_SYSTEM)
    except Exception as exc:  # noqa: BLE001
        log.warning("state_llm_extract_failed", error=str(exc))
        return []

    known_labels = {f.label.lower() for f in state.findings}
    extra: list[Finding] = []
    for item in raw.findings:
        label = item.label.strip()
        if not label or label.lower() in known_labels:
            continue
        if not _quote_is_grounded(item.evidence_quote, state.patient_words):
            log.info("state_finding_dropped_ungrounded", label=label, quote=item.evidence_quote[:80])
            continue
        # Re-derive polarity from the quote itself rather than trusting the model.
        status = item.status
        quote_index = _normalise(state.patient_words).find(_normalise(item.evidence_quote).strip()[:30])
        if quote_index >= 0:
            derived = polarity_at(
                state.patient_words, (quote_index, quote_index + len(item.evidence_quote))
            )
            if derived == "absent":
                status = "absent"
        extra.append(
            Finding(
                name=re.sub(r"\W+", "_", label.lower()).strip("_"),
                label=label,
                category="other",
                status=status,
                specificity=0.45,
                evidence=item.evidence_quote,
                source="llm",
            )
        )
    return extra


async def build_state(transcript: list[dict], *, use_llm: bool = True) -> PatientState:
    """Full two-pass state build. The deterministic pass always wins conflicts."""
    state = extract_deterministic(transcript)
    if use_llm:
        for finding in await _extract_llm(state):
            if state.get(finding.name) is None:
                state.findings.append(finding)
    log.info(
        "patient_state_built",
        present=[f.name for f in state.present],
        absent=[f.name for f in state.absent],
        discriminators=[f.name for f in state.discriminators],
        duration_days=state.duration_days,
    )
    return state
