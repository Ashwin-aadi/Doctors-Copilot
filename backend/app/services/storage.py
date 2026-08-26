"""Secure upload pipeline (CLAUDE.md P2.2).

MIME is sniffed from content, never trusted from the client-supplied
extension or `Content-Type` header. Uploads are capped at 20MB, PDFs
carrying active-content tokens are rejected outright, and images are
re-encoded to strip EXIF (GPS tags, camera serials, etc.) before they ever
touch disk. Content is deduped per-patient by SHA-256 so re-uploading the
same document twice returns the existing `FileObject` instead of writing a
second copy.

The frozen §4.2 signatures (`save_file(patient_id, upload, uploaded_by) ->
FileObject`, `open_file(file_id, requester) -> tuple[BinaryIO, FileObject]`,
`signed_url(file_id, ttl=300) -> str`) are extended here with an optional
trailing `db` parameter (opens its own session when omitted) since none of
them can do a dedupe lookup, an ownership check, or a patient-file-object
read without one -- SQLAlchemy's async session simply has no ambient/global
form to reach for instead. `signed_url` additionally takes `user_id` since
P2.2 requires the token be bound to *both* `file_id` and `user_id`, which
the frozen two-arg form can't express. Noted in docs/DECISIONS.md; every
caller in this checkpoint (app/api/v1/files.py) uses the extended form.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

import magic
from fastapi import UploadFile
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import CurrentUser
from app.core.errors import ApiError
from app.db.models.document import FileObject
from app.db.session import SessionLocal

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_SNIFF_BYTES = 2048
_SIGNED_URL_SALT = "pratyaksh.files.signed-url.v1"

# Extension is metadata only (stored on disk purely so a human browsing the
# storage tree can tell what a file is); the MIME sniffed from content is
# what gates acceptance and what's stored in FileObject.mime.
ALLOWED_MIME_EXT: dict[str, str] = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/tiff": "tiff",
}

_MALICIOUS_PDF_TOKENS: tuple[bytes, ...] = (b"/JavaScript", b"/Launch", b"/EmbeddedFile")

_PIL_SAVE_FORMAT: dict[str, str] = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
    "image/tiff": "TIFF",
}


def _signer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.secret_key, salt=_SIGNED_URL_SALT)


def sniff_mime(data: bytes) -> str:
    """Detect the true MIME type from magic bytes, ignoring any client-
    supplied extension or Content-Type -- this is the whole point of the
    control, so nothing upstream of this call may be trusted instead."""
    return magic.from_buffer(data[:_SNIFF_BYTES], mime=True)


def reject_malicious_pdf(data: bytes) -> None:
    """Raise VALIDATION_FAILED if a PDF carries an active-content token.
    A crude byte-substring scan, not a PDF parser -- deliberately so: a
    parser can be confused by malformed structure into missing an object a
    naive scan still catches."""
    for token in _MALICIOUS_PDF_TOKENS:
        if token in data:
            raise ApiError(
                "VALIDATION_FAILED",
                "PDF contains a disallowed active-content token",
                status_code=422,
            )


def strip_exif(data: bytes, mime: str) -> bytes:
    """Re-encode an image without its metadata (EXIF GPS/camera/timestamp
    tags can leak a patient's location). Falls back to the original bytes
    if re-encoding fails for any reason -- the file already passed MIME
    sniffing, so a decode failure here is treated as non-fatal rather than
    blocking the whole upload."""
    save_format = _PIL_SAVE_FORMAT.get(mime)
    if save_format is None:
        return data
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        clean = Image.new(image.mode, image.size)
        clean.putdata(list(image.getdata()))
        buf = io.BytesIO()
        clean.save(buf, format=save_format)
        return buf.getvalue()
    except Exception:
        return data


def validate_upload_bytes(data: bytes) -> str:
    """Run the full accept/reject pipeline on raw bytes (size, MIME
    allowlist, malicious-PDF scan) and return the sniffed MIME. Split out
    from `save_file` so it's unit-testable without a DB session."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError(
            "VALIDATION_FAILED", "file exceeds the 20MB upload limit", status_code=422
        )

    mime = sniff_mime(data)
    if mime not in ALLOWED_MIME_EXT:
        raise ApiError(
            "VALIDATION_FAILED",
            "unsupported file type; only PDF, PNG, JPEG, WEBP and TIFF are accepted",
            status_code=422,
        )

    if mime == "application/pdf":
        reject_malicious_pdf(data)

    return mime


