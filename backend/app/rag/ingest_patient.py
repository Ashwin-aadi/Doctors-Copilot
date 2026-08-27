"""Per-patient plain-language corpus for the patient chatbot.

Two collections feed `app.rag.patient_chat`:

* ``patient_{patient_id}`` -- the patient's OWN records (lab results, uploaded
  documents, prescriptions, visit summaries), rewritten into short
  plain-language chunks at upsert time. One collection per patient means a
  cross-patient read is structurally impossible, not just filtered out.
* ``lay`` -- general health education. MedlinePlus pages when the network is
  reachable, otherwise the bundled `data/lay_corpus.yaml` entries, which are
  written in-house at roughly an 8th-standard reading level.

The `clinical` collection is deliberately NOT reachable from here: doctor-facing
drug labels and guideline text are not safe patient-facing reading.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models.clinical import LabResult, Prescription, TriageSession, Visit
from app.db.models.document import Document
from app.rag.store import Chunk, VectorStore

log = get_logger(__name__)
settings = get_settings()

_DATA_DIR = Path(__file__).parent / "data"
LAY_COLLECTION = "lay"

_FLAG_WORDS = {
    "critical": "far outside the usual range and needs a doctor's attention",
    "high": "higher than the usual range",
    "low": "lower than the usual range",
    "normal": "within the usual range",
    "unknown": "reported without a reference range",
}


def patient_collection(patient_id: UUID) -> str:
    return f"patient_{patient_id}"


def _chunk_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()  # noqa: S324


def _metadata(**overrides: Any) -> dict:
    base = {
        "source": "doctors-copilot",
        "title": "Your record",
        "url": "",
        "section": "record",
        "doc_type": "patient_record",
        "published": "",
    }
    base.update({k: v for k, v in overrides.items() if v is not None})
    return base


# ---------------------------------------------------------------- record text


def _lab_sentence(lab: LabResult) -> str:
    value = lab.value_num if lab.value_num is not None else (lab.value_text or "")
    unit = f" {lab.unit}" if lab.unit else ""
    said = _FLAG_WORDS.get(lab.flag, _FLAG_WORDS["unknown"])
    ref = ""
    if lab.ref_low is not None and lab.ref_high is not None:
        ref = f" The usual range printed on the report is {lab.ref_low} to {lab.ref_high}{unit}."
    when = f" It was taken on {lab.observed_at:%d/%m/%Y}." if lab.observed_at else ""
    return (
        f"Your {lab.test_name} result was {value}{unit}, which is {said}."
        f"{ref}{when} This is your own result from your own report."
    )


def _prescription_sentence(items: list[dict]) -> str:
    lines = []
    for item in items:
        name = item.get("name") or item.get("drug") or "a medicine"
        generic = item.get("ingredient") or item.get("generic")
        dose = item.get("dose") or item.get("strength") or ""
        freq = item.get("frequency") or item.get("schedule") or ""
        label = f"{generic} ({name})" if generic and generic.lower() != str(name).lower() else name
        detail = " ".join(part for part in (dose, freq) if part)
        lines.append(f"{label}{': ' + detail if detail else ''}")
    return "Your doctor has prescribed: " + "; ".join(lines) + "." if lines else ""


def _document_sentences(doc: Document) -> str:
    if not doc.text:
        return ""
    cleaned = re.sub(r"\s+", " ", doc.text).strip()
    return f"This is text read from a report you uploaded: {cleaned[:1200]}"


def _triage_sentence(result: dict) -> str:
    colour = result.get("triage_colour", "")
    specialty = (result.get("specialty") or "").replace("_", " ")
    labs = ", ".join(lab.get("name", "") for lab in result.get("suggested_labs", []) if lab.get("name"))
    parts = [
        "In your pre-visit questionnaire, the clinic recorded your case as "
        f"{colour or 'not yet coloured'} priority and suggested you see "
        f"{specialty or 'a general physician'}."
    ]
    if labs:
        parts.append(f"The tests suggested for you were: {labs}.")
    return " ".join(parts)


# ------------------------------------------------------------------- upserts


async def sync_patient(db: AsyncSession, patient_id: UUID) -> int:
    """Rebuild the patient's own plain-language collection from Postgres.

    Called on every visit transition (see `app.services.visit`) and after any
    document, lab or prescription write. Idempotent: chunk ids are content
    hashes, so re-running upserts in place rather than duplicating.
    """

    chunks: list[Chunk] = []
    collection = patient_collection(patient_id)

    labs = (
        await db.execute(
            select(LabResult)
            .where(LabResult.patient_id == patient_id)
            .order_by(LabResult.observed_at.desc().nullslast())
            .limit(60)
        )
    ).scalars().all()
    for lab in labs:
        chunks.append(
            Chunk(
                id=_chunk_id("lab", str(lab.id)),
                text=_lab_sentence(lab),
                metadata=_metadata(
                    title=f"Your {lab.test_name} result",
                    section="lab_result",
                    doc_type="patient_lab",
                    published=lab.observed_at.isoformat() if lab.observed_at else "",
                ),
            )
        )

    documents = (
        await db.execute(
            select(Document)
            .where(Document.patient_id == patient_id, Document.status == "done")
            .limit(30)
        )
    ).scalars().all()
    for doc in documents:
        text = _document_sentences(doc)
        if text:
            chunks.append(
                Chunk(
                    id=_chunk_id("doc", str(doc.id)),
                    text=text,
                    metadata=_metadata(
                        title="A report you uploaded",
                        section="document",
                        doc_type="patient_document",
                    ),
                )
            )

    prescriptions = (
        await db.execute(
            select(Prescription).where(Prescription.patient_id == patient_id).limit(30)
        )
    ).scalars().all()
    for pres in prescriptions:
        text = _prescription_sentence(list(pres.items or []))
        if text:
            chunks.append(
                Chunk(
                    id=_chunk_id("prescription", str(pres.id)),
                    text=text,
                    metadata=_metadata(
                        title="Your prescription",
                        section="prescription",
                        doc_type="patient_prescription",
                    ),
                )
            )

    visits = (
        await db.execute(select(Visit).where(Visit.patient_id == patient_id).limit(30))
    ).scalars().all()
    for visit in visits:
        if not visit.triage_session_id:
            continue
        session = await db.get(TriageSession, visit.triage_session_id)
        if session is None or not session.result:
            continue
        chunks.append(
            Chunk(
                id=_chunk_id("triage", str(visit.id)),
                text=_triage_sentence(session.result),
                metadata=_metadata(
                    title="Your pre-visit questionnaire",
                    section="triage",
                    doc_type="patient_triage",
                ),
            )
        )

    if chunks:
        VectorStore().upsert(collection, chunks)
    log.info("patient_corpus_synced", patient_id=str(patient_id), chunks=len(chunks))
    return len(chunks)


# --------------------------------------------------------------- lay corpus


def _lay_fallback_chunks() -> list[Chunk]:
    data = yaml.safe_load((_DATA_DIR / "lay_corpus.yaml").read_text(encoding="utf-8"))
    chunks = []
    for entry in data.get("entries", []):
        text = " ".join(entry["text"].split())
        chunks.append(
            Chunk(
                id=_chunk_id("lay", entry["topic"]),
                text=text,
                metadata={
                    "source": "Doctor's Copilot patient guide",
                    "title": entry["title"],
                    "url": settings.medlineplus_base,
                    "section": entry["topic"],
                    "doc_type": "lay",
                    "published": "",
                },
            )
        )
    return chunks


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style|nav|header|footer).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'")
    return re.sub(r"\s+", " ", text).strip()


async def ingest_lay_corpus(*, offline: bool = False) -> int:
    """Populate the shared `lay` collection.

    Tries the MedlinePlus pages listed in `lay_corpus.yaml` first, then always
    upserts the bundled entries so the collection is never empty and never
    depends on the network at demo time.
    """

    store = VectorStore()
    chunks = _lay_fallback_chunks()

    if not offline:
        import httpx

        data = yaml.safe_load((_DATA_DIR / "lay_corpus.yaml").read_text(encoding="utf-8"))
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as http:
                for source in data.get("sources", []):
                    try:
                        response = await http.get(source["url"])
                        response.raise_for_status()
                    except Exception as exc:  # noqa: BLE001
                        log.warning("lay_fetch_failed", url=source["url"], error=str(exc))
                        continue
                    body = _strip_html(response.text)
                    for i in range(0, min(len(body), 6000), 900):
                        piece = body[i : i + 1000]
                        if len(piece) < 200:
                            continue
                        chunks.append(
                            Chunk(
                                id=_chunk_id("medlineplus", source["url"], str(i)),
                                text=piece,
                                metadata={
                                    "source": "MedlinePlus",
                                    "title": source["title"],
                                    "url": source["url"],
                                    "section": f"part-{i // 900 + 1}",
                                    "doc_type": "lay",
                                    "published": "",
                                },
                            )
                        )
        except Exception as exc:  # noqa: BLE001
            log.warning("lay_ingest_offline_fallback", error=str(exc))

    store.upsert(LAY_COLLECTION, chunks)
    total = store.count(LAY_COLLECTION)
    log.info("lay_corpus_ingested", upserted=len(chunks), collection_size=total)
    return total


if __name__ == "__main__":  # pragma: no cover - operator entry point
    import asyncio

    print(asyncio.run(ingest_lay_corpus()))
