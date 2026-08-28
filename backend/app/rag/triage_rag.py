"""Pre-assessment triage.

The pipeline is explicitly staged, and every stage reads the same structured
`PatientState` rather than re-reading free text:

    conversation
      -> patient state          (app.rag.patient_state, negation-aware)
      -> weighted query fan-out (app.rag.query_builder)
      -> evidence retrieval     (app.rag.retriever.multi_hybrid)
      -> differential           (LLM, grounded in state + evidence)
      -> red flags              (app.rag.triage_rules, deterministic)
      -> triage level           (app.rag.triage_rules, deterministic)
      -> rationale + labs       (LLM, explaining a decision already made)
      -> consistency repair     (app.rag.triage_rules.check_consistency)

The division of labour matters. The LLM writes prose and ranks conditions
against retrieved evidence; it never decides whether a finding is present and
never decides how urgent the patient is. That is what stops a note asserting a
symptom the patient denied, or calling a patient critical while explaining that
nothing life-threatening was found.
"""

import re
from datetime import datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.logging import get_logger
from app.db.models.clinical import TriageSession
from app.llm.gateway import complete, json_complete
from app.llm.prompts import (
    DIFFERENTIAL_SYSTEM,
    RED_FLAG_SYSTEM,
    TRIAGE_FINALIZE_SYSTEM_V2,
    TRIAGE_QUESTION_SYSTEM,
)
from app.rag import triage_rules
from app.rag.negation import polarity_at
from app.rag.patient_state import (
    _COMPILED as _FEATURE_PATTERNS,
)
from app.rag.patient_state import FEATURES, PatientState, build_state, extract_deterministic
from app.rag.query_builder import build_queries, candidate_conditions
from app.rag.retriever import multi_hybrid
from app.rag.store import Hit
from app.schemas.common import Citation
from app.schemas.triage import (
    DifferentialItem,
    FindingOut,
    PatientStateOut,
    SuggestedLab,
    TriageResult,
    TriageTurnOut,
    colour_for_esi,
)

log = get_logger(__name__)

MAX_QUESTIONS = 8
EVIDENCE_K = 10
IST = ZoneInfo("Asia/Kolkata")
OPENING_QUICK_REPLIES = [
    "Fever",
    "Cough or breathing trouble",
    "Stomach pain",
    "Injury",
]
_DATA_DIR = Path(__file__).parent / "data"

_esi_data = yaml.safe_load((_DATA_DIR / "esi_rules.yaml").read_text(encoding="utf-8"))
_RED_FLAG_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _esi_data["red_flag_patterns"]]

# Feature categories worth covering before finalizing, in the order a clinician
# would work through them. Used to steer questioning toward what is missing
# rather than letting the model wander.
_COVERAGE_ORDER = ["exposure", "constitutional", "renal", "hepatic", "respiratory", "neurological"]


class _RedFlagCheck(BaseModel):
    red_flag: bool = False
    reason: str = ""


def _regex_red_flag(text: str) -> str | None:
    """Legacy phrase-level screen, now negation-aware.

    A pattern only counts when the phrase is actually asserted. "no difficulty
    breathing" used to match `difficulty breathing` and produce a red flag for a
    symptom the patient had just denied -- the single most damaging bug in the
    old pipeline.
    """
    for pattern in _RED_FLAG_PATTERNS:
        for match in pattern.finditer(text):
            if polarity_at(text, match.span()) == "present":
                return pattern.pattern
    return None


async def _llm_red_flag(text: str) -> str | None:
    check = await json_complete(text, schema=_RedFlagCheck, system=RED_FLAG_SYSTEM)
    return check.reason if check.red_flag else None


async def _check_red_flags(text: str) -> list[str]:
    """Turn-level safety screen. Deliberately kept as a fast net over one utterance.

    The authoritative red-flag list comes from `triage_rules.detect_red_flags`
    over the whole state at finalize time; this only decides whether to stop
    asking questions and escalate now.
    """
    flags: list[str] = []
    regex_hit = _regex_red_flag(text)
    if regex_hit:
        flags.append(f"pattern match: {regex_hit}")
    # The classifier is only consulted about text the patient actually asserted,
    # so a turn made entirely of denials cannot raise a flag.
    asserted = _asserted_text(text)
    if asserted.strip():
        llm_hit = await _llm_red_flag(asserted)
        if llm_hit:
            flags.append(llm_hit)
    return flags


