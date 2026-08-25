from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.rag import triage_rag
from app.schemas.triage import TriageMessageIn, TriageResult, TriageTurnOut

router = APIRouter(prefix="/triage", tags=["triage"])


@router.post("/session", response_model=TriageTurnOut)
async def start_session(
    patient_id: UUID | None = None, db: AsyncSession = Depends(get_db)
) -> TriageTurnOut:
    return await triage_rag.start(db, patient_id)


@router.post("/{session_id}/message", response_model=TriageTurnOut)
async def send_message(
    session_id: UUID, body: TriageMessageIn, db: AsyncSession = Depends(get_db)
) -> TriageTurnOut:
    return await triage_rag.turn(db, session_id, body.content)


@router.get("/{session_id}/result", response_model=TriageResult)
async def get_result(session_id: UUID, db: AsyncSession = Depends(get_db)) -> TriageResult:
    return await triage_rag.get_result(db, session_id)
