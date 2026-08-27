"""Patient chatbot endpoint: Server-Sent Events over `POST /api/v1/chat/patient`.

A patient may only ever read their own records. The `patient_id` a caller sends
is honoured only for a doctor or staff member; for a patient it is ignored in
favour of the profile attached to their own user, and a mismatch is a 403 rather
than a silent substitution -- a patient probing another patient's id gets told no.
"""

from uuid import UUID

import orjson
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user
from app.core.errors import ApiError
from app.db.session import get_db
from app.rag import patient_chat
from app.rag.patient_chat import resolve_patient_for_user

router = APIRouter(prefix="/chat", tags=["chat"])


class PatientChatIn(BaseModel):
    message: str
    patient_id: UUID | None = None
    history: list[dict] = []


async def _authorized_patient(db: AsyncSession, user: CurrentUser, requested: UUID | None):
    if user.role in ("doctor", "staff", "admin"):
        if requested is None:
            raise ApiError("VALIDATION_FAILED", "patient_id is required for staff callers", 422)
        from app.db.models.patient import Patient

        patient = await db.get(Patient, requested)
        if patient is None:
            raise ApiError("NOT_FOUND", "patient not found", status_code=404)
        return patient

    patient = await resolve_patient_for_user(db, user.id)
    if patient is None:
        raise ApiError("AUTH_FORBIDDEN", "no patient profile for this account", status_code=403)
    if requested is not None and requested != patient.id:
        raise ApiError("AUTH_FORBIDDEN", "you may only read your own records", status_code=403)
    return patient


@router.post("/patient")
async def patient_chat_route(
    body: PatientChatIn,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    patient = await _authorized_patient(db, user, body.patient_id)

    async def _events():
        async for event in patient_chat.chat_stream(db, patient, body.message, body.history):
            payload = orjson.dumps(event["data"]).decode()
            yield f"event: {event['event']}\ndata: {payload}\n\n"

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
