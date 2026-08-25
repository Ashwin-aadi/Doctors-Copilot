from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(prefix="/doctors-profile", tags=["doctors-profile"])


@router.get("")
async def list_doctor_profiles() -> list:
    raise not_implemented("doctor profile admin owned by pratyaksh")


@router.post("")
async def create_doctor_profile() -> dict:
    raise not_implemented("doctor profile admin owned by pratyaksh")


@router.patch("/{doctor_id}")
async def update_doctor_profile(doctor_id: UUID) -> dict:
    raise not_implemented("doctor profile admin owned by pratyaksh")
