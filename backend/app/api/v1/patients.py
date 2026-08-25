from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented
from app.schemas.patient import PatientIn, PatientOut

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=list[PatientOut])
async def list_patients() -> list[PatientOut]:
    raise not_implemented("patients list owned by pratyaksh")


@router.post("", response_model=PatientOut)
async def create_patient(body: PatientIn) -> PatientOut:
    raise not_implemented("patients create owned by pratyaksh")


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(patient_id: UUID) -> PatientOut:
    raise not_implemented("patients get owned by pratyaksh")


@router.patch("/{patient_id}", response_model=PatientOut)
async def update_patient(patient_id: UUID, body: PatientIn) -> PatientOut:
    raise not_implemented("patients update owned by pratyaksh")


@router.get("/{patient_id}/consent")
async def get_consent(patient_id: UUID) -> dict:
    raise not_implemented("patient consent owned by pratyaksh")
