"""Doctor-facing clinical copilot brief: KG context + abnormal labs + triage
result drive one retrieval query per axis against the "clinical" collection,
reranked and deduped, then summarized into a cited CopilotBrief. Never emits
an ungrounded claim -- any sentence whose citation can't be resolved against
the retrieved hits is stripped, and an empty citation list forces
confidence=0 with an extractive summary instead of LLM prose.
"""

import re
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.logging import get_logger
from app.db.models.clinical import LabResult, TriageSession, Visit
from app.db.models.patient import Patient
from app.kg.queries import patient_context
from app.llm.gateway import json_complete
from app.llm.prompts import CLINICAL_BRIEF_SYSTEM
from app.rag.retriever import hybrid
from app.rag.store import Hit
from app.rag.tool_bridge import flag_labs
from app.schemas.common import Citation
from app.schemas.copilot import CopilotBrief

log = get_logger(__name__)

_K_PER_AXIS = 8
_TOP_K = 10

# A plain `[n]` marker, and the wrappers models put around one. Smaller local
# models routinely emit `[cite [2]]` or `(ref: 3)` where the prompt asked for
# `[2]`; the citation is real, only the packaging differs, so normalise rather
# than discard.
_CITE_MARKER = re.compile(r"\[(\d+)\]")
_LOOSE_MARKER = re.compile(
    r"[\[(]\s*(?:cite|citation|ref|reference|source)s?\s*[:\-]?\s*\[?(\d+)\]?\s*[\])]",
    re.IGNORECASE,
)


def _normalise_markers(text: str) -> str:
    """Rewrite decorated citation markers into the bare `[n]` form."""
    return _LOOSE_MARKER.sub(r"[\1]", text or "")


async def _load_visit(db: AsyncSession, visit_id: UUID) -> Visit:
    visit = await db.get(Visit, visit_id)
    if visit is None:
        raise ApiError("NOT_FOUND", "visit not found", status_code=404)
    return visit


def _build_axis_queries(patient: Patient, context: dict, triage: dict | None, abnormal_labs: list[dict]) -> list[str]:
    queries: list[str] = []
    if triage and triage.get("specialty"):
        queries.append(f"{triage['specialty']} presenting complaint: {triage.get('rationale', '')[:200]}")
    for lab in abnormal_labs:
        name = lab.get("test_name") or lab.get("normalized_name")
        if name:
            queries.append(f"abnormal lab result {name} flag {lab.get('flag', '')} clinical significance")
    for med in context.get("medications", []):
        name = med.get("name")
        if name:
            queries.append(f"{name} indications dosing contraindications interactions")
    for condition in context.get("conditions", []):
        name = condition.get("name")
        if name:
            queries.append(f"{name} management guideline India")
    if not queries:
        queries.append(f"general outpatient assessment {patient.name}".strip())
    return queries[:8]


async def _retrieve_deduped(queries: list[str]) -> list[Hit]:
    by_url: dict[str, Hit] = {}
    for q in queries:
        for hit in await hybrid("clinical", q, k=_K_PER_AXIS):
            url = hit.metadata.get("url") or hit.id
            existing = by_url.get(url)
            if existing is None or hit.score > existing.score:
                by_url[url] = hit
    ranked = sorted(by_url.values(), key=lambda h: h.score, reverse=True)
    return ranked[:_TOP_K]


class _RawBrief(BaseModel):
    """What the model is actually asked for.

    Deliberately narrower than `CopilotBrief`: citations are rebuilt from the
    `[n]` markers against the hits we retrieved, so asking the model to echo a
    dozen citation objects back only spends completion tokens -- enough to push
    the request past a free-tier per-minute budget -- and gives a small local
    model one more shape to get wrong and fail validation on.
    """

    summary: str = ""
    differentials: list[str] = []
    recommended_procedures: list[str] = []
    cautions: list[str] = []
    confidence: float = 0.0


