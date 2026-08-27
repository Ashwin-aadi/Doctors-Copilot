"""Visit read and advance endpoints.

`GET /visits/{id}` returns the whole visit -- triage, documents, brief, safety
report and queue position -- in one response, so the doctor's screen needs a
single call. `POST /visits/{id}/advance` is the only way a visit changes state
from outside; illegal transitions come back as 409 CONFLICT.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user, require_role
from app.core.errors import ApiError
from app.db.session import get_db
from app.schemas.visit import VisitOut, VisitState
from app.services import visit as visit_service

router = APIRouter(prefix="/visits", tags=["visits"])


class AdvanceIn(BaseModel):
    target: VisitState | None = None


async def _assert_may_read(db: AsyncSession, visit_id: UUID, user: CurrentUser) -> None:
    if user.role in ("doctor", "staff", "admin"):
        return

    from app.db.models.clinical import Visit
    from app.rag.patient_chat import resolve_patient_for_user

    record = await db.get(Visit, visit_id)
    patient = await resolve_patient_for_user(db, user.id)
    if record is None or patient is None or record.patient_id != patient.id:
        # Never distinguish "not yours" from "does not exist".
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)


@router.get("/{visit_id}", response_model=VisitOut)
async def get_visit(
    visit_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> VisitOut:
    await _assert_may_read(db, visit_id, user)
    return await visit_service.assemble(db, visit_id)


@router.post("/{visit_id}/advance", response_model=VisitOut)
async def advance_visit(
    visit_id: UUID,
    body: AdvanceIn | None = None,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role("doctor", "staff", "admin")),
) -> VisitOut:
    target = body.target if body else None
    await visit_service.advance(db, visit_id, target, actor_id=user.id)
    return await visit_service.assemble(db, visit_id)
