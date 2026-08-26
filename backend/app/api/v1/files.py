"""Secure file upload/download (checkpoint P2.2).

`POST /files` is multipart, captcha-gated and authenticated. `GET
/files/{id}` returns a signed-URL descriptor (JSON) rather than the bytes
themselves; `GET /files/{id}/raw` streams the actual content given a valid
`sig`. Ownership is enforced identically on both read paths via
`app.services.storage.get_file_object_for_requester`.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user, require_captcha
from app.core.errors import ApiError
from app.core.ratelimit import limiter
from app.db.models.patient import Patient
from app.db.session import get_db
from app.services.storage import (
    get_file_object_for_requester,
    open_file,
    save_file,
    signed_url,
    verify_signed_url,
)

router = APIRouter(prefix="/files", tags=["files"])

_SIGNED_URL_TTL = 300


async def _authorize_upload(db: AsyncSession, user: CurrentUser, patient_id: UUID) -> None:
    """Who may attach a file to `patient_id`: the patient themself, a doctor
    with a Visit/Appointment relationship to that patient, or staff/admin.
    Mirrors `app/api/v1/patients.py`'s `_authorize_patient_access`."""
    if user.role in ("staff", "admin"):
        return
    if user.role == "patient":
        result = await db.execute(select(Patient.id).where(Patient.user_id == user.id))
        owned_id = result.scalar_one_or_none()
        if owned_id is not None and owned_id == patient_id:
            return
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)
    if user.role == "doctor":
        from app.api.v1.patients import _doctor_has_relationship

        if await _doctor_has_relationship(db, user.id, patient_id):
            return
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)
    raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)


@router.post("", dependencies=[Depends(require_captcha)])
@limiter.limit("10/minute")
async def upload_file(
    request: Request,
    patient_id: UUID = Form(...),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _authorize_upload(db, user, patient_id)
    file_obj = await save_file(patient_id, file, user.id, db=db)
    return {
        "id": file_obj.id,
        "patient_id": file_obj.patient_id,
        "mime": file_obj.mime,
        "size": file_obj.size,
        "sha256": file_obj.sha256,
    }


@router.get("/{file_id}")
async def get_file(
    file_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    file_obj = await get_file_object_for_requester(file_id, user, db)
    token = signed_url(file_obj.id, ttl=_SIGNED_URL_TTL, user_id=user.id)
    return {
        "id": file_obj.id,
        "mime": file_obj.mime,
        "size": file_obj.size,
        "url": f"/api/v1/files/{file_obj.id}/raw?sig={token}",
        "expires_in": _SIGNED_URL_TTL,
    }


@router.get("/{file_id}/raw")
async def get_file_raw(
    file_id: UUID,
    sig: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    verify_signed_url(sig, file_id, user.id, ttl=_SIGNED_URL_TTL)
    handle, file_obj = await open_file(file_id, user, db=db)
    return StreamingResponse(handle, media_type=file_obj.mime)
