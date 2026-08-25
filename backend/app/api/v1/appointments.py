from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("")
async def list_appointments() -> list:
    raise not_implemented("appointments owned by niyati")


@router.post("")
async def create_appointment() -> dict:
    raise not_implemented("appointments owned by niyati")


@router.patch("/{appointment_id}")
async def update_appointment(appointment_id: UUID) -> dict:
    raise not_implemented("appointments owned by niyati")


@router.post("/simulate")
async def simulate_appointment() -> dict:
    raise not_implemented("appointment simulation owned by niyati")
