"""PDF export endpoint (checkpoint P3.3). Ownership-checked the same way as
`app/services/storage.py`'s file access: patients only their own records,
doctors only patients they have a Visit/Appointment with, staff/admin
unrestricted."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user
from app.core.errors import ApiError
from app.db.models.clinical import LabOrder, Prescription
from app.db.models.patient import Patient
from app.db.session import get_db
from app.services.pdf import Kind, render

router = APIRouter(prefix="/exports", tags=["exports"])

_VALID_KINDS = {"summary", "prescription", "lab_order"}


async def _authorize_export(
    db: AsyncSession, user: CurrentUser, export_type: str, entity_id: UUID
) -> UUID:
    """Resolves the patient_id the export belongs to and enforces
    ownership. Never distinguishes "not yours" from "doesn't exist"."""
    if export_type == "summary":
        patient_id = entity_id
    elif export_type == "prescription":
        record = await db.get(Prescription, entity_id)
        if record is None:
            raise ApiError("NOT_FOUND", "prescription not found", status_code=404)
        patient_id = record.patient_id
    elif export_type == "lab_order":
        record = await db.get(LabOrder, entity_id)
        if record is None:
            raise ApiError("NOT_FOUND", "lab order not found", status_code=404)
        patient_id = record.patient_id
    else:
        raise ApiError("VALIDATION_FAILED", "unsupported export type", status_code=422)

    if user.role in ("staff", "admin"):
        return patient_id
    if user.role == "patient":
        from sqlalchemy import select

        result = await db.execute(select(Patient.id).where(Patient.user_id == user.id))
        own_patient_id = result.scalar_one_or_none()
        if own_patient_id is not None and own_patient_id == patient_id:
            return patient_id
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)
    if user.role == "doctor":
        from app.api.v1.patients import _doctor_has_relationship

        if await _doctor_has_relationship(db, user.id, patient_id):
            return patient_id
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)
    raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)


@router.get("/{export_type}/{entity_id}.pdf")
async def export_pdf(
    export_type: str,
    entity_id: UUID,
    lang: str = "en",
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if export_type not in _VALID_KINDS:
        raise ApiError("VALIDATION_FAILED", "unsupported export type", status_code=422)

    await _authorize_export(db, user, export_type, entity_id)
    locale = lang if lang in ("en", "hi") else "en"
    pdf_bytes = await render(cast(Kind, export_type), entity_id, locale=locale, db=db)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{export_type}-{entity_id}.pdf"'},
    )