async def save_file(
    patient_id: UUID,
    upload: UploadFile,
    uploaded_by: UUID,
    db: AsyncSession | None = None,
) -> FileObject:
    data = await upload.read()
    mime = validate_upload_bytes(data)
    data = strip_exif(data, mime)
    sha256 = hashlib.sha256(data).hexdigest()

    async def _run(session: AsyncSession) -> FileObject:
        existing = await session.execute(
            select(FileObject).where(
                FileObject.sha256 == sha256, FileObject.patient_id == patient_id
            )
        )
        existing_obj = existing.scalar_one_or_none()
        if existing_obj is not None:
            return existing_obj

        settings = get_settings()
        ext = ALLOWED_MIME_EXT[mime]
        dest_dir = Path(settings.storage_root) / str(patient_id) / sha256[:2]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{sha256}.{ext}"
        if not dest_path.exists():
            dest_path.write_bytes(data)

        file_obj = FileObject(
            patient_id=patient_id,
            sha256=sha256,
            path=str(dest_path),
            mime=mime,
            size=len(data),
            uploaded_by=uploaded_by,
        )
        session.add(file_obj)
        await session.commit()
        await session.refresh(file_obj)
        return file_obj

    if db is not None:
        return await _run(db)
    async with SessionLocal() as session:
        return await _run(session)


async def _requester_can_access(
    db: AsyncSession, requester: CurrentUser, file_obj: FileObject
) -> bool:
    if requester.role in ("staff", "admin"):
        return True
    if requester.role == "patient":
        from app.db.models.patient import Patient

        result = await db.execute(select(Patient.id).where(Patient.user_id == requester.id))
        patient_id = result.scalar_one_or_none()
        return patient_id is not None and patient_id == file_obj.patient_id
    if requester.role == "doctor":
        from app.api.v1.patients import _doctor_has_relationship

        return await _doctor_has_relationship(db, requester.id, file_obj.patient_id)
    return False


async def get_file_object_for_requester(
    file_id: UUID, requester: CurrentUser, db: AsyncSession
) -> FileObject:
    """Ownership-checked lookup, shared by the JSON metadata endpoint and
    `open_file`. Never distinguishes "not yours" from "doesn't exist"."""
    file_obj = await db.get(FileObject, file_id)
    if file_obj is None:
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)
    if not await _requester_can_access(db, requester, file_obj):
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)
    return file_obj


async def open_file(
    file_id: UUID, requester: CurrentUser, db: AsyncSession | None = None
) -> tuple[BinaryIO, FileObject]:
    async def _run(session: AsyncSession) -> tuple[BinaryIO, FileObject]:
        file_obj = await get_file_object_for_requester(file_id, requester, session)
        path = Path(file_obj.path)
        if not path.exists():
            raise ApiError("NOT_FOUND", "file content is missing from storage", status_code=404)
        return open(path, "rb"), file_obj

    if db is not None:
        return await _run(db)
    async with SessionLocal() as session:
        return await _run(session)


def signed_url(file_id: UUID, ttl: int = 300, *, user_id: UUID) -> str:
    """A `file_id`+`user_id`-bound, time-limited token (not a full URL --
    callers build `/files/{file_id}/raw?sig=<token>` around it)."""
    return _signer().dumps({"file_id": str(file_id), "user_id": str(user_id)})


def verify_signed_url(token: str, file_id: UUID, user_id: UUID, ttl: int = 300) -> None:
    try:
        payload = _signer().loads(token, max_age=ttl)
    except SignatureExpired as exc:
        raise ApiError("AUTH_FORBIDDEN", "signed url has expired", status_code=403) from exc
    except BadSignature as exc:
        raise ApiError("AUTH_FORBIDDEN", "invalid signed url", status_code=403) from exc

    if payload.get("file_id") != str(file_id) or payload.get("user_id") != str(user_id):
        raise ApiError("AUTH_FORBIDDEN", "signed url does not match this file/user", status_code=403)