def _asserted_text(text: str) -> str:
    """Drop clauses that are pure denials before handing text to a classifier."""
    from app.rag.negation import split_clauses

    kept = []
    for clause in split_clauses(text):
        probe = clause.text.strip()
        if not probe:
            continue
        mid = len(probe) // 2
        if polarity_at(clause.text, (mid, min(mid + 1, len(clause.text)))) == "absent":
            continue
        kept.append(probe)
    return ". ".join(kept)


async def _get_session(db: AsyncSession, session_id: UUID) -> TriageSession:
    result = await db.execute(select(TriageSession).where(TriageSession.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise ApiError("NOT_FOUND", "triage session not found", status_code=404)
    return session


def _questions_asked(transcript: list[dict]) -> int:
    return sum(1 for turn in transcript if turn.get("role") == "assistant")


def _transcript_text(transcript: list[dict]) -> str:
    return "\n".join(f"{t['role']}: {t['content']}" for t in transcript)


def _greeting(now: datetime | None = None) -> str:
    """Time-of-day greeting in clinic local time (IST)."""
    hour = (now or datetime.now(IST)).hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def _opening_question() -> str:
    """The first turn is a fixed open invitation, not a model-generated question.

    With an empty transcript the model has nothing to condition on and invents a
    symptom, so ask the patient what brings them in instead.
    """
    return (
        f"{_greeting()}! I am the clinic's pre-assessment assistant. "
        "How can we help you today? Please tell me what you are feeling, in your own words."
    )


def _coverage_gaps(state: PatientState) -> list[str]:
    """Categories that would change the differential but have not been asked about.

    Steering questions at the gaps is what lets a discriminating feature --
    exposure history, urine colour, duration -- get on the record at all. It is
    also why the note can be honest about what remains unassessed.
    """
    conditions = candidate_conditions(state)
    covered = {f.category for f in state.findings if f.status != "unknown"}
    wanted: set[str] = set()
    for condition in conditions[:6]:
        for name, spec in FEATURES.items():
            if condition in spec.suggests and state.status(name) == "unknown":
                wanted.add(spec.category)
    # A category the patient has already answered something in is not a gap;
    # reporting "exposure not assessed" next to a recorded water exposure is the
    # kind of internal contradiction this pipeline is supposed to eliminate.
    wanted -= covered
    if state.duration_days is None:
        wanted.add("duration")
    gaps = [c for c in _COVERAGE_ORDER if c in wanted]
    if "duration" in wanted:
        gaps.insert(0, "duration")
    return gaps


async def _ask_question(transcript: list[dict]) -> str:
    state = extract_deterministic(transcript)
    gaps = _coverage_gaps(state)
    gap_hint = (
        f"\nStill unassessed and worth asking about: {', '.join(gaps[:3])}."
        if gaps
        else ""
    )
    prompt = (
        "Structured patient state so far:\n"
        f"{state.as_prompt_block()}\n"
        f"{gap_hint}\n\n"
        "Ask the single next most useful triage question. Do not ask about anything "
        "already listed as PRESENT or EXPLICITLY DENIED above."
    )
    question = await complete(prompt, system=TRIAGE_QUESTION_SYSTEM, max_tokens=80, temperature=0.3)
    return question.strip()


async def start(db: AsyncSession, patient_id: UUID | None) -> TriageTurnOut:
    session = TriageSession(patient_id=patient_id, transcript=[], result=None)
    db.add(session)
    await db.flush()

    question = _opening_question()
    transcript = [{"role": "assistant", "content": question}]
    session.transcript = transcript
    await db.commit()

    return TriageTurnOut(
        session_id=session.id,
        assistant=question,
        done=False,
        quick_replies=OPENING_QUICK_REPLIES,
        questions_asked=1,
    )


async def turn(db: AsyncSession, session_id: UUID, content: str) -> TriageTurnOut:
    session = await _get_session(db, session_id)
    transcript = list(session.transcript or [])
    transcript.append({"role": "user", "content": content})

    red_flags = await _check_red_flags(content)
    questions_asked = _questions_asked(transcript)

    if red_flags or questions_asked >= MAX_QUESTIONS:
        session.transcript = transcript
        await db.commit()
        closing = (
            "Thank you — based on what you have described, this needs immediate "
            "medical attention. Please go to the nearest emergency department now, "
            "or call 112 (or 108 for an ambulance). Finalizing your triage."
            if red_flags
            else "Thank you, that is everything I need. Finalizing your triage now."
        )
        await finalize(db, session.id)
        return TriageTurnOut(
            session_id=session.id,
            assistant=closing,
            done=True,
            quick_replies=[],
            questions_asked=questions_asked,
        )

    question = await _ask_question(transcript)
    transcript.append({"role": "assistant", "content": question})
    session.transcript = transcript
    await db.commit()

    return TriageTurnOut(
        session_id=session.id,
        assistant=question,
        done=False,
        quick_replies=[],
        questions_asked=questions_asked + 1,
    )


# ----------------------------------------------------------------- finalize


_CONFIDENCE_WORDS = {
    "very low": 0.1, "low": 0.25, "moderate": 0.5, "medium": 0.5,
    "high": 0.8, "very high": 0.9, "certain": 0.95,
}
_LAB_NAME_ALIASES = ("test", "test_name", "lab", "investigation", "label")


class _RawDifferential(BaseModel):
    differentials: list[DifferentialItem] = []

    @model_validator(mode="before")
    @classmethod
    def _normalise(cls, data):
        """Accept the wrapper and item key names models actually use.

        Observed in practice: the bare array, `{"conditions": [...]}`, and items
        keyed `name` or `diagnosis` rather than `condition`. None of these are
        the model reasoning badly, so none of them should cost us the whole
        differential.
        """
        if isinstance(data, list):
            data = {"differentials": data}
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "differentials" not in data:
            for alias in ("conditions", "differential", "diagnoses", "items"):
                if isinstance(data.get(alias), list):
                    data["differentials"] = data.pop(alias)
                    break
        items = data.get("differentials")
        if isinstance(items, list):
            normalised = []
            for item in items:
                if isinstance(item, str):
                    normalised.append({"condition": item})
                    continue
                if not isinstance(item, dict):
                    continue
                item = dict(item)
                if "condition" not in item:
                    for alias in ("name", "diagnosis", "title", "label"):
                        if item.get(alias):
                            item["condition"] = item.pop(alias)
                            break
                if item.get("condition"):
                    normalised.append(item)
            data["differentials"] = normalised
        return data



# --- specialty routing -------------------------------------------------
#
# `services/scheduling/repo.doctors_by_specialty` matches the Doctor.specialties
# JSONB array exactly, so a free-text specialty from the model ("Infectious
# Diseases") routes to nobody and every booking made from a triage session
# 404s. Triage is the producer of that field, so the vocabulary is pinned
# here rather than papered over at the booking layer.
#
# The canonical set is what an Indian primary/secondary clinic actually
# staffs; sub-specialties map to the department that runs the OPD for them.

CANONICAL_SPECIALTIES: frozenset[str] = frozenset(
    {
        "general_medicine",
        "cardiology",
        "pediatrics",
        "dermatology",
        "orthopedics",
        "neurology",
        "pulmonology",
        "gastroenterology",
        "nephrology",
        "endocrinology",
        "obstetrics_gynaecology",
        "psychiatry",
        "ophthalmology",
        "ent",
        "urology",
        "general_surgery",
    }
)

_SPECIALTY_ALIASES: dict[str, str] = {
    # Infectious disease is run out of general medicine in most Indian OPDs,
    # and the tropical-fever burden this triage covers lands there.
    "infectious_diseases": "general_medicine",
    "infectious_disease": "general_medicine",
    "tropical_medicine": "general_medicine",
    "internal_medicine": "general_medicine",
    "general_practice": "general_medicine",
    "family_medicine": "general_medicine",
    "emergency_medicine": "general_medicine",
    "critical_care": "general_medicine",
    "hepatology": "gastroenterology",
    "rheumatology": "general_medicine",
    "haematology": "general_medicine",
    "hematology": "general_medicine",
    "oncology": "general_medicine",
    "endocrine": "endocrinology",
    "diabetology": "endocrinology",
    "respiratory_medicine": "pulmonology",
    "chest_medicine": "pulmonology",
    "pulmonary_medicine": "pulmonology",
    "cardiovascular": "cardiology",
    "paediatrics": "pediatrics",
    "child_health": "pediatrics",
    "neonatology": "pediatrics",
    "orthopaedics": "orthopedics",
    "trauma": "orthopedics",
    "obstetrics": "obstetrics_gynaecology",
    "gynaecology": "obstetrics_gynaecology",
    "gynecology": "obstetrics_gynaecology",
    "obstetrics_and_gynaecology": "obstetrics_gynaecology",
    "obgyn": "obstetrics_gynaecology",
    "skin": "dermatology",
    "venereology": "dermatology",
    "eye": "ophthalmology",
    "otorhinolaryngology": "ent",
    "ear_nose_throat": "ent",
    "mental_health": "psychiatry",
    "surgery": "general_surgery",
    "nephrology_renal": "nephrology",
}

# Last-resort keyword routing for phrasings the alias table has not seen.
_SPECIALTY_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("cardio", "cardiology"),
    ("heart", "cardiology"),
    ("neuro", "neurology"),
    ("stroke", "neurology"),
    ("derma", "dermatology"),
    ("skin", "dermatology"),
    ("ortho", "orthopedics"),
    ("fracture", "orthopedics"),
    ("bone", "orthopedics"),
    ("paediat", "pediatrics"),
    ("pediat", "pediatrics"),
    ("child", "pediatrics"),
    ("pulmon", "pulmonology"),
    ("respirat", "pulmonology"),
    ("lung", "pulmonology"),
    ("gastro", "gastroenterology"),
    ("liver", "gastroenterology"),
    ("hepat", "gastroenterology"),
    ("nephro", "nephrology"),
    ("renal", "nephrology"),
    ("kidney", "nephrology"),
    ("endocrin", "endocrinology"),
    ("diabet", "endocrinology"),
    ("thyroid", "endocrinology"),
    ("obstetr", "obstetrics_gynaecology"),
    ("gynae", "obstetrics_gynaecology"),
    ("gyneco", "obstetrics_gynaecology"),
    ("pregnan", "obstetrics_gynaecology"),
    ("psychiat", "psychiatry"),
    ("mental", "psychiatry"),
    ("ophthalm", "ophthalmology"),
    ("eye", "ophthalmology"),
    ("ent", "ent"),
    ("throat", "ent"),
    ("urolog", "urology"),
    ("surg", "general_surgery"),
)


def normalise_specialty(raw: str | None) -> str:
    """Map whatever the model wrote onto a bookable specialty slug.

    Always returns a member of `CANONICAL_SPECIALTIES`; unrecognised input
    degrades to `general_medicine`, which is the department that sees an
    undifferentiated presentation anyway.
    """

    if not raw:
        return "general_medicine"

    slug = re.sub(r"[^a-z0-9]+", "_", str(raw).strip().lower()).strip("_")
    if not slug:
        return "general_medicine"

    if slug in CANONICAL_SPECIALTIES:
        return slug
    if slug in _SPECIALTY_ALIASES:
        return _SPECIALTY_ALIASES[slug]

    for needle, target in _SPECIALTY_KEYWORDS:
        if needle in slug:
            return target

    return "general_medicine"


class _RawTriage(BaseModel):
    """The model's contribution to the note: prose, labs and citation numbers.

    Deliberately tolerant. A schema mismatch here used to discard the entire
    reasoning output and fall back to an empty note, which is safe but useless.
    The shapes normalised below are the ones observed in practice: labs keyed on
    `test`, citations given as bare excerpt numbers, confidence as a word.
    """

    severity_esi: int | None = None
    specialty: str = "general_medicine"
    suggested_labs: list[SuggestedLab] = []
    rationale: str = ""
    citations: list[int] = []
    confidence: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def _normalise(cls, data):
        if not isinstance(data, dict):
            return data
        data = dict(data)

        labs = data.get("suggested_labs")
        if isinstance(labs, list):
            normalised = []
            for lab in labs:
                if isinstance(lab, str):
                    normalised.append({"name": lab, "reason": ""})
                    continue
                if not isinstance(lab, dict):
                    continue
                lab = dict(lab)
                if "name" not in lab:
                    for alias in _LAB_NAME_ALIASES:
                        if lab.get(alias):
                            lab["name"] = lab.pop(alias)
                            break
                lab.setdefault("reason", "")
                if lab.get("name"):
                    normalised.append(lab)
            data["suggested_labs"] = normalised

        # Citations are excerpt numbers. Accepting objects too lets us take the
        # `n` and throw away every other field the model wrote -- the citation
        # text is always rebuilt from the retrieved hit, never from the model.
        citations = data.get("citations")
        if isinstance(citations, list):
            numbers: list[int] = []
            for citation in citations:
                if isinstance(citation, int):
                    numbers.append(citation)
                elif isinstance(citation, dict) and isinstance(citation.get("n"), int):
                    numbers.append(citation["n"])
            data["citations"] = numbers

        confidence = data.get("confidence")
        if isinstance(confidence, str):
            data["confidence"] = _CONFIDENCE_WORDS.get(confidence.strip().lower(), 0.0)

        return data


def _context_block(hits: list[Hit]) -> str:
    return "\n".join(
        f"[{i + 1}] {h.metadata.get('title', 'untitled')} "
        f"({h.metadata.get('source', 'unknown source')}): {h.text[:400]}"
        for i, h in enumerate(hits)
    )


async def retrieve_evidence(state: PatientState) -> list[Hit]:
    """Weighted multi-query retrieval driven by the patient's own features."""
    queries = build_queries(state)
    return await multi_hybrid(
        "guidelines",
        [(q.text, q.weight) for q in queries],
        k=EVIDENCE_K,
        discriminator_terms=[f.label for f in state.discriminators],
        denied_terms=[f.label for f in state.absent],
        rerank_query=queries[0].text,
    )


def _rests_on_unassessed(claim: str, state: PatientState) -> bool:
    """Does this "against" claim argue from a finding that was never assessed?"""
    lowered = claim.lower()
    if not re.search(r"\b(absence|absent|no |not |lack|without|denied|negative)\b", lowered):
        return False
    # Resolved through the feature's own patterns rather than its label, so
    # "no reported chills or rigors" is recognised as the `rigors` feature even
    # though its label reads "shaking chills with the fever".
    for name, patterns in _FEATURE_PATTERNS.items():
        if any(pattern.search(claim) for pattern in patterns):
            return state.status(name) == "unknown"
    return False


class DifferentialUnavailable(Exception):
    """The differential stage could not run, as opposed to finding nothing."""


async def build_differential(state: PatientState, hits: list[Hit]) -> list[DifferentialItem]:
    """Rank conditions against the evidence, then demote unsupported common ones."""
    if not hits:
        return []
    prompt = (
        "Structured patient state (authoritative — do not add to it):\n"
        f"{state.as_prompt_block()}\n\n"
        "Discriminating features the patient reported, most specific first:\n"
        f"{', '.join(f.label for f in state.discriminators) or 'none'}\n\n"
        "Retrieved evidence excerpts (cite as [n]):\n"
        f"{_context_block(hits)}\n\n"
        "Return up to six conditions worth considering, ordered by how well the "
        "patient's ACTUAL findings fit. For each give `supporting` (present "
        "findings only), `against` (denied findings or a mismatch of duration or "
        "pattern), `discriminating_tests` (what would separate it from the "
        "others) and `citation_numbers`."
    )
    try:
        raw = await json_complete(prompt, schema=_RawDifferential, system=DIFFERENTIAL_SYSTEM)
    except Exception as exc:  # noqa: BLE001
        log.warning("differential_failed", error=str(exc))
        raise DifferentialUnavailable(str(exc)) from exc

    present_labels = {f.label.lower() for f in state.present}
    absent_labels = {f.label.lower() for f in state.absent}
    cleaned: list[DifferentialItem] = []
    for item in raw.differentials:
        if not item.condition.strip():
            continue
        # A "supporting" finding must be one the patient actually reported.
        item.supporting = [
            s for s in item.supporting
            if any(label in s.lower() or s.lower() in label for label in present_labels)
        ]
        # And a finding the patient denied can only ever appear under `against`.
        moved = [
            s for s in item.supporting
            if any(label in s.lower() for label in absent_labels)
        ]
        if moved:
            item.supporting = [s for s in item.supporting if s not in moved]
            item.against = list(dict.fromkeys([*item.against, *moved]))
        # An argument *against* a condition must rest on something the patient
        # actually denied. Models reach for "absence of rigors" when rigors were
        # never asked about, which turns a gap in the history into evidence.
        item.against = [
            a for a in item.against
            if not _rests_on_unassessed(a, state)
        ]
        item.citation_numbers = [n for n in item.citation_numbers if 1 <= n <= len(hits)]
        if not item.citation_numbers:
            log.info("differential_dropped_uncited", condition=item.condition)
            continue
        cleaned.append(item)

    ordered_names = triage_rules.suppress_common_bias([i.condition for i in cleaned], state)
    by_name = {i.condition: i for i in cleaned}
    return [by_name[n] for n in ordered_names if n in by_name]


def _resolve_citations(
    rationale: str,
    cited_numbers: list[int],
    hits: list[Hit],
    differentials: list[DifferentialItem] | None = None,
) -> tuple[str, list[Citation]]:
    """Build the citation list from retrieved hits and rewrite the `[n]` markers.

    Citations are constructed from the retrieved chunk's own metadata, never
    from text the model wrote. That removes fabricated titles and URLs by
    construction rather than by validation: the model's only influence is which
    excerpt number it points at, and a number outside the retrieved range is
    dropped along with its marker.

    Renumbering rewrites the prose as well. The previous code renumbered the
    citation objects but left the markers pointing at pre-renumbering indices,
    so a "validated" citation list could still be paired with wrong markers.
    """
    used = [int(n) for n in re.findall(r"\[(\d+)\]", rationale)]
    from_differentials = [n for d in (differentials or []) for n in d.citation_numbers]
    ordered = list(dict.fromkeys([*used, *cited_numbers, *from_differentials]))

    remap: dict[int, int] = {}
    kept: list[Citation] = []
    for number in ordered:
        if not 1 <= number <= len(hits):
            continue
        hit = hits[number - 1]
        remap[number] = len(kept) + 1
        kept.append(
            Citation(
                n=len(kept) + 1,
                title=hit.metadata.get("title") or "untitled",
                source=hit.metadata.get("source") or "unknown",
                url=hit.metadata.get("url") or None,
                snippet=hit.text[:300],
                published=hit.metadata.get("published") or None,
            )
        )

    def _sub(match: re.Match[str]) -> str:
        new = remap.get(int(match.group(1)))
        return f"[{new}]" if new else ""

    text = re.sub(r"\[(\d+)\]", _sub, rationale)

    # The differential cites the same excerpt list, so it must be renumbered
    # with it. Leaving it on the old indices was a silent internal mismatch.
    for item in differentials or []:
        item.citation_numbers = [remap[n] for n in item.citation_numbers if n in remap]

    return re.sub(r"\s{2,}", " ", text).strip(), kept


def _state_out(state: PatientState) -> PatientStateOut:
    def _to_out(findings) -> list[FindingOut]:
        return [
            FindingOut(
                name=f.name,
                label=f.label,
                category=f.category,
                status=f.status,
                specificity=f.specificity,
                severity=f.severity,
                evidence=f.evidence[:200],
            )
            for f in findings
        ]

    return PatientStateOut(
        chief_complaint=state.chief_complaint,
        duration_days=state.duration_days,
        present=_to_out(state.present),
        absent=_to_out(state.absent),
        unknown=_to_out(state.unknown),
        discriminating_features=[f.label for f in state.discriminators],
    )


def _uncertainty_notes(
    state: PatientState,
    hits: list[Hit],
    differentials: list,
    *,
    differential_available: bool = True,
) -> list[str]:
    """What the note is NOT able to conclude, stated plainly."""
    notes: list[str] = []
    if state.turns_answered < 2:
        notes.append("Very little history was gathered; this assessment is provisional.")
    if state.duration_days is None:
        notes.append("Symptom duration was not established.")
    if not state.discriminators:
        notes.append(
            "No discriminating features were reported, so the differential rests on "
            "non-specific symptoms and cannot be narrowed."
        )
    if not hits:
        notes.append("No supporting guideline evidence was retrieved.")
    if not differential_available:
        notes.append(
            "The differential reasoning step was unavailable, so no ranked "
            "conditions are shown. The evidence and triage level below still stand."
        )
    elif not differentials:
        notes.append("No condition could be supported by the retrieved evidence.")
    gaps = _coverage_gaps(state)
    if gaps:
        notes.append("Not yet assessed: " + ", ".join(gaps[:4]) + ".")
    return notes


async def finalize(db: AsyncSession, session_id: UUID) -> TriageResult:
    session = await _get_session(db, session_id)
    transcript = list(session.transcript or [])

    # Stage 1 — structured state. Everything below reads only from this.
    state = await build_state(transcript)

    # Stage 2 — evidence retrieval driven by the state's discriminating features.
    hits = await retrieve_evidence(state)

    # Stage 3 — differential, grounded in state + evidence, debiased.
    differential_available = True
    try:
        differentials = await build_differential(state, hits)
    except DifferentialUnavailable:
        differentials, differential_available = [], False

    # Stage 4 — red flags and severity, deterministic and state-derived.
    decision = triage_rules.decide_severity(state)
    red_flag_texts = [f.render() for f in decision.red_flags]

    # Stage 5 — rationale and investigations. The model explains a decision that
    # has already been made; it is given the severity rather than choosing it.
    prompt = (
        "Structured patient state (authoritative — do not add to it):\n"
        f"{state.as_prompt_block()}\n\n"
        f"Triage decision already made by the rule engine — severity ESI "
        f"{decision.esi} ({colour_for_esi(decision.esi)}), basis: {decision.basis}.\n"
        f"Red flags: {'; '.join(red_flag_texts) or 'NONE — no red flag rule fired'}\n"
        f"Concerning combinations: {'; '.join(decision.urgent_reasons) or 'none'}\n\n"
        "Differential under consideration:\n"
        + (
            "\n".join(
                f"- {d.condition}: supported by {', '.join(d.supporting) or 'no present finding'}; "
                f"against: {', '.join(d.against) or 'nothing recorded'}"
                for d in differentials
            )
            or "- none established"
        )
        + "\n\nRetrieved evidence excerpts (cite as [n]):\n"
        f"{_context_block(hits)}\n\n"
        "Write the triage note: `rationale` explaining the severity above and what "
        "the differential turns on, `specialty`, `suggested_labs` (each with a "
        "reason naming the specific finding it is for), `citations` matching the "
        "excerpts, and `confidence` as a number between 0 and 1. Echo back "
        "`severity_esi` as given. `citations` is a list of the excerpt NUMBERS you "
        "actually cited, for example [1, 4, 7] — do not copy the excerpt text."
    )
    try:
        raw = await json_complete(prompt, schema=_RawTriage, system=TRIAGE_FINALIZE_SYSTEM_V2)
    except Exception as exc:  # noqa: BLE001
        log.warning("triage_finalize_llm_failed", error=str(exc))
        raw = _RawTriage()

    # The model's severity is only ever a proposal, and only inside the band the
    # rule engine allows. With a red flag, the band is a single value.
    decision = triage_rules.decide_severity(state, llm_esi=raw.severity_esi)
    severity = decision.esi
    red_flag_texts = [f.render() for f in decision.red_flags]

    # Stage 6 — citation validation, then consistency repair.
    rationale, citations = _resolve_citations(
        raw.rationale, raw.citations, hits, differentials
    )
    rationale, consistency_notes = triage_rules.check_consistency(
        esi=severity, red_flags=red_flag_texts, rationale=rationale, state=state
    )

    labs = [
        lab for lab in raw.suggested_labs if lab.name.strip()
    ]
    uncertainty = _uncertainty_notes(
        state, hits, differentials, differential_available=differential_available
    )

    confidence = raw.confidence if citations else 0.0
    if not state.discriminators:
        # Non-specific presentations get a hard confidence cap. The pipeline
        # should not sound sure about a picture that fits fifty illnesses.
        confidence = min(confidence, 0.4)
    if consistency_notes:
        confidence = min(confidence, 0.5)
    if not rationale:
        confidence = 0.0
        rationale = (
            "Insufficient grounded evidence to write an assessment. "
            + (f"Extractive summary: {hits[0].text[:200]}" if hits else "")
        ).strip()

    triage_result = TriageResult(
        session_id=session.id,
        patient_id=session.patient_id,
        severity_esi=severity,
        triage_colour=colour_for_esi(severity),
        specialty=normalise_specialty(raw.specialty),
        red_flags=red_flag_texts,
        suggested_labs=labs,
        rationale=rationale,
        citations=citations,
        confidence=round(max(0.0, min(1.0, confidence)), 2),
        differentials=differentials,
        patient_state=_state_out(state),
        uncertainty=uncertainty,
        consistency_notes=consistency_notes,
    )

    session.result = triage_result.model_dump(mode="json")
    await db.commit()

    log.info(
        "triage_finalized",
        session_id=str(session.id),
        esi=triage_result.severity_esi,
        colour=triage_result.triage_colour,
        basis=decision.basis,
        red_flags=red_flag_texts,
        differentials=[d.condition for d in differentials],
        consistency_notes=consistency_notes,
    )
    return triage_result


async def get_result(db: AsyncSession, session_id: UUID) -> TriageResult:
    session = await _get_session(db, session_id)
    if session.result is None:
        raise ApiError("NOT_FOUND", "triage result not yet finalized", status_code=404)
    return TriageResult.model_validate(session.result)
