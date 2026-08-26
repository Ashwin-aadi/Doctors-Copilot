from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.deps import require_role, require_self_or_role
from app.kg import queries

router = APIRouter(prefix="/kg", tags=["kg"])


@router.get("/patient/{patient_id}/timeline")
async def patient_timeline(
    patient_id: UUID,
    _user=Depends(require_self_or_role("patient_id", "doctor", "staff", "admin")),
) -> list[dict]:
    return await queries.patient_timeline(patient_id)


@router.get("/patient/{patient_id}/context")
async def patient_context(
    patient_id: UUID,
    _user=Depends(require_role("doctor", "staff", "admin")),
) -> dict:
    return await queries.patient_context(patient_id)
