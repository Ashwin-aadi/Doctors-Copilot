"""SOAP clinical summary generator.

`build_summary` assembles S/O/A/P deterministically from the visit's triage
transcript, the patient's flagged labs, and completed-document text, then
asks the LLM gateway (`app.llm.gateway.json_complete`) to phrase it as a
`SoapSummary`. Every fact fed into the prompt carries a numbered `[n]`
citation tag built here, not by the model; a post-check drops any output
sentence containing a number that doesn't also appear in the assembled
context, so the model can add prose but never invent a value.

Owns its own DB session (`SessionLocal`) since the frozen §4.2 signature --
`build_summary(req: SummaryRequest) -> SoapSummary` -- carries no `db` param.
"""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.clinical import LabResult, TriageSession, Visit
from app.db.models.document import Document
from app.db.models.patient import Patient
from app.db.session import SessionLocal
from app.kg.queries import patient_context
from app.llm.gateway import json_complete
from app.ml.schemas_ml import SummaryRequest
from app.schemas.common import Citation
from app.schemas.ml import SoapSummary

_NUMBER_RE = re.compile(r"\d+\.?\d*")
_CITATION_TAG_RE = re.compile(r"\[\d+\]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_FLAG_ORDER = {"critical": 0, "high": 1, "low": 2, "normal": 3, "unknown": 4}

# India-endemic conditions to keep in the differential when the symptom/lab
# pattern is consistent with them, instead of defaulting to Western-prevalence
# assumptions (per V3.2 spec).
_ENDEMIC_RULES: list[tuple[str, list[str], list[str]]] = [
    ("dengue", ["fever", "rash", "joint pain", "body ache", "retro-orbital"], ["platelet_count", "platelets"]),
    ("malaria", ["fever", "chills", "rigor", "sweating"], []),
    ("typhoid", ["fever", "abdominal pain", "constipation", "diarrhoea", "diarrhea"], []),
    ("tuberculosis", ["cough", "weight loss", "night sweats", "haemoptysis", "hemoptysis"], []),
    ("chikungunya", ["fever", "joint pain", "rash"], []),
    ("anaemia", ["fatigue", "weakness", "pallor", "breathlessness"], ["hemoglobin", "haemoglobin"]),
]


async def _load(
    db: AsyncSession, patient_id: UUID, visit_id: UUID
) -> tuple[Patient | None, Visit | None, TriageSession | None, list[LabResult], list[Document]]:
    patient = await db.get(Patient, patient_id)
    visit = await db.get(Visit, visit_id)
    triage: TriageSession | None = None
    if visit is not None and visit.triage_session_id:
        triage = await db.get(TriageSession, visit.triage_session_id)
    lab_rows = (
        (await db.execute(select(LabResult).where(LabResult.patient_id == patient_id)))
        .scalars()
        .all()
    )
    doc_rows = (
        (
            await db.execute(
                select(Document).where(
                    Document.patient_id == patient_id, Document.status == "done"
                )
            )
        )
        .scalars()
        .all()
    )
    return patient, visit, triage, list(lab_rows), list(doc_rows)


def _reported_symptoms(triage: TriageSession | None) -> str:
    if triage is None:
        return ""
    turns = [
        str(turn.get("content", ""))
        for turn in (triage.transcript or [])
        if isinstance(turn, dict) and turn.get("role") == "user"
    ]
    return " ".join(t for t in turns if t)


def _add_citation(citations: list[Citation], *, title: str, source: str, snippet: str) -> int:
    n = len(citations) + 1
    citations.append(Citation(n=n, title=title, source=source, snippet=snippet[:400]))
    return n


def _subjective(
    context: dict, triage: TriageSession | None, citations: list[Citation]
) -> tuple[str, str]:
    """Returns (prompt_text, raw_symptoms_for_endemic_matching)."""
    parts: list[str] = []
    symptoms = _reported_symptoms(triage)
    if symptoms:
        n = _add_citation(citations, title="Patient-reported symptoms", source="triage_transcript", snippet=symptoms)
        parts.append(f"Patient reports: {symptoms} [{n}]")

    if triage is not None and triage.result:
        rationale = triage.result.get("rationale")
        if rationale:
            n = _add_citation(citations, title="Triage rationale", source="triage_result", snippet=rationale)
            parts.append(f"Triage assessment: {rationale} [{n}]")

    for cond in context.get("conditions", []):
        name = cond.get("name") if isinstance(cond, dict) else None
        if not name:
            continue
        n = _add_citation(citations, title=f"History: {name}", source="patient_history", snippet=name)
        parts.append(f"History of {name} [{n}]")

    if not parts:
        parts.append("No subjective history available.")
    return " ".join(parts), symptoms


def _objective(
    lab_rows: list[LabResult], doc_rows: list[Document], citations: list[Citation]
) -> str:
    parts: list[str] = []
    ordered = sorted(lab_rows, key=lambda lab: _FLAG_ORDER.get(lab.flag, 4))
    for lab in ordered:
        value = lab.value_num if lab.value_num is not None else lab.value_text
        snippet = f"{lab.test_name}: {value} {lab.unit or ''} (reference {lab.ref_low}-{lab.ref_high}, flag={lab.flag})"
        n = _add_citation(citations, title=lab.test_name, source="lab_result", snippet=snippet)
        parts.append(f"{lab.test_name} {value}{lab.unit or ''} [{lab.flag}] [{n}]")

    for doc in doc_rows:
        if doc.text:
            excerpt = doc.text[:300]
            n = _add_citation(citations, title="Document finding", source="document", snippet=excerpt)
            parts.append(f"Document finding: {excerpt} [{n}]")

    if not parts:
        parts.append("No objective findings recorded.")
    return " ".join(parts)


def _endemic_differentials(symptoms: str, lab_rows: list[LabResult]) -> list[str]:
    symptoms_l = symptoms.lower()
    abnormal_names = {lab.normalized_name.lower() for lab in lab_rows if lab.flag in ("critical", "high", "low")}
    matches: list[str] = []
    for condition, symptom_keywords, lab_keywords in _ENDEMIC_RULES:
        symptom_hit = any(kw in symptoms_l for kw in symptom_keywords)
        lab_hit = not lab_keywords or any(kw in abnormal_names for kw in lab_keywords)
        if symptom_hit and lab_hit:
            matches.append(condition)
    return matches


async def _differentials(
    db: AsyncSession,
    visit: Visit | None,
    subjective_text: str,
    objective_text: str,
    symptoms: str,
    lab_rows: list[LabResult],
) -> list[str]:
    from app.schemas.visit import VisitState

    differentials: list[str] = []
    if visit is not None and visit.state in (
        VisitState.BRIEF_READY.value,
        VisitState.CONSULTED.value,
        VisitState.PRESCRIBED.value,
    ):
        try:
            from app.rag.clinical_rag import build_brief

            brief = await build_brief(visit.id, db)
            differentials = list(brief.differentials)
        except Exception:  # noqa: BLE001 -- brief assembly is best-effort here
            differentials = []

    if not differentials:
        from app.ml.ner import extract

        bundle = await extract(f"{subjective_text} {objective_text}")
        seen: set[str] = set()
        for cond in bundle.conditions:
            key = cond.text.lower()
            if cond.negated or key in seen:
                continue
            seen.add(key)
            differentials.append(cond.text)

    endemic = _endemic_differentials(symptoms, lab_rows)
    existing_l = {d.lower() for d in differentials}
    for condition in endemic:
        if condition not in existing_l:
            differentials.insert(0, condition)
            existing_l.add(condition)

    return differentials


async def _plan(
    context: dict,
    lab_rows: list[LabResult],
    citations: list[Citation],
) -> str:
    parts: list[str] = []

    pending = [lab.test_name for lab in lab_rows if lab.flag == "unknown"]
    if pending:
        parts.append(f"Pending/unreviewed results: {', '.join(pending)}.")

    medications = [
        (med.get("name") if isinstance(med, dict) else med)
        for med in context.get("medications", [])
        if med
    ]
    allergies = [
        (a.get("name") if isinstance(a, dict) else a) for a in context.get("allergies", []) if a
    ]
    conditions = [
        (c.get("name") if isinstance(c, dict) else c) for c in context.get("conditions", []) if c
    ]
    if medications:
        try:
            from app.ml.safety import check_interactions
            from app.ml.schemas_ml import InteractionRequest

            report = await check_interactions(
                InteractionRequest(medications=medications, allergies=allergies, conditions=conditions)
            )
            for pair in report.pairs:
                n = _add_citation(
                    citations,
                    title=f"Interaction: {pair.drug_a} + {pair.drug_b}",
                    source=pair.evidence_source,
                    snippet=pair.mechanism,
                )
                parts.append(
                    f"Safety: {pair.drug_a} + {pair.drug_b} is a {pair.severity} interaction [{n}]."
                )
            for conflict in report.allergy_conflicts:
                n = _add_citation(
                    citations,
                    title=f"Allergy conflict: {conflict.drug}",
                    source=conflict.source,
                    snippet=conflict.rationale,
                )
                parts.append(f"Safety: {conflict.drug} conflicts with allergy to {conflict.allergen} [{n}].")
        except Exception:  # noqa: BLE001 -- safety check is best-effort in the plan section
            pass

    parts.append("Follow-up as clinically indicated; findings require doctor review before action.")
    if not parts:
        parts.append("No specific plan items identified.")
    return " ".join(parts)


def _strip_hallucinated_numbers(text: str, context_numbers: set[str]) -> str:
    sentences = _SENTENCE_SPLIT_RE.split(text.strip())
    kept: list[str] = []
    for sentence in sentences:
        if not sentence.strip():
            continue
        bare = _CITATION_TAG_RE.sub("", sentence)
        numbers = _NUMBER_RE.findall(bare)
        if all(num in context_numbers for num in numbers):
            kept.append(sentence)
    return " ".join(kept)


async def build_summary(req: SummaryRequest) -> SoapSummary:
    async with SessionLocal() as db:
        patient, visit, triage, lab_rows, doc_rows = await _load(db, req.patient_id, req.visit_id)
        context = await patient_context(req.patient_id)

        citations: list[Citation] = []
        subjective_text, symptoms = _subjective(context, triage, citations)
        objective_text = _objective(lab_rows, doc_rows, citations)
        differentials = await _differentials(db, visit, subjective_text, objective_text, symptoms, lab_rows)
        plan_text = await _plan(context, lab_rows, citations)

        assessment_parts = []
        if differentials:
            assessment_parts.append("Differential diagnoses: " + ", ".join(differentials) + ".")
        else:
            assessment_parts.append("No differential diagnosis could be assembled from available data.")
        assessment_text = " ".join(assessment_parts)

        context_block = (
            f"SUBJECTIVE CONTEXT:\n{subjective_text}\n\n"
            f"OBJECTIVE CONTEXT:\n{objective_text}\n\n"
            f"ASSESSMENT CONTEXT:\n{assessment_text}\n\n"
            f"PLAN CONTEXT:\n{plan_text}"
        )
        raw_context_text = " ".join([subjective_text, objective_text, assessment_text, plan_text])
        context_numbers = set(_NUMBER_RE.findall(_CITATION_TAG_RE.sub("", raw_context_text)))

        prompt = (
            "You are drafting a doctor-facing SOAP note from the context below. "
            "Do not state any fact, value, or number that is not present in the context. "
            "Preserve every [n] citation marker exactly as given; do not invent new ones.\n\n"
            f"{context_block}\n\n"
            "Return a JSON object with fields: subjective, objective, assessment, plan "
            "(each a short paragraph of prose reusing the [n] markers), confidence (0-1)."
        )

        result = await json_complete(prompt, schema=SoapSummary)

        subjective = _strip_hallucinated_numbers(result.subjective or subjective_text, context_numbers)
        objective = _strip_hallucinated_numbers(result.objective or objective_text, context_numbers)
        assessment = _strip_hallucinated_numbers(result.assessment or assessment_text, context_numbers)
        plan = _strip_hallucinated_numbers(result.plan or plan_text, context_numbers)

        confidence = min(0.95, 0.3 + 0.05 * min(len(citations), 12))
        if not subjective and not objective:
            confidence = 0.1

        return SoapSummary(
            subjective=subjective or subjective_text,
            objective=objective or objective_text,
            assessment=assessment or assessment_text,
            plan=plan or plan_text,
            citations=citations,
            confidence=confidence,
        )
