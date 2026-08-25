from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented
from app.schemas.triage import TriageMessageIn, TriageResult, TriageTurnOut

router = APIRouter(prefix="/triage", tags=["triage"])


@router.post("/session", response_model=TriageTurnOut)
async def start_session() -> TriageTurnOut:
    raise not_implemented("triage session start lands in A1.4")


@router.post("/{session_id}/message", response_model=TriageTurnOut)
async def send_message(session_id: UUID, body: TriageMessageIn) -> TriageTurnOut:
    raise not_implemented("triage turn handling lands in A1.4")


@router.get("/{session_id}/result", response_model=TriageResult)
async def get_result(session_id: UUID) -> TriageResult:
    raise not_implemented("triage finalize lands in A1.4")
