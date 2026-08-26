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
_TOP_K = 12


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
    summary: str = ""
    differentials: list[str] = []
    recommended_procedures: list[str] = []
    cautions: list[str] = []
    citations: list[Citation] = []
    confidence: float = 0.0


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
        await db.execute(select(LabResult).where(LabResult.patient_id == visit.patient_id))
    ).scalars().all()
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
        f"{h.text[:400]}"
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

    prompt = (
        f"Patient context:\n{patient_block}\n\n"
        f"Retrieved clinical excerpts (cite as [n]):\n{context_block or '(none retrieved)'}\n\n"
        "Produce a CopilotBrief JSON with fields: summary (cite [n] for every "
        "clinical claim), differentials (list of strings), recommended_procedures "
        "(list of strings), cautions (list of strings covering interactions, "
        "allergy conflicts, and contraindications), citations (list of {n, title, "
        "source, url, snippet, published} matching the excerpts above), "
        "confidence (0-1)."
    )

    if not hits:
        return CopilotBrief(
            visit_id=visit_id,
            summary="Insufficient retrieved clinical context to generate a grounded brief.",
            differentials=[],
            recommended_procedures=[],
            cautions=[],
            citations=[],
            confidence=0.0,
        )

    raw = await json_complete(prompt, schema=_RawBrief, system=CLINICAL_BRIEF_SYSTEM)

    valid_titles = {h.metadata.get("title", "") for h in hits}
    kept_citations = [c for c in raw.citations if c.title in valid_titles]
    kept_numbers = {c.n for c in kept_citations}

    def _strip_unresolved(text: str) -> str:
        for c in raw.citations:
            if c.n not in kept_numbers:
                text = re.sub(rf"\[{c.n}\]", "", text)
        return text

    summary = _strip_unresolved(raw.summary)
    cautions = [_strip_unresolved(c) for c in raw.cautions]

    for i, c in enumerate(kept_citations, start=1):
        c.n = i

    confidence = raw.confidence if kept_citations else 0.0
    if not kept_citations:
        summary = "Extractive summary (unable to ground a generated brief): " + " ".join(
            h.text[:200] for h in hits[:3]
        )

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
