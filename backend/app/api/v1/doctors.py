from fastapi import APIRouter

from app.core.errors import not_implemented
from app.schemas.scheduling import DoctorRanked

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("", response_model=list[DoctorRanked])
async def list_doctors() -> list[DoctorRanked]:
    raise not_implemented("doctor ranking owned by niyati")
