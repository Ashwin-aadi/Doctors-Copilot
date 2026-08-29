import hashlib
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import CurrentUser, get_current_user
from app.core.errors import ApiError
from app.core.logging import get_logger
from app.db.models.clinical import LabResult
from app.db.models.document import Document, FileObject
from app.db.models.patient import Patient
from app.db.session import get_db
from app.schemas.document import DocumentOut, LabResultOut
from app.workers.queue import enqueue_process_document

router = APIRouter(prefix="/documents", tags=["documents"])

log = get_logger(__name__)


class DocumentUploadIn(BaseModel):
    file_id: UUID
    patient_id: UUID
    # Which line of the lab order this report answers, when the patient
    # uploaded it from the order itself rather than as a loose file.
    test_name: str | None = None


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DocumentOut:
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        # TEMP-ADAPTER: remove when pratyaksh ships services/storage.py + /files.
        # Accepts a raw file upload directly and stores it under
        # STORAGE_ROOT/tmp/, since the real /files endpoint isn't merged yet.
        form = await request.form()
        upload = form.get("file")
        raw_patient_id = form.get("patient_id")
        raw_test_name = form.get("test_name")
        if upload is None or raw_patient_id is None:
            raise ApiError("VALIDATION_FAILED", "file and patient_id are required", 422)

        patient_id = UUID(str(raw_patient_id))
        test_name = str(raw_test_name) if raw_test_name else None
        data = await upload.read()

        settings = get_settings()
        dest_dir = Path(settings.storage_root) / "tmp"
        dest_dir.mkdir(parents=True, exist_ok=True)
        file_id = uuid4()
        suffix = Path(upload.filename or "").suffix
        dest_path = dest_dir / f"{file_id}{suffix}"
        dest_path.write_bytes(data)

        file_obj = FileObject(
            id=file_id,
            patient_id=patient_id,
            sha256=hashlib.sha256(data).hexdigest(),
            path=str(dest_path),
            mime=upload.content_type or "application/octet-stream",
            size=len(data),
            uploaded_by=current_user.id,
        )
        db.add(file_obj)
        await db.flush()
    else:
        body = DocumentUploadIn.model_validate(await request.json())
        patient_id = body.patient_id
        file_id = body.file_id
        test_name = body.test_name
        file_obj = await db.get(FileObject, file_id)
        if file_obj is None:
            raise ApiError("NOT_FOUND", "file not found", status_code=404)

    document = Document(
        patient_id=patient_id, file_id=file_id, status="queued", test_name=test_name
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    enqueue_process_document(document.id)

    return DocumentOut(
        id=document.id,
        patient_id=document.patient_id,
        file_id=document.file_id,
        status=document.status,
        test_name=document.test_name,
    )


async def _authorize_document_access(
    db: AsyncSession, user: CurrentUser, patient_id: UUID
) -> None:
    """Who may act on a patient's document: the patient themself, a doctor with
    a visit/appointment relationship to them, or staff/admin. Mirrors the
    upload gate in `app/api/v1/files.py` -- a wrong photo is the patient's to
    withdraw, so this is deliberately not doctor-only.
    """
    if user.role in ("staff", "admin"):
        return
    if user.role == "patient":
        owned = (
            await db.execute(select(Patient.id).where(Patient.user_id == user.id))
        ).scalar_one_or_none()
        if owned is not None and owned == patient_id:
            return
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)
    if user.role == "doctor":
        from app.api.v1.patients import _doctor_has_relationship

        if await _doctor_has_relationship(db, user.id, patient_id):
            return
    raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    """Withdraw an uploaded report: the wrong file, the wrong patient's report,
    a scan too poor to read. Removes the extracted lab values with it -- values
    read out of a document the patient has retracted must not keep informing
    the brief -- and the stored file when nothing else references it.
    """
    document = await db.get(Document, document_id)
    if document is None:
        raise ApiError("NOT_FOUND", "document not found", status_code=404)
    await _authorize_document_access(db, current_user, document.patient_id)

    patient_id = document.patient_id
    file_id = document.file_id
    await db.execute(delete(LabResult).where(LabResult.document_id == document.id))
    await db.delete(document)
    await db.flush()

    # The same bytes can back more than one document (uploads dedupe on
    # sha256), so the file only goes when the last reference to it does.
    others = (
        await db.execute(select(Document.id).where(Document.file_id == file_id).limit(1))
    ).scalar_one_or_none()
    if others is None:
        file_obj = await db.get(FileObject, file_id)
        if file_obj is not None:
            path = Path(file_obj.path)
            await db.delete(file_obj)
            if path.exists():
                path.unlink(missing_ok=True)

    await db.commit()

    # The graph is a projection of Postgres, so it has to be rebuilt once the
    # rows are gone -- otherwise the withdrawn report's values keep reaching
    # the copilot brief through `patient_context`.
    try:
        from app.kg.ingest import sync_patient

        await sync_patient(patient_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("kg_resync_after_delete_failed", patient_id=str(patient_id), error=str(exc))

    return Response(status_code=204)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DocumentOut:
    document = await db.get(Document, document_id)
    if document is None:
        raise ApiError("NOT_FOUND", "document not found", status_code=404)

    labs: list[LabResultOut] = []
    if document.status == "done":
        result = await db.execute(select(LabResult).where(LabResult.document_id == document.id))
        labs = [
            LabResultOut(
                test_name=row.test_name,
                normalized_name=row.normalized_name,
                value=row.value_num if row.value_num is not None else (row.value_text or ""),
                unit=row.unit,
                ref_low=row.ref_low,
                ref_high=row.ref_high,
                flag=row.flag,
                confidence=row.confidence,
            )
            for row in result.scalars().all()
        ]

    return DocumentOut(
        id=document.id,
        patient_id=document.patient_id,
        file_id=document.file_id,
        status=document.status,
        engine=document.engine,
        mean_confidence=document.mean_confidence,
        text=document.text,
        labs=labs,
        error=document.error,
        test_name=document.test_name,
    )
