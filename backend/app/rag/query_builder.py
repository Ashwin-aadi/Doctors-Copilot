"""Turn a `PatientState` into a weighted set of retrieval queries.

The old pipeline embedded the entire transcript -- assistant questions included
-- as a single query. Two things follow from that, and both were visible in the
leptospirosis test case:

* The signal is dominated by whatever is most frequent in the text, which for
  any febrile illness is "fever", "vomiting", "body ache". Those tokens are
  near-uniform across the corpus, so the nearest neighbours are simply the
  commonest febrile illnesses. Dengue wins on prior, every time.
* Interrogative text ("do you have chest pain?") is retrieved against as if the
  patient had asserted it, and denied symptoms are embedded as positive text.

So instead we fan out: one query for the whole presentation, one per
discriminating feature anchored to its context, one for the discriminating
combination, and one per condition that a discriminating feature actually
raises. Denied findings never enter query text; they are applied as penalties
at rerank instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger
from app.rag.patient_state import FEATURES, PatientState

log = get_logger(__name__)

MAX_DISCRIMINATOR_QUERIES = 4
MAX_CONDITION_QUERIES = 6


@dataclass
class RetrievalQuery:
    text: str
    weight: float
    kind: str


def _duration_phrase(state: PatientState) -> str:
    days = state.duration_days
    if days is None:
        return ""
    if days < 1:
        return "of a few hours duration, acute onset"
    if days <= 2:
        return "for one to two days, acute"
    if days <= 4:
        return "for three to four days"
    if days <= 10:
        return f"for {days:g} days, prolonged fever"
    return "for more than two weeks, chronic"


def candidate_conditions(state: PatientState) -> list[str]:
    """Conditions raised by the patient's discriminating features.

    Only discriminating features contribute. A condition suggested purely by
    "fever" would be every condition, which is the same as no condition at all.
    """
    scored: dict[str, float] = {}
    for finding in state.discriminators:
        spec = FEATURES.get(finding.name)
        if spec is None:
            continue
        for condition in spec.suggests:
            scored[condition] = scored.get(condition, 0.0) + finding.specificity
    ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    return [c for c, _ in ranked]


def build_queries(state: PatientState) -> list[RetrievalQuery]:
    """The weighted query fan-out for one patient state."""
    present_labels = [f.label for f in sorted(state.present, key=lambda f: -f.specificity)]
    duration = _duration_phrase(state)
    queries: list[RetrievalQuery] = []

    if present_labels:
        queries.append(
            RetrievalQuery(
                text=", ".join(present_labels) + (f", {duration}" if duration else ""),
                weight=1.0,
                kind="presentation",
            )
        )
    elif state.chief_complaint:
        queries.append(RetrievalQuery(text=state.chief_complaint, weight=1.0, kind="presentation"))

    discriminators = state.discriminators[:MAX_DISCRIMINATOR_QUERIES]
    anchor = ", ".join(f.label for f in state.generic[:2])

    # One query per discriminating feature. This is what gives an uncommon but
    # highly specific finding its own shot at retrieval, instead of being
    # averaged away inside a long presentation vector.
    for finding in discriminators:
        text = finding.label
        if anchor:
            text = f"{text} with {anchor}"
        if duration:
            text = f"{text} {duration}"
        queries.append(
            RetrievalQuery(text=text, weight=0.6 + 0.4 * finding.specificity, kind="discriminator")
        )

    # The combination itself is often more diagnostic than any single feature.
    if len(discriminators) >= 2:
        combo = ", ".join(f.label for f in discriminators)
        queries.append(
            RetrievalQuery(
                text=f"{combo}{', ' + anchor if anchor else ''}{', ' + duration if duration else ''}",
                weight=1.2,
                kind="combination",
            )
        )

    # Named-condition probes. Retrieval against a disease name reaches corpus
    # chunks that a symptom vector alone will not, which is how a rarer
    # condition becomes visible next to the common ones.
    for condition in candidate_conditions(state)[:MAX_CONDITION_QUERIES]:
        queries.append(
            RetrievalQuery(
                text=f"{condition}: presentation, diagnosis and investigations{', ' + anchor if anchor else ''}",
                weight=0.7,
                kind="condition",
            )
        )

    if not queries:
        queries.append(RetrievalQuery(text="general adult intake assessment", weight=1.0, kind="fallback"))

    log.info("triage_queries_built", queries=[(q.kind, q.text[:70]) for q in queries])
    return queries
