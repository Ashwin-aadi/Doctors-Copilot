"""Patient-facing chatbot.

Retrieval is deliberately narrow: the patient's own `patient_{id}` collection
(k=6) plus the general-education `lay` collection (k=4). The doctor-facing
`clinical` collection -- drug labels, guideline protocol text -- is never
reachable from this path, so a patient cannot be handed prescribing guidance
through the chat window.

Every answer runs the full guardrail stack: PII is stripped before the prompt
leaves the process, citations that do not resolve are dropped, poorly supported
sentences are removed, and anything that reads like an emergency gets the
emergency banner and, where the patient is in a queue, an escalation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.patient import Patient
from app.db.models.scheduling import QueueEntry
from app.llm.gateway import complete
from app.llm.prompts import PATIENT_CHAT_SYSTEM
from app.rag import guardrails
from app.rag.ingest_patient import LAY_COLLECTION, patient_collection
from app.rag.retriever import hybrid
from app.rag.store import Hit
from app.schemas.common import Citation

log = get_logger(__name__)

K_OWN_RECORDS = 6
K_LAY = 4

# Phrasing that means the patient is asking us to change treatment. The system
# prompt forbids it too, but a deterministic check is what actually holds when
# the model is having an off day or the extractive fallback is in play.
_DOSE_CHANGE_PATTERNS = (
    "should i stop",
    "should i start",
    "can i stop",
    "can i start",
    "should i take",
    "can i take",
    "increase my dose",
    "decrease my dose",
    "reduce my dose",
    "double the dose",
    "double my dose",
    "skip my",
    "change my medicine",
    "change my dose",
    "how many tablets",
    "what dose",
    "which antibiotic",
    "prescribe",
)

_MEDICATION_REFUSAL = (
    "I cannot advise you to start, stop or change any medicine, or suggest a dose "
    "— only your doctor can do that after seeing you. What I can do is explain what "
    "is written in your own reports and prescriptions in simple language. Please "
    "discuss this question with your doctor, and if you feel unwell in the meantime, "
    "go to the clinic. In an emergency call 112, or 108 for an ambulance."
)


def is_medication_change_request(message: str) -> bool:
    lowered = message.lower()
    return any(pattern in lowered for pattern in _DOSE_CHANGE_PATTERNS)


async def resolve_patient_for_user(db: AsyncSession, user_id: UUID) -> Patient | None:
    result = await db.execute(select(Patient).where(Patient.user_id == user_id))
    return result.scalar_one_or_none()


async def _retrieve(patient_id: UUID, message: str) -> list[Hit]:
    own = await hybrid(patient_collection(patient_id), message, k=K_OWN_RECORDS)
    lay = await hybrid(LAY_COLLECTION, message, k=K_LAY)
    return own + lay


def _citations(hits: list[Hit]) -> list[Citation]:
    return [
        Citation(
            n=i + 1,
            title=hit.metadata.get("title") or "Your record",
            source=hit.metadata.get("source") or "Doctor's Copilot",
            url=hit.metadata.get("url") or None,
            snippet=hit.text[:300],
            published=hit.metadata.get("published") or None,
        )
        for i, hit in enumerate(hits)
    ]


async def _active_queue_entry(db: AsyncSession, patient_id: UUID) -> UUID | None:
    result = await db.execute(
        select(QueueEntry.id)
        .where(QueueEntry.patient_id == patient_id, QueueEntry.status == "waiting")
        .order_by(QueueEntry.enqueued_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def answer(
    db: AsyncSession,
    patient: Patient,
    message: str,
    history: list[dict] | None = None,
) -> tuple[str, list[Citation], float]:
    """Produce one guarded answer. Used by the SSE route and by the tests."""

    history = history or []

    if is_medication_change_request(message):
        log.info("patient_chat_medication_refusal", patient_id=str(patient.id))
        return _MEDICATION_REFUSAL, [], 1.0

    hits = await _retrieve(patient.id, message)
    citations = _citations(hits)

    if not hits:
        text = (
            "I could not find anything in your records that answers this. Your "
            "reports may not be uploaded yet. Please ask your doctor at your next "
            "visit, and bring your old reports with you."
        )
        return text, [], 0.0

    context_block = "\n".join(
        f"[{i + 1}] {h.metadata.get('title', 'Your record')}: {h.text[:500]}"
        for i, h in enumerate(hits)
    )
    history_block = "\n".join(f"{turn['role']}: {turn['content']}" for turn in history[-6:])

    raw_prompt = (
        f"Earlier in this conversation:\n{history_block or '(this is the first message)'}\n\n"
        f"Excerpts from this patient's own records and from general health "
        f"information (cite as [n]):\n{context_block}\n\n"
        f"The patient asks: {message}\n\n"
        "Answer in plain English using only these excerpts. Put a [n] marker after "
        "every sentence that uses an excerpt. End with a line telling them to "
        "discuss it with their doctor."
    )

    # Pass 1: the model never sees the patient's name, phone, ABHA id or any
    # record UUID. Values are put back with `pii.restore` after generation.
    redacted_prompt, pii = guardrails.redact_pii(raw_prompt, names=[patient.name])

    generated = await complete(
        redacted_prompt, system=PATIENT_CHAT_SYSTEM, max_tokens=700, temperature=0.2
    )

    if guardrails.SCOPE_REFUSAL_MARKER in generated:
        log.info("patient_chat_scope_refusal", patient_id=str(patient.id))
        return generated.strip(), [], 1.0

    # Passes 2 and 3: unresolvable citations out, unsupported sentences out,
    # mean support becomes the confidence we report.
    cleaned, confidence = guardrails.apply_all(generated, hits)
    cleaned = pii.restore(cleaned)

    if not cleaned.strip():
        cleaned = (
            "I could not explain this safely from what is in your records. "
            "Please ask your doctor to go through this report with you."
        )
        confidence = 0.0

    if "doctor" not in cleaned.lower():
        cleaned += "\n\nPlease discuss this with your doctor at your next visit."

    # Pass 4: an emergency in the question outranks everything above it.
    queue_entry_id = await _active_queue_entry(db, patient.id)
    red_flags = _red_flag_terms(message)
    cleaned, _escalated = await guardrails.emergency_intercept(
        severity_esi=None,
        red_flags=red_flags,
        queue_entry_id=queue_entry_id,
        text=cleaned,
    )

    used = guardrails.cited_markers(cleaned)
    citations = [c for c in citations if c.n in used] or citations[:3]

    return cleaned, citations, confidence


_RED_FLAG_TERMS = (
    "chest pain",
    "cannot breathe",
    "can't breathe",
    "breathless",
    "unconscious",
    "fainted",
    "seizure",
    "fits",
    "bleeding heavily",
    "vomiting blood",
    "black stool",
    "coughing blood",
    "snake bite",
    "snakebite",
    "poison",
    "suicide",
    "kill myself",
    "stroke",
    "slurred speech",
)


def _red_flag_terms(message: str) -> list[str]:
    lowered = message.lower()
    return [term for term in _RED_FLAG_TERMS if term in lowered]


async def chat_stream(
    db: AsyncSession,
    patient: Patient,
    message: str,
    history: list[dict] | None = None,
) -> AsyncIterator[dict]:
    """Yield SSE events: `token` repeatedly, then `citation` per source, then `done`.

    The answer is guarded in full before the first token leaves, so a sentence
    can never be streamed to the patient and then retracted.
    """

    try:
        text, citations, confidence = await answer(db, patient, message, history)
    except Exception as exc:  # noqa: BLE001
        log.warning("patient_chat_failed", patient_id=str(patient.id), error=str(exc))
        yield {"event": "error", "data": {"code": "INTERNAL", "message": "chat unavailable"}}
        return

    chunk = 48
    for i in range(0, len(text), chunk):
        yield {"event": "token", "data": {"text": text[i : i + chunk]}}

    for citation in citations:
        yield {"event": "citation", "data": citation.model_dump(mode="json")}

    yield {"event": "done", "data": {"confidence": confidence}}