def _ungrounded_summary(measured_labs: list[dict], triage: dict | None) -> str:
    """What can honestly be said when the model or the corpus let us down.

    Only facts we hold directly: the values read off this patient's reports and
    the triage score. No guideline claim, because nothing here is cited.
    """
    parts: list[str] = [
        "Guideline grounding was unavailable, so this is a factual readout of "
        "the visit record rather than a clinical brief."
    ]

    abnormal = [lab for lab in measured_labs if lab.get("flag") in ("critical", "high", "low")]
    if abnormal:
        listed = "; ".join(
            "{name} {value}{unit} ({flag}, ref {low}-{high})".format(
                name=lab["test_name"],
                value=lab["value"],
                unit=f" {lab['unit']}" if lab.get("unit") else "",
                flag=lab.get("flag"),
                low=lab.get("ref_low") if lab.get("ref_low") is not None else "?",
                high=lab.get("ref_high") if lab.get("ref_high") is not None else "?",
            )
            for lab in abnormal[:8]
        )
        parts.append(f"Values outside the reference range: {listed}.")
        normal = len(measured_labs) - len(abnormal)
        if normal:
            parts.append(f"{normal} further value(s) read within range.")
    elif measured_labs:
        parts.append(
            f"All {len(measured_labs)} value(s) read from the uploaded reports are "
            "within their reference ranges."
        )
    else:
        parts.append("No lab values have been extracted from this patient's reports yet.")

    if triage:
        parts.append(
            f"Triage recorded ESI {triage.get('severity_esi', 'n/a')} "
            f"({triage.get('triage_colour', 'n/a')}), suggested specialty "
            f"{triage.get('specialty', 'n/a')}."
        )

    parts.append("Rebuild the brief once the language model is reachable again.")
    return " ".join(parts)


