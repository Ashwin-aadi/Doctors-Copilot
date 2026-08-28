"""Deterministic red-flag, ESI and consistency logic over a `PatientState`.

This module exists so that the urgency decision has a single, inspectable
owner. Previously the ESI came from the LLM, was silently clamped to 2 whenever
a red-flag regex fired anywhere in the transcript, and the rationale was
generated independently -- which is exactly how a note ends up saying
"ESI 2, critical" and "no immediate life-threatening signs" in the same breath.

Rules here:

* A red flag requires every one of its features to be asserted PRESENT in the
  state. A denied or unassessed feature can never raise a flag.
* The rule engine sets the band the severity is allowed to fall in. The LLM may
  propose a value inside that band, but it can neither de-escalate below a fired
  rule nor escalate to an emergency level without one. A red flag decides the
  severity outright.
* `check_consistency` is run on the assembled result and repairs, rather than
  merely reports, contradictions between severity, red flags and rationale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.logging import get_logger
from app.rag.negation import polarity_at
from app.rag.patient_state import (
    _COMPILED,
    COMMON_BIAS,
    RED_FLAG_RULES,
    URGENT_RULES,
    PatientState,
)

log = get_logger(__name__)

# Language that asserts an emergency. If none of the deterministic rules fired,
# none of this may appear in the rationale.
_EMERGENCY_LANGUAGE = re.compile(
    r"\b(critical|life[- ]threatening|immediate(ly)? (life|resuscitat|emergen)|"
    r"resuscitat\w*|emergency department now|needs? immediate emergency|"
    r"imminent|peri[- ]arrest|code blue|crash)\w*",
    re.IGNORECASE,
)
# Language that asserts safety. If a red flag DID fire, none of this may appear.
_REASSURANCE_LANGUAGE = re.compile(
    r"(no (immediate |acute )?(life[- ]threatening|red[- ]?flag|emergency|danger)"
    r"[a-z ]*(sign|feature|symptom)?s?|"
    r"does not (appear|seem) (to be )?(an )?(emergency|urgent)|"
    r"esi ?[12] is not indicated|not an emergency|no urgent concern)",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class RedFlag:
    """A fired rule, carrying the evidence that fired it."""

    id: str
    text: str
    esi: int
    evidence: list[str]

    def render(self) -> str:
        return f"{self.text} ({'; '.join(self.evidence)})" if self.evidence else self.text


@dataclass
class SeverityDecision:
    esi: int
    floor: int
    ceiling: int
    red_flags: list[RedFlag]
    urgent_reasons: list[str]
    basis: str


def _rule_satisfied(rule: dict, state: PatientState) -> tuple[bool, list[str]]:
    evidence: list[str] = []
    for name in rule.get("all_of", []):
        finding = state.get(name)
        if finding is None or finding.status != "present":
            return False, []
        evidence.append(finding.label)

    any_of = rule.get("any_of", [])
    if any_of:
        matched = [state.get(n) for n in any_of]
        matched = [f for f in matched if f is not None and f.status == "present"]
        if not matched:
            return False, []
        evidence.extend(f.label for f in matched)

    qualifiers = rule.get("any_of_text", [])
    if qualifiers:
        # The qualifier must appear in the patient's own words AND not be negated.
        # Checking the raw text alone was how "no difficulty breathing" used to
        # satisfy a breathing rule.
        hit = None
        for qualifier in qualifiers:
            for match in re.finditer(re.escape(qualifier), state.patient_words, re.IGNORECASE):
                if polarity_at(state.patient_words, match.span()) == "present":
                    hit = qualifier
                    break
            if hit:
                break
        if hit is None:
            return False, []
        evidence.append(f"described as {hit}")

    min_severity = rule.get("min_severity")
    if min_severity is not None:
        severe = {"severe", "intense", "terrible", "unbearable", "excruciating", "worst"}
        names = set(rule.get("all_of", [])) | set(rule.get("any_of", []))
        graded = [
            f for f in state.present
            if f.name in names and (f.severity or "") in severe
        ]
        if not graded:
            return False, []
        evidence.extend(f"{f.label} described as {f.severity}" for f in graded)

    min_days = rule.get("min_duration_days")
    if min_days is not None:
        if state.duration_days is None or state.duration_days < min_days:
            return False, []
        evidence.append(f"{state.duration_days:g} days")

    return True, evidence


def detect_red_flags(state: PatientState) -> list[RedFlag]:
    """Every red-flag rule whose features are all PRESENT in the state."""
    flags: list[RedFlag] = []
    for rule in RED_FLAG_RULES:
        satisfied, evidence = _rule_satisfied(rule, state)
        if satisfied:
            flags.append(RedFlag(id=rule["id"], text=rule["text"], esi=int(rule["esi"]), evidence=evidence))
    return sorted(flags, key=lambda f: f.esi)


def detect_urgent(state: PatientState) -> list[tuple[str, int]]:
    """Concerning-but-not-emergency combinations that justify ESI 3."""
    out: list[tuple[str, int]] = []
    for rule in URGENT_RULES:
        satisfied, _ = _rule_satisfied(rule, state)
        if satisfied:
            out.append((rule["text"], int(rule["esi"])))
    return out


def decide_severity(state: PatientState, llm_esi: int | None = None) -> SeverityDecision:
    """Combine rule evidence with an optional LLM proposal inside hard bounds."""
    red_flags = detect_red_flags(state)
    urgent = detect_urgent(state)

    if red_flags:
        # The most urgent fired rule decides outright; the model gets no say.
        floor = min(f.esi for f in red_flags)
        return SeverityDecision(
            esi=floor,
            floor=floor,
            ceiling=floor,
            red_flags=red_flags,
            urgent_reasons=[text for text, _ in urgent],
            basis="red flag rule",
        )

    if urgent:
        # Without a red flag the patient cannot be triaged as an emergency, no
        # matter what the model proposes. This is the fix for the contradictory
        # "ESI 2 / critical" plus "no life-threatening signs" output.
        floor, ceiling, basis = min(esi for _, esi in urgent), 4, "urgent rule"
    elif not state.present:
        # Nothing to go on yet. Conservative means "must still be assessed",
        # not "must be resuscitated".
        floor, ceiling, basis = 3, 4, "insufficient information"
    else:
        floor, ceiling, basis = 4, 5, "no rule fired"

    proposed = floor if llm_esi is None else llm_esi
    esi = max(floor, min(ceiling, max(1, min(5, proposed))))

    return SeverityDecision(
        esi=esi,
        floor=floor,
        ceiling=ceiling,
        red_flags=red_flags,
        urgent_reasons=[text for text, _ in urgent],
        basis=basis,
    )


# --------------------------------------------------------------- consistency


def _asserts_feature(sentence: str, finding) -> bool:
    """Does `sentence` state this finding as PRESENT?

    Matched through the feature's own lexicon patterns, so a rationale saying
    "difficulty breathing" is caught by the `dyspnoea` finding whose label is
    "shortness of breath" -- the substring check that came before missed it
    entirely. Polarity is re-derived, so "denies difficulty breathing" is kept.
    """
    patterns = _COMPILED.get(finding.name)
    if not patterns:
        label = finding.label.lower()
        if len(label) < 4:
            return False
        patterns = [re.compile(re.escape(label), re.IGNORECASE)]
    for pattern in patterns:
        for match in pattern.finditer(sentence):
            if polarity_at(sentence, match.span()) == "present":
                return True
    return False


def strip_denied_findings(text: str, state: PatientState) -> str:
    """Remove sentences that assert a finding the patient explicitly denied."""
    denied = state.absent
    if not denied or not text:
        return text
    kept: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text):
        offender = next((f for f in denied if _asserts_feature(sentence, f)), None)
        if offender is not None:
            log.info(
                "rationale_sentence_dropped_denied",
                feature=offender.name,
                sentence=sentence[:120],
            )
            continue
        kept.append(sentence)
    return " ".join(kept).strip()


def check_consistency(
    *, esi: int, red_flags: list[str], rationale: str, state: PatientState
) -> tuple[str, list[str]]:
    """Repair contradictions between severity, red flags and rationale.

    Returns the repaired rationale and the list of issues that were corrected,
    so the mismatch is visible rather than silently patched.
    """
    issues: list[str] = []
    text = strip_denied_findings(rationale, state)
    if text != rationale:
        issues.append("removed statements about findings the patient denied")

    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]

    if esi >= 3 or not red_flags:
        surviving = [s for s in sentences if not _EMERGENCY_LANGUAGE.search(s)]
        if len(surviving) != len(sentences):
            issues.append("removed emergency language unsupported by any red flag")
            sentences = surviving

    if esi <= 2 and red_flags:
        surviving = [s for s in sentences if not _REASSURANCE_LANGUAGE.search(s)]
        if len(surviving) != len(sentences):
            issues.append("removed reassurance that contradicted an active red flag")
            sentences = surviving

    text = " ".join(sentences).strip()

    if esi <= 2 and red_flags:
        flag_text = "; ".join(red_flags)
        if not any(rf.split("(")[0].strip()[:20].lower() in text.lower() for rf in red_flags):
            text = (
                f"Triaged as ESI {esi} because of {flag_text}. " + text
            ).strip()
            issues.append("prepended the red flag that determined the severity")
    elif not red_flags:
        marker = "No emergency red flags were identified from the patient's answers."
        if marker.lower() not in text.lower():
            text = (text + " " + marker).strip()

    return text, issues


def suppress_common_bias(ranked_conditions: list[str], state: PatientState) -> list[str]:
    """Demote high-base-rate conditions supported only by generic features.

    Dengue on fever+vomiting+rash alone is not a differential, it is a prior.
    Such a condition keeps its place in the list -- it may well be right -- but
    it cannot lead when a discriminating feature points elsewhere.
    """
    configured = {k.lower(): v for k, v in COMMON_BIAS.get("conditions", {}).items()}
    required = int(COMMON_BIAS.get("requires_discriminator", 1))
    if not state.discriminators:
        return ranked_conditions

    leading, demoted = [], []
    for condition in ranked_conditions:
        entry = next((v for k, v in configured.items() if k in condition.lower()), None)
        if entry is None:
            leading.append(condition)
            continue
        supported = sum(1 for d in entry.get("discriminators", []) if state.is_present(d))
        if supported >= required:
            leading.append(condition)
        else:
            log.info("common_condition_demoted", condition=condition)
            demoted.append(condition)
    return leading + demoted
