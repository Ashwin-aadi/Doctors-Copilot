"""Doctor approval + immutable lock (checkpoint P2.3).

Approving a lab order or prescription is one-way: `content_hash` is a
SHA-256 of the canonical (sorted-key, no-whitespace) JSON of `items`, the
record is stamped `locked=True`, and re-approval of an already-locked
record is rejected with `409 LOCKED` before anything else runs. Locking is
enforced twice, per spec: here at the service layer, and again at the
database layer via the `lab_order_lock`/`prescription_lock` triggers added
in `alembic/versions/a3f9c1d84b77_lock_triggers.py` -- so even a write that
bypasses this router (a raw SQL `UPDATE`, or a future route someone else
adds) still fails once `locked` is true.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, require_captcha, require_role
from app.core.errors import ApiError
from app.core.redis_client import redis_client
from app.db.models.audit import AuditLog
from app.db.models.clinical import LabOrder, Prescription, Visit
from app.db.models.patient import Patient
from app.db.models.scheduling import Doctor
from app.db.session import get_db
from app.schemas.visit import VisitState
from app.services import visit as visit_service
from app.services.notify import notify

router = APIRouter(prefix="/approvals", tags=["approvals"])

_require_doctor = require_role("doctor")


def canonical_content_hash(items: Any) -> str:
    canonical = json.dumps(items, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _resolve_doctor_id(db: AsyncSession, user_id: UUID) -> UUID:
    result = await db.execute(select(Doctor.id).where(Doctor.user_id == user_id))
    doctor_id = result.scalar_one_or_none()
    if doctor_id is None:
        raise ApiError(
            "AUTH_FORBIDDEN", "no doctor profile is associated with this account", status_code=403
        )
    return doctor_id


def _audit_entry(
    *, actor_id: UUID, role: str, action: str, entity: str, entity_id: UUID, diff_hash: str | None
) -> AuditLog:
    return AuditLog(
        actor_id=actor_id,
        role=role,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        diff_hash=diff_hash,
        ts=datetime.now(UTC),
    )


async def _reject_if_locked(
    db: AsyncSession, *, user: CurrentUser, entity: str, entity_id: UUID, action: str
) -> None:
    db.add(_audit_entry(actor_id=user.id, role=user.role, action=action, entity=entity, entity_id=entity_id, diff_hash=None))
    await db.commit()
    raise ApiError(
        "LOCKED", f"{entity.replace('_', ' ')} is already approved and locked", status_code=409
    )


async def _notify_patient_approved(
    db: AsyncSession, patient_id: UUID, type_: str, entity_id: UUID
) -> None:
    """Best-effort: an approval must never fail because a notification
    couldn't be sent (P3.2's `notify()` already degrades gracefully on a
    missing email/phone; this just guards against notify() itself raising,
    e.g. a Redis publish failing)."""
    result = await db.execute(select(Patient.user_id).where(Patient.id == patient_id))
    user_id = result.scalar_one_or_none()
    if user_id is None:
        return
    try:
        await notify(user_id, type_, {"entity_id": str(entity_id)}, db)
    except Exception:
        pass


class ApproveLabOrderIn(BaseModel):
    """The doctor may add or drop tests on the approval screen. Sending the
    final list here rather than through a separate PATCH keeps the edit and
    the lock in one transaction -- `content_hash` then always covers exactly
    what was signed for, with no window in which a draft could change between
    the two calls.
    """

    items: list[dict] | None = None


@router.post("/lab-order/{lab_order_id}")
async def approve_lab_order(
    lab_order_id: UUID,
    body: ApproveLabOrderIn | None = None,
    user: CurrentUser = Depends(_require_doctor),
    _captcha: None = Depends(require_captcha),
    db: AsyncSession = Depends(get_db),
) -> dict:
    lab_order = await db.get(LabOrder, lab_order_id)
    if lab_order is None:
        raise ApiError("NOT_FOUND", "lab order not found", status_code=404)

    if lab_order.locked:
        await _reject_if_locked(
            db,
            user=user,
            entity="lab_order",
            entity_id=lab_order_id,
            action="POST /approvals/lab-order/{id} [rejected: already locked]",
        )

    doctor_id = await _resolve_doctor_id(db, user.id)
    visit = await db.get(Visit, lab_order.visit_id)
    if visit is None or visit.doctor_id != doctor_id:
        raise ApiError(
            "AUTH_FORBIDDEN", "not the doctor assigned to this visit", status_code=403
        )

    if body is not None and body.items is not None:
        if not body.items:
            raise ApiError(
                "VALIDATION_FAILED", "a lab order needs at least one test", status_code=422
            )
        lab_order.items = body.items

    content_hash = canonical_content_hash(lab_order.items)
    now = datetime.now(UTC)
    lab_order.approved_by = user.id
    lab_order.approved_at = now
    lab_order.content_hash = content_hash
    lab_order.locked = True
    lab_order.status = "approved"

    db.add(
        _audit_entry(
            actor_id=user.id,
            role=user.role,
            action="POST /approvals/lab-order/{id}",
            entity="lab_order",
            entity_id=lab_order_id,
            diff_hash=content_hash,
        )
    )
    await db.commit()
    await db.refresh(lab_order)

    await redis_client.publish(
        "approval.locked",
        json.dumps({"entity": "lab_order", "id": str(lab_order.id), "content_hash": content_hash}),
    )
    await _notify_patient_approved(db, lab_order.patient_id, "lab_order_approved", lab_order.id)

    # The lock is the LABS_SUGGESTED -> LABS_APPROVED trigger in the visit
    # machine. Advancing here is what puts the visit into the state the
    # patient's portal reads as "your tests are approved, upload the report".
    # A visit sitting in some other state is not an error -- the order was
    # still validly signed -- so a rejected transition is swallowed.
    if visit.state == VisitState.LABS_SUGGESTED.value:
        try:
            await visit_service.advance(
                db, visit.id, VisitState.LABS_APPROVED, actor_id=user.id
            )
        except ApiError:
            pass

    return {
        "id": lab_order.id,
        "status": lab_order.status,
        "locked": lab_order.locked,
        "approved_by": lab_order.approved_by,
        "approved_at": lab_order.approved_at,
        "content_hash": lab_order.content_hash,
    }


@router.post("/prescription/{prescription_id}")
async def approve_prescription(
    prescription_id: UUID,
    user: CurrentUser = Depends(_require_doctor),
    _captcha: None = Depends(require_captcha),
    db: AsyncSession = Depends(get_db),
) -> dict:
    prescription = await db.get(Prescription, prescription_id)
    if prescription is None:
        raise ApiError("NOT_FOUND", "prescription not found", status_code=404)

    if prescription.locked:
        await _reject_if_locked(
            db,
            user=user,
            entity="prescription",
            entity_id=prescription_id,
            action="POST /approvals/prescription/{id} [rejected: already locked]",
        )

    doctor_id = await _resolve_doctor_id(db, user.id)
    visit = await db.get(Visit, prescription.visit_id)
    if visit is None or visit.doctor_id != doctor_id:
        raise ApiError(
            "AUTH_FORBIDDEN", "not the doctor assigned to this visit", status_code=403
        )

    content_hash = canonical_content_hash(prescription.items)
    now = datetime.now(UTC)
    prescription.approved_by = user.id
    prescription.approved_at = now
    prescription.content_hash = content_hash
    prescription.locked = True
    # NOTE: Prescription has no `status` column (unlike LabOrder) -- see
    # docs/DECISIONS.md, additive migration requested from Ashwin for parity.

    db.add(
        _audit_entry(
            actor_id=user.id,
            role=user.role,
            action="POST /approvals/prescription/{id}",
            entity="prescription",
            entity_id=prescription_id,
            diff_hash=content_hash,
        )
    )
    await db.commit()
    await db.refresh(prescription)

    await redis_client.publish(
        "approval.locked",
        json.dumps(
            {"entity": "prescription", "id": str(prescription.id), "content_hash": content_hash}
        ),
    )
    await _notify_patient_approved(
        db, prescription.patient_id, "prescription_ready", prescription.id
    )

    return {
        "id": prescription.id,
        "locked": prescription.locked,
        "approved_by": prescription.approved_by,
        "approved_at": prescription.approved_at,
        "content_hash": prescription.content_hash,
    }
