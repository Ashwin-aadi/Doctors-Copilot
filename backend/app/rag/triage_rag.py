"""Pre-assessment triage conversation: one question per turn, red-flag safety net
on every turn, and a guideline-grounded finalize step producing a TriageResult."""

import re
from pathlib import Path
from uuid import UUID

import yaml
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.logging import get_logger
from app.db.models.clinical import TriageSession
from app.llm.gateway import complete, json_complete
from app.llm.prompts import RED_FLAG_SYSTEM, TRIAGE_FINALIZE_SYSTEM, TRIAGE_QUESTION_SYSTEM
from app.rag.retriever import hybrid
from app.schemas.common import Citation
from app.schemas.triage import SuggestedLab, TriageResult, TriageTurnOut

log = get_logger(__name__)

MAX_QUESTIONS = 8
_DATA_DIR = Path(__file__).parent / "data"

_esi_data = yaml.safe_load((_DATA_DIR / "esi_rules.yaml").read_text(encoding="utf-8"))
_RED_FLAG_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _esi_data["red_flag_patterns"]]


class _RedFlagCheck(BaseModel):
    red_flag: bool = False
    reason: str = ""


def _regex_red_flag(text: str) -> str | None:
    for pattern in _RED_FLAG_PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    return None


async def _llm_red_flag(text: str) -> str | None:
    check = await json_complete(text, schema=_RedFlagCheck, system=RED_FLAG_SYSTEM)
    return check.reason if check.red_flag else None


async def _check_red_flags(text: str) -> list[str]:
    flags: list[str] = []
    regex_hit = _regex_red_flag(text)
    if regex_hit:
        flags.append(f"pattern match: {regex_hit}")
    llm_hit = await _llm_red_flag(text)
    if llm_hit:
        flags.append(llm_hit)
    return flags


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


async def _ask_question(transcript: list[dict]) -> str:
    prompt = (
        "Patient intake transcript so far:\n"
        f"{_transcript_text(transcript) or '(no answers yet)'}\n\n"
        "Ask the single next most useful triage question."
    )
    question = await complete(prompt, system=TRIAGE_QUESTION_SYSTEM, max_tokens=80, temperature=0.3)
    return question.strip()


async def start(db: AsyncSession, patient_id: UUID | None) -> TriageTurnOut:
    session = TriageSession(patient_id=patient_id, transcript=[], result=None)
    db.add(session)
    await db.flush()

    question = await _ask_question([])
    transcript = [{"role": "assistant", "content": question}]
    session.transcript = transcript
    await db.commit()

    return TriageTurnOut(
        session_id=session.id,
        assistant=question,
        done=False,
        quick_replies=[],
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
            "Thanks — based on what you've described, this needs prompt clinical "
            "attention. Finalizing your triage now."
            if red_flags
            else "Thanks, that's everything I need. Finalizing your triage now."
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


async def finalize(db: AsyncSession, session_id: UUID) -> TriageResult:
    session = await _get_session(db, session_id)
    transcript = list(session.transcript or [])
    transcript_text = _transcript_text(transcript)

    red_flags: list[str] = []
    for t in transcript:
        if t.get("role") == "user":
            hit = _regex_red_flag(t["content"])
            if hit:
                red_flags.append(f"pattern match: {hit}")

    hits = await hybrid("guidelines", transcript_text or "general intake", k=8)
    context_block = "\n".join(
        f"[{i + 1}] {h.metadata.get('title', 'untitled')}: {h.text[:400]}"
        for i, h in enumerate(hits)
    )

    prompt = (
        f"Patient intake transcript:\n{transcript_text}\n\n"
        f"Retrieved guideline excerpts (cite as [n]):\n{context_block}\n\n"
        "Produce a TriageResult JSON with fields: severity_esi (1-5), specialty, "
        "red_flags (list of strings), suggested_labs (list of {name, loinc, reason, "
        "source}), rationale (cite [n] for every guideline-derived claim), "
        "citations (list of {n, title, source, url, snippet, published} matching "
        "the excerpts above), confidence (0-1)."
    )

    class _RawTriage(BaseModel):
        severity_esi: int = 3
        specialty: str = "general_medicine"
        red_flags: list[str] = []
        suggested_labs: list[SuggestedLab] = []
        rationale: str = ""
        citations: list[Citation] = []
        confidence: float = 0.0

    raw = await json_complete(prompt, schema=_RawTriage, system=TRIAGE_FINALIZE_SYSTEM)

    valid_hit_titles = {h.metadata.get("title", "") for h in hits}
    kept_citations = [c for c in raw.citations if c.title in valid_hit_titles]
    kept_numbers = {c.n for c in kept_citations}
    rationale = raw.rationale
    for c in raw.citations:
        if c.n not in kept_numbers:
            rationale = re.sub(rf"\[{c.n}\]", "", rationale)
    for i, c in enumerate(kept_citations, start=1):
        c.n = i

    if red_flags:
        severity = min(raw.severity_esi or 5, 2)
    else:
        severity = raw.severity_esi or 3
    severity = max(1, min(5, severity))

    confidence = raw.confidence if kept_citations else 0.0
    if not raw.rationale and not kept_citations:
        confidence = 0.0
        rationale = rationale or "Extractive summary: " + (hits[0].text[:200] if hits else "")

    triage_result = TriageResult(
        session_id=session.id,
        patient_id=session.patient_id,
        severity_esi=severity,
        specialty=raw.specialty or "general_medicine",
        red_flags=list({*raw.red_flags, *red_flags}),
        suggested_labs=raw.suggested_labs,
        rationale=rationale,
        citations=kept_citations,
        confidence=confidence,
    )

    session.result = triage_result.model_dump(mode="json")
    await db.commit()

    log.info("triage_finalized", session_id=str(session.id), esi=triage_result.severity_esi)
    return triage_result


async def get_result(db: AsyncSession, session_id: UUID) -> TriageResult:
    session = await _get_session(db, session_id)
    if session.result is None:
        raise ApiError("NOT_FOUND", "triage result not yet finalized", status_code=404)
    return TriageResult.model_validate(session.result)
