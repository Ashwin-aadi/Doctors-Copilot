import hashlib
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import CurrentUser, get_current_user
from app.core.errors import ApiError
from app.db.models.clinical import LabResult
from app.db.models.document import Document, FileObject
from app.db.session import get_db
from app.schemas.document import DocumentOut, LabResultOut
from app.workers.queue import enqueue_process_document

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentUploadIn(BaseModel):
    file_id: UUID
    patient_id: UUID


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
        if upload is None or raw_patient_id is None:
            raise ApiError("VALIDATION_FAILED", "file and patient_id are required", 422)

        patient_id = UUID(str(raw_patient_id))
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
        file_obj = await db.get(FileObject, file_id)
        if file_obj is None:
            raise ApiError("NOT_FOUND", "file not found", status_code=404)

    document = Document(patient_id=patient_id, file_id=file_id, status="queued")
    db.add(document)
    await db.commit()
    await db.refresh(document)

    enqueue_process_document(document.id)

    return DocumentOut(
        id=document.id,
        patient_id=document.patient_id,
        file_id=document.file_id,
        status=document.status,
    )


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
    )
