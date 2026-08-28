"""Scope-aware negation and uncertainty detection over patient utterances.

The triage pipeline previously ran red-flag regexes straight over the raw
transcript, so a patient saying "no difficulty breathing" produced a
"difficulty breathing" red flag. Every symptom mention now goes through this
module first, which answers a narrower question: *for this span of text, is the
surrounding clause asserting it, denying it, or hedging it?*

The algorithm is a NegEx variant. A trigger word opens a scope; the scope runs
to the end of the clause or until a termination token flips the polarity back.
Pseudo-triggers ("no doubt", "not only") never open a scope. It is deliberately
lexical and deterministic: it is the layer the LLM is not allowed to overrule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Polarity = Literal["present", "absent", "unknown"]

# Words that open a negated scope running forward from the trigger.
_PRE_NEGATION = [
    r"no", r"not", r"non", r"never", r"none", r"nil", r"without", r"denies",
    r"deny", r"denied", r"denying", r"absent", r"negative for", r"free of",
    r"ruled out", r"rules out", r"there is no", r"there are no", r"hasn'?t",
    r"haven'?t", r"doesn'?t", r"don'?t", r"didn'?t", r"isn'?t", r"aren'?t",
    r"wasn'?t", r"weren'?t", r"cannot say", r"no sign of", r"no signs of",
    r"no history of", r"no h/o", r"nothing like", r"apart from",
    # Hindi/Hinglish forms that show up constantly in Indian OPD intake text.
    r"nahi", r"nahin", r"koi nahi", r"bilkul nahi",
]

# Words that close a negated scope running backward to the trigger.
_POST_NEGATION = [
    r"is absent", r"are absent", r"was absent", r"were absent",
    r"is negative", r"are negative", r"not present", r"is not there",
    r"nahi hai", r"nahi h",
]

# Look like negation but are not; must be stripped before trigger matching.
_PSEUDO_NEGATION = [
    r"no doubt", r"not only", r"not just", r"no change", r"no longer",
    r"not necessarily", r"no matter", r"cannot rule out", r"can'?t rule out",
    r"not sure", r"not certain", r"don'?t know", r"do not know",
]

# Hedges that make an assertion "unknown" rather than "present".
_UNCERTAINTY = [
    r"maybe", r"may be", r"might", r"possibly", r"perhaps", r"not sure",
    r"unsure", r"not certain", r"don'?t know", r"do not know", r"cannot say",
    r"can'?t say", r"i think", r"probably", r"suspect", r"unclear",
    r"pata nahi", r"shayad",
]

# Tokens that terminate a negation scope mid-sentence.
_TERMINATION = [
    r"but", r"however", r"though", r"although", r"except", r"apart from",
    r"aside from", r"yet", r"still", r"nevertheless", r"whereas", r"while",
    r"and now", r"now i", r"now there", r"instead",
]

_MAX_SCOPE_TOKENS = 8


def _alt(patterns: list[str]) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)(?:" + "|".join(patterns) + r")(?!\w)", re.IGNORECASE)


_RE_PRE = _alt(_PRE_NEGATION)
_RE_POST = _alt(_POST_NEGATION)
_RE_PSEUDO = _alt(_PSEUDO_NEGATION)
_RE_UNCERTAIN = _alt(_UNCERTAINTY)
_RE_TERM = _alt(_TERMINATION)
_CLAUSE_SPLIT = re.compile(r"[.;!?\n]|(?<!\d),(?!\d)")


@dataclass(frozen=True)
class Clause:
    text: str
    start: int
    end: int


def split_clauses(text: str) -> list[Clause]:
    """Split into clauses, keeping absolute offsets into the original string."""
    clauses: list[Clause] = []
    cursor = 0
    for match in _CLAUSE_SPLIT.finditer(text):
        if match.start() > cursor:
            clauses.append(Clause(text[cursor : match.start()], cursor, match.start()))
        cursor = match.end()
    if cursor < len(text):
        clauses.append(Clause(text[cursor:], cursor, len(text)))
    return [c for c in clauses if c.text.strip()]


def _mask_pseudo(text: str) -> str:
    """Blank out pseudo-negations so they cannot open a scope, preserving offsets."""
    return _RE_PSEUDO.sub(lambda m: "#" * (m.end() - m.start()), text)


def _token_distance(text: str, a: int, b: int) -> int:
    lo, hi = (a, b) if a <= b else (b, a)
    return len(text[lo:hi].split())


def polarity_at(text: str, span: tuple[int, int]) -> Polarity:
    """Classify the assertion status of the concept occupying `span` in `text`."""
    start, end = span
    clause = next(
        (c for c in split_clauses(text) if c.start <= start < c.end),
        Clause(text, 0, len(text)),
    )
    local = _mask_pseudo(clause.text)
    rel_start = start - clause.start
    rel_end = end - clause.start

    for match in _RE_PRE.finditer(local):
        if match.end() > rel_start:
            continue
        between = local[match.end() : rel_start]
        if _RE_TERM.search(between):
            continue
        if _token_distance(local, match.end(), rel_start) <= _MAX_SCOPE_TOKENS:
            return "absent"

    for match in _RE_POST.finditer(local):
        if match.start() < rel_end:
            continue
        between = local[rel_end : match.start()]
        if _RE_TERM.search(between):
            continue
        if _token_distance(local, rel_end, match.start()) <= _MAX_SCOPE_TOKENS:
            return "absent"

    for match in _RE_UNCERTAIN.finditer(clause.text):
        if _token_distance(clause.text, match.end(), rel_start) <= _MAX_SCOPE_TOKENS:
            return "unknown"

    return "present"


def is_negated(text: str, span: tuple[int, int]) -> bool:
    return polarity_at(text, span) == "absent"


def find_assertions(text: str, pattern: re.Pattern[str]) -> list[tuple[str, Polarity, tuple[int, int]]]:
    """Every match of `pattern` in `text`, tagged with its assertion status."""
    return [
        (m.group(0), polarity_at(text, m.span()), m.span())
        for m in pattern.finditer(text)
    ]
