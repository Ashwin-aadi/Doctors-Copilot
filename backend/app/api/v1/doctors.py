from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, get_current_user
from app.services.scheduling.optimizer import rank_doctors
from app.services.scheduling.schemas import DoctorRankedOut

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("", response_model=list[DoctorRankedOut])
async def list_doctors(
    specialty: str,
    lat: float | None = None,
    lng: float | None = None,
    date: datetime | None = None,
    max_fee: float | None = None,
    language: str | None = None,
    scheme: str | None = None,
    user: CurrentUser = Depends(get_current_user),
) -> list[DoctorRankedOut]:
    now = datetime.now(UTC)
    date_from = date or now
    if date_from.tzinfo is None:
        date_from = date_from.replace(tzinfo=UTC)
    return await rank_doctors(
        specialty=specialty,
        lat=lat,
        lng=lng,
        date_from=date_from,
        max_fee=max_fee,
        language=language,
        scheme=scheme,
        now=now,
    )
