from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented
from app.schemas.scheduling import QueueEntryOut

router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("/{clinic_id}", response_model=list[QueueEntryOut])
async def get_queue(clinic_id: UUID) -> list[QueueEntryOut]:
    raise not_implemented("queue owned by niyati")


@router.post("/{queue_entry_id}/next")
async def next_in_queue(queue_entry_id: UUID) -> dict:
    raise not_implemented("queue owned by niyati")


@router.post("/{queue_entry_id}/escalate")
async def escalate_queue(queue_entry_id: UUID) -> dict:
    raise not_implemented("queue owned by niyati")
