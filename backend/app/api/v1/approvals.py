from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("/lab-order/{lab_order_id}")
async def approve_lab_order(lab_order_id: UUID) -> dict:
    raise not_implemented("lab order approval owned by pratyaksh")


@router.post("/prescription/{prescription_id}")
async def approve_prescription(prescription_id: UUID) -> dict:
    raise not_implemented("prescription approval owned by pratyaksh")
