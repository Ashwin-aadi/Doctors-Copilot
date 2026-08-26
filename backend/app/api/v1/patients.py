"""Patient identity, ownership and DPDP-style consent.

Consent request/response bodies are defined locally (not in
`app/schemas/patient.py`, Ashwin's) since the consent artefact shape
(purpose, data_categories, granular_scopes, ...) isn't in that stub schema.
See docs/DECISIONS.md.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user, require_self_or_role
from app.core.errors import ApiError
from app.db.models.clinical import Visit
from app.db.models.patient import Patient
from app.db.models.scheduling import Appointment, Doctor
from app.db.session import get_db
from app.schemas.patient import PatientIn, PatientOut
from app.services.consent import (
    CONSENT_NOTICES,
    DEFAULT_SCOPES,
    get_latest_consent,
    record_consent,
    withdraw_consent,
)

router = APIRouter(prefix="/patients", tags=["patients"])

_patient_gate = require_self_or_role("patient_id", "doctor", "staff", "admin")


class ConsentRequest(BaseModel):
    version: str = "1.0"
    purpose: list[str] = ["triage", "care_coordination"]
    data_categories: list[str] = ["demographics", "symptoms", "lab_reports", "prescriptions"]
    language: str = "en"
    expiry: datetime | None = None
    granular_scopes: dict[str, bool] = {scope: False for scope in DEFAULT_SCOPES}


class ConsentOut(BaseModel):
    id: UUID
    patient_id: UUID
    version: str
    accepted_at: datetime
    ip: str | None = None
    purpose: list[str]
    data_categories: list[str]
    language: str | None = None
    expiry: datetime | None = None
    granular_scopes: dict[str, bool]
    withdrawn_at: datetime | None = None


async def _doctor_has_relationship(db: AsyncSession, doctor_user_id: UUID, patient_id: UUID) -> bool:
    result = await db.execute(select(Doctor.id).where(Doctor.user_id == doctor_user_id))
    doctor_id = result.scalar_one_or_none()
    if doctor_id is None:
        return False

    visit_result = await db.execute(
        select(Visit.id).where(Visit.doctor_id == doctor_id, Visit.patient_id == patient_id).limit(1)
    )
    if visit_result.scalar_one_or_none() is not None:
        return True

    appt_result = await db.execute(
        select(Appointment.id)
        .where(Appointment.doctor_id == doctor_id, Appointment.patient_id == patient_id)
        .limit(1)
    )
    return appt_result.scalar_one_or_none() is not None


async def _authorize_patient_access(
    db: AsyncSession, user: CurrentUser, patient_id: UUID
) -> None:
    """Fine-grained check beyond the `require_self_or_role` gate: a doctor
    may only reach a patient they have a Visit or Appointment with (staff and
    admin are unrestricted here -- staff-to-clinic scoping needs a
    staff-clinic assignment that doesn't exist on `User` yet; see
    docs/DECISIONS.md). Never distinguishes "not yours" from "doesn't exist".
    """
    if user.role in ("staff", "admin"):
        return
    if user.role == "doctor":
        if await _doctor_has_relationship(db, user.id, patient_id):
            return
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)
    # patient role already passed require_self_or_role only if it's their own record


async def _get_patient_or_403(db: AsyncSession, patient_id: UUID) -> Patient:
    patient = await db.get(Patient, patient_id)
    if patient is None:
        # Never leak existence: a patient probing another id gets the same
        # 403 whether or not that id exists.
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)
    return patient


@router.get("", response_model=list[PatientOut])
async def list_patients(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PatientOut]:
    if user.role not in ("doctor", "staff", "admin"):
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)

    if user.role == "admin" or user.role == "staff":
        result = await db.execute(select(Patient))
        patients = result.scalars().all()
    else:
        doctor_result = await db.execute(select(Doctor.id).where(Doctor.user_id == user.id))
        doctor_id = doctor_result.scalar_one_or_none()
        if doctor_id is None:
            patients = []
        else:
            via_visit = select(Visit.patient_id).where(Visit.doctor_id == doctor_id)
            via_appt = select(Appointment.patient_id).where(Appointment.doctor_id == doctor_id)
            result = await db.execute(select(Patient).where(Patient.id.in_(via_visit.union(via_appt))))
            patients = result.scalars().all()

    return [PatientOut.model_validate(p, from_attributes=True) for p in patients]


@router.post("", response_model=PatientOut)
async def create_patient(
    body: PatientIn,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PatientOut:
    if user.role != "patient":
        raise ApiError(
            "AUTH_FORBIDDEN", "only a patient may create their own patient profile", status_code=403
        )

    existing = await db.execute(select(Patient).where(Patient.user_id == user.id))
    if existing.scalar_one_or_none() is not None:
        raise ApiError("CONFLICT", "a patient profile already exists for this account", status_code=409)

    patient = Patient(user_id=user.id, **body.model_dump())
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return PatientOut.model_validate(patient, from_attributes=True)


@router.get("/{patient_id}", response_model=PatientOut, dependencies=[Depends(_patient_gate)])
async def get_patient(
    patient_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PatientOut:
    await _authorize_patient_access(db, user, patient_id)
    patient = await _get_patient_or_403(db, patient_id)
    return PatientOut.model_validate(patient, from_attributes=True)


@router.patch("/{patient_id}", response_model=PatientOut, dependencies=[Depends(_patient_gate)])
async def update_patient(
    patient_id: UUID,
    body: PatientIn,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PatientOut:
    await _authorize_patient_access(db, user, patient_id)
    patient = await _get_patient_or_403(db, patient_id)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)

    await db.commit()
    await db.refresh(patient)
    return PatientOut.model_validate(patient, from_attributes=True)


@router.get("/{patient_id}/consent/notice")
async def get_consent_notice(patient_id: UUID, version: str = "1.0") -> dict:
    notice = CONSENT_NOTICES.get(version)
    if notice is None:
        raise ApiError("NOT_FOUND", "no consent notice for that version", status_code=404)
    return {"version": version, "text": notice, "scopes": list(DEFAULT_SCOPES)}


@router.post(
    "/{patient_id}/consent", response_model=ConsentOut, dependencies=[Depends(_patient_gate)]
)
async def post_consent(
    patient_id: UUID,
    body: ConsentRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConsentOut:
    await _authorize_patient_access(db, user, patient_id)
    await _get_patient_or_403(db, patient_id)

    consent = await record_consent(
        db,
        patient_id,
        version=body.version,
        purpose=body.purpose,
        data_categories=body.data_categories,
        language=body.language,
        expiry=body.expiry,
        granular_scopes=body.granular_scopes,
        ip=request.client.host if request.client else None,
    )
    return ConsentOut.model_validate(consent)


@router.get(
    "/{patient_id}/consent", response_model=ConsentOut | None, dependencies=[Depends(_patient_gate)]
)
async def get_consent(
    patient_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConsentOut | None:
    await _authorize_patient_access(db, user, patient_id)
    await _get_patient_or_403(db, patient_id)

    consent = await get_latest_consent(db, patient_id)
    return ConsentOut.model_validate(consent) if consent else None


@router.delete(
    "/{patient_id}/consent", response_model=ConsentOut | None, dependencies=[Depends(_patient_gate)]
)
async def delete_consent(
    patient_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConsentOut | None:
    """Records withdrawal. Never a hard delete -- DPDP requires both the
    grant and the withdrawal to remain auditable.
    """
    await _authorize_patient_access(db, user, patient_id)
    await _get_patient_or_403(db, patient_id)

    consent = await withdraw_consent(db, patient_id)
    return ConsentOut.model_validate(consent) if consent else None
