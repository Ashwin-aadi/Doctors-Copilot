from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(prefix="/kg", tags=["kg"])


@router.get("/patient/{patient_id}/timeline")
async def patient_timeline(patient_id: UUID) -> list:
    raise not_implemented("knowledge graph timeline lands in A2.2")


@router.get("/patient/{patient_id}/context")
async def patient_context(patient_id: UUID) -> dict:
    raise not_implemented("knowledge graph context lands in A2.2")