async def build_brief(visit_id: UUID, db: AsyncSession) -> CopilotBrief:
    visit = await _load_visit(db, visit_id)
    patient = await db.get(Patient, visit.patient_id)
    if patient is None:
        raise ApiError("NOT_FOUND", "patient not found for visit", status_code=404)

    context = await patient_context(visit.patient_id)

    triage: dict | None = None
    if visit.triage_session_id:
        triage_session = await db.get(TriageSession, visit.triage_session_id)
        if triage_session and triage_session.result:
            triage = triage_session.result

    lab_rows = (
        await db.execute(
            select(LabResult)
            .where(LabResult.patient_id == visit.patient_id)
            .order_by(LabResult.observed_at.desc().nullslast())
        )
    ).scalars().all()
    # Every measured value, not only the flagged ones: a normal platelet count
    # is what rules dengue out, and a brief that never saw it cannot say so.
    measured_labs = [
        {
            "test_name": lab.test_name,
            "value": lab.value_num if lab.value_num is not None else lab.value_text,
            "unit": lab.unit,
            "ref_low": lab.ref_low,
            "ref_high": lab.ref_high,
            "flag": lab.flag,
        }
        for lab in lab_rows
    ]
    abnormal_labs = [
        {
            "test_name": lab.test_name,
            "normalized_name": lab.normalized_name,
            "value": lab.value_num if lab.value_num is not None else lab.value_text,
            "unit": lab.unit,
            "flag": lab.flag,
        }
        for lab in lab_rows
        if lab.flag in ("critical", "high", "low")
    ]
    # TEMP-ADAPTER: cross-checks Virat's rule-based flags against ours; returns
    # [] until app/ml/tools.flag_labs ships, so this is a no-op enrichment today.
    extra_flags = await flag_labs(visit.patient_id, abnormal_labs)
    if extra_flags:
        abnormal_labs = extra_flags

    queries = _build_axis_queries(patient, context, triage, abnormal_labs)
    hits = await _retrieve_deduped(queries)

    context_block = "\n".join(
        f"[{i + 1}] {h.metadata.get('title', 'untitled')} ({h.metadata.get('region', 'INTL')}): "
        f"{h.text[:300]}"
        for i, h in enumerate(hits)
    )
    patient_block = (
        f"Conditions: {[c.get('name') for c in context.get('conditions', [])]}\n"
        f"Medications: {[m.get('name') for m in context.get('medications', [])]}\n"
        f"Allergies: {[a.get('name') for a in context.get('allergies', [])]}\n"
        f"Abnormal labs: {[(lab.get('test_name'), lab.get('flag')) for lab in abnormal_labs]}\n"
        f"Triage: severity_esi={triage.get('severity_esi') if triage else 'n/a'}, "
        f"specialty={triage.get('specialty') if triage else 'n/a'}"
    )

    # The measured values are the part of the brief that is about this patient
    # rather than about the literature, so they go in verbatim -- value, unit
    # and the lab's own reference range -- instead of a bare flag word.
    if measured_labs:
        lines = [
            "{name}: {value}{unit} (ref {low}-{high}) [{flag}]".format(
                name=lab["test_name"],
                value=lab["value"],
                unit=f" {lab['unit']}" if lab.get("unit") else "",
                low=lab.get("ref_low") if lab.get("ref_low") is not None else "?",
                high=lab.get("ref_high") if lab.get("ref_high") is not None else "?",
                flag=lab.get("flag") or "unknown",
            )
            for lab in measured_labs
        ]
        lab_block = "Measured lab values from this patient's uploaded reports:\n" + "\n".join(
            lines
        )
    else:
        lab_block = "No lab values have been extracted from this patient's reports yet."

    prompt = (
        f"Patient context:\n{patient_block}\n\n"
        f"{lab_block}\n\n"
        f"Retrieved clinical excerpts (cite as [n]):\n{context_block or '(none retrieved)'}\n\n"
        "Produce a CopilotBrief JSON with fields: summary, differentials, "
        "recommended_procedures, cautions, confidence (0-1).\n"
        "`summary` must be four to six sentences and must read as a note about "
        "THIS patient: quote the measured values that matter by name, number and "
        "unit, say which fall outside the reference range and in which direction, "
        "name the pattern they form, and state what the normal values rule out. "
        "Cite [n] for every claim taken from the excerpts; the patient's own "
        "measured value needs no citation.\n"
        "`differentials` are ordered most to least likely, each naming the "
        "specific finding that supports it.\n"
        "`recommended_procedures` are concrete next steps -- which test to "
        "repeat and when, which examination, which referral -- not general advice.\n"
        "`cautions` covers interactions, allergy conflicts, contraindications, "
        "and any value needing same-day action.\n"
        "Do not emit a citations field; the [n] markers in the prose are the "
        "citations."
    )

    if not hits:
        return CopilotBrief(
            visit_id=visit_id,
            summary=_ungrounded_summary(measured_labs, triage),
            differentials=[],
            recommended_procedures=[],
            cautions=[],
            citations=[],
            confidence=0.0,
        )

    raw = await json_complete(prompt, schema=_RawBrief, system=CLINICAL_BRIEF_SYSTEM)

    # Citations are rebuilt from the retrieved excerpt a marker points at,
    # never from what the model wrote about it. Matching on model-supplied
    # titles dropped every citation whenever the model paraphrased the title
    # -- routine for smaller local models -- which silently collapsed the
    # brief to confidence 0 despite perfectly good retrieval.
    summary = _normalise_markers(raw.summary)
    cautions = [_normalise_markers(c) for c in raw.cautions]

    cited: set[int] = {
        int(n) for text in (summary, *cautions) for n in _CITE_MARKER.findall(text)
    }
    # An excerpt number is only usable if it indexes a hit we actually retrieved.
    resolved = sorted(n for n in cited if 1 <= n <= len(hits))
    renumber = {old: new for new, old in enumerate(resolved, start=1)}

    kept_citations = [
        Citation(
            n=renumber[old],
            title=hits[old - 1].metadata.get("title", "untitled"),
            source=hits[old - 1].metadata.get("source", "unknown"),
            url=hits[old - 1].metadata.get("url"),
            snippet=hits[old - 1].text[:300],
            published=hits[old - 1].metadata.get("published"),
        )
        for old in resolved
    ]

    def _remap(text: str) -> str:
        """Renumber surviving markers and drop the ones nothing backs."""

        def replace(match: re.Match[str]) -> str:
            old = int(match.group(1))
            return f"[{renumber[old]}]" if old in renumber else ""

        return _CITE_MARKER.sub(replace, text).replace("  ", " ").strip()

    summary = _remap(summary)
    cautions = [_remap(c) for c in cautions]

    confidence = raw.confidence if kept_citations else 0.0
    if not kept_citations:
        # Concatenating retrieved snippets here used to produce a "brief" that
        # spliced a dengue fact sheet into an amoxicillin interaction into a TB
        # abstract -- unreadable, and about no patient in particular. When the
        # generation cannot be grounded, report the patient's own measurements,
        # which are certain, and say plainly that the guidance is missing.
        summary = _ungrounded_summary(measured_labs, triage)

    brief = CopilotBrief(
        visit_id=visit_id,
        summary=summary,
        differentials=raw.differentials,
        recommended_procedures=raw.recommended_procedures,
        cautions=cautions,
        citations=kept_citations,
        confidence=confidence,
    )

    log.info(
        "clinical_brief_built",
        visit_id=str(visit_id),
        citations=len(kept_citations),
        confidence=confidence,
    )
    return brief
