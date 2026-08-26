"""RQ job: preprocess -> OCR -> parse_labs -> persist LabResult rows.

Runs in a separate `rq worker` process, so it uses a plain synchronous
SQLAlchemy session (the async engine in app.db.session is bound to the API
process's event loop) over the same `postgresql+psycopg` URL, which the
psycopg3 dialect supports synchronously without changes.
"""

from __future__ import annotations

import json
from uuid import UUID

import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models.clinical import LabResult
from app.db.models.document import Document, FileObject
from app.ml.lab_parser import parse_labs
from app.ml.ocr import run_ocr

logger = structlog.get_logger(__name__)

_engine = None
_session_factory: sessionmaker | None = None


def _get_session_factory() -> sessionmaker:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _session_factory


def _publish_document_done(document_id: UUID, status: str) -> None:
    payload = json.dumps({"document_id": str(document_id), "status": status})
    try:
        from app.core import events as core_events

        publish = getattr(core_events, "publish", None)
        if publish is not None:
            publish("document.done", payload)
            return
    except ImportError:
        pass

    from redis import Redis

    Redis.from_url(get_settings().redis_url).publish("document.done", payload)


def _persist_labs(session: Session, document: Document) -> None:
    file_obj = session.get(FileObject, document.file_id)
    if file_obj is None:
        raise FileNotFoundError(f"file_objects row missing for file_id={document.file_id}")

    ocr_result = run_ocr(file_obj.path)
    labs = parse_labs(ocr_result)

    document.text = "\n\n".join(page["text"] for page in ocr_result["pages"])
    document.engine = ocr_result["engine"]
    document.mean_confidence = ocr_result["mean_confidence"]

    session.query(LabResult).filter(LabResult.document_id == document.id).delete()
    for lab in labs:
        value_num = lab.value if isinstance(lab.value, int | float) else None
        value_text = None if value_num is not None else str(lab.value)
        session.add(
            LabResult(
                document_id=document.id,
                patient_id=document.patient_id,
                test_name=lab.test_name,
                normalized_name=lab.normalized_name,
                value_num=value_num,
                value_text=value_text,
                unit=lab.unit,
                ref_low=lab.ref_low,
                ref_high=lab.ref_high,
                flag=lab.flag,
                confidence=lab.confidence,
            )
        )

    document.status = "done"
    document.error = None


def process_document(document_id: str) -> None:
    """Never raises into the worker loop -- failures are recorded on the row."""
    session_factory = _get_session_factory()
    with session_factory() as session:
        document = session.get(Document, UUID(document_id))
        if document is None:
            logger.warning("workers.ocr_worker.document_missing", document_id=document_id)
            return

        try:
            document.status = "processing"
            session.commit()

            _persist_labs(session, document)
            session.commit()
            _publish_document_done(document.id, "done")
        except Exception as exc:  # noqa: BLE001 -- must never escape the worker loop
            session.rollback()
            document = session.get(Document, UUID(document_id))
            document.status = "failed"
            document.error = f"{type(exc).__name__}: {exc}"[:1000]
            session.commit()
            logger.warning("workers.ocr_worker.failed", document_id=document_id, error=str(exc))
            _publish_document_done(document.id, "failed")
