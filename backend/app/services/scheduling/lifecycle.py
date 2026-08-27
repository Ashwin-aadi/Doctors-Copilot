"""Appointment lifecycle: cancel, reschedule, no-show, walk-in insertion and
referral-out (section 8 N3.2).

Every mutation here does three things: move the `Appointment` row, re-key the
affected `QueueEntry`, and publish the rebuilt board on Redis so the OPD
display updates without polling. The board payload carries `token`,
`position`, `triage_colour` and the Hindi reason lines, because that display
is what patients in the waiting hall actually read.

Rule-based and deterministic throughout -- `now` is always injected, never
read off the wall clock, so the same inputs replay to the same board.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from uuid import UUID, uuid4

import yaml
from sqlalchemy import select

from app.core.errors import ApiError
from app.core.events import QUEUE_CHANNEL, publish
from app.core.logging import get_logger
from app.db.models.patient import Patient
from app.db.models.scheduling import Appointment, Doctor, QueueEntry
from app.db.session import SessionLocal
from app.services.queueing.pq import enqueue, snapshot
from app.services.queueing.schemas import QueueEntryOut
from app.services.scheduling.repo import RELEASING_STATUSES
from app.services.scheduling.repo import booked_slots as repo_booked_slots
from app.services.scheduling.slots import free_slots

log = get_logger(__name__)

_PACKS_DIR = Path(__file__).resolve().parents[1] / "rules" / "packs"
_QUEUE_PACK = _PACKS_DIR / "queue.yaml"

# `booked` is the only live appointment status. `RELEASING_STATUSES` is
# defined in `repo` (which `booked_slots` filters on) and re-exported here so
# the two views of "this slot is free again" can never drift apart.
LIVE_STATUSES = ("booked",)

# The `QueueEntry.status` column is constrained by Ashwin's frozen
# `QueueEntryOut.status` literal (waiting|in_consult|done|cancelled), so a
# no-show or referral-out closes the queue entry as `cancelled` and records
# the finer-grained reason on the *appointment*, which is unconstrained.
_QUEUE_CLOSED = "cancelled"


@lru_cache(maxsize=1)
def _queue_pack() -> dict:
    return yaml.safe_load(_QUEUE_PACK.read_text(encoding="utf-8")) or {}


def _grace_minutes() -> int:
    return int(_queue_pack().get("grace_minutes", 15))


def _appointment_dict(a: Appointment) -> dict:
    return {
        "id": a.id,
        "patient_id": a.patient_id,
        "doctor_id": a.doctor_id,
        "clinic_id": a.clinic_id,
        "slot_start": a.slot_start,
        "slot_end": a.slot_end,
        "status": a.status,
    }


async def publish_board(clinic_id: UUID, *, now: dt.datetime) -> list[QueueEntryOut]:
    """Rebuild the clinic board and push it on `queue.updated:{clinic_id}`.

    Best-effort by construction -- `app.core.events.publish` logs and swallows
    a Redis failure, so a cancellation never fails because the display is
    briefly unreachable.
    """
    board = await snapshot(clinic_id, now=now)
    await publish(
        QUEUE_CHANNEL,
        {
            "clinic_id": str(clinic_id),
            "at": now.isoformat(),
            "entries": [
                {
                    "id": str(e.id),
                    "token": e.token,
                    "position": e.position,
                    "triage_colour": e.triage_colour,
                    "severity_esi": e.severity_esi,
                    "emergency": e.emergency,
                    "estimated_wait_minutes": e.estimated_wait_minutes,
                    "reasons": e.reasons,
                    "reasons_hi": e.reasons_hi,
                }
                for e in board
            ],
        },
    )
    return board


async def _notify(user_id: UUID | None, type_: str, payload: dict) -> None:
    """Best-effort SMS-first notification. Kept guarded even though
    `app/services/notify.py` has shipped: a DLT/SMTP outage must never roll
    back a cancellation the clerk has already told the patient about.
    """
    if user_id is None:
        return
    try:
        from app.services.notify import notify as _notify_fn

        await _notify_fn(user_id, type_, payload)
    except Exception as exc:  # noqa: BLE001 -- delivery is never load-bearing
        log.warning("notify_failed", type_=type_, error=str(exc))


async def _patient_user_id(session, patient_id: UUID) -> UUID | None:
    return (
        await session.execute(select(Patient.user_id).where(Patient.id == patient_id))
    ).scalar_one_or_none()


async def _doctor_user_id(session, doctor_id: UUID) -> UUID | None:
    return (
        await session.execute(select(Doctor.user_id).where(Doctor.id == doctor_id))
    ).scalar_one_or_none()


async def _close_queue_entries(session, appointment_id: UUID) -> int:
    """Close every still-open queue entry attached to this appointment.
    Returns how many were closed, so callers can tell a cancel-before-arrival
    from a cancel-after-check-in.
    """
    entries = (
        (
            await session.execute(
                select(QueueEntry)
                .where(QueueEntry.appointment_id == appointment_id)
                .where(QueueEntry.status.in_(["waiting", "in_consult"]))
            )
        )
        .scalars()
        .all()
    )
    for entry in entries:
        entry.status = _QUEUE_CLOSED
    return len(entries)


async def _load(session, appointment_id: UUID) -> Appointment:
    appt = await session.get(Appointment, appointment_id)
    if appt is None:
        raise ApiError("NOT_FOUND", "appointment not found", status_code=404)
    return appt


async def cancel(appointment_id: UUID, *, now: dt.datetime, reason: str | None = None) -> dict:
    """Free the slot, drop the queue entry, tell the patient by SMS."""
    async with SessionLocal() as session:
        async with session.begin():
            appt = await _load(session, appointment_id)
            if appt.status in RELEASING_STATUSES:
                raise ApiError(
                    "CONFLICT",
                    f"appointment is already {appt.status}",
                    status_code=409,
                    details={"status": appt.status},
                )
            appt.status = "cancelled"
            await _close_queue_entries(session, appointment_id)
            patient_user_id = await _patient_user_id(session, appt.patient_id)
            clinic_id, slot_start = appt.clinic_id, appt.slot_start
            out = _appointment_dict(appt)

    await _notify(
        patient_user_id,
        "appointment_cancelled",
        {
            "appointment_id": str(appointment_id),
            "slot_start": slot_start.isoformat(),
            "reason": reason,
        },
    )
    await publish_board(clinic_id, now=now)
    return out


async def reschedule(appointment_id: UUID, new_slot_start: dt.datetime, *, now: dt.datetime) -> dict:
    """Atomic release + rebook onto `new_slot_start` for the same doctor.

    The target must be a slot the doctor genuinely has free -- validated
    against `free_slots` with this appointment's own slot excluded from
    `booked`, so moving an appointment one slot later and back again is a
    no-op rather than a self-conflict.
    """
    if new_slot_start.tzinfo is None:
        new_slot_start = new_slot_start.replace(tzinfo=dt.UTC)

    async with SessionLocal() as session:
        appt = await _load(session, appointment_id)
        if appt.status in RELEASING_STATUSES:
            raise ApiError(
                "CONFLICT", f"cannot reschedule a {appt.status} appointment", status_code=409
            )
        doctor_id, clinic_id = appt.doctor_id, appt.clinic_id
        old_start = appt.slot_start
        patient_id = appt.patient_id

    horizon_start = min(new_slot_start, now).date()
    horizon_end = new_slot_start.date() + dt.timedelta(days=1)
    booked = (await repo_booked_slots([doctor_id], horizon_start, horizon_end)).get(doctor_id, [])
    booked = [(s, e) for s, e in booked if s != old_start]

    candidates = free_slots(doctor_id, clinic_id, horizon_start, horizon_end, booked)
    target = next((s for s in candidates if s[0] == new_slot_start), None)
    if target is None:
        raise ApiError(
            "CONFLICT",
            "requested slot is not available for this doctor",
            status_code=409,
            details={"next_available": candidates[0][0].isoformat() if candidates else None},
        )

    async with SessionLocal() as session:
        async with session.begin():
            appt = await _load(session, appointment_id)
            appt.slot_start, appt.slot_end = target
            appt.status = "booked"
            patient_user_id = await _patient_user_id(session, patient_id)
            out = _appointment_dict(appt)

    await _notify(
        patient_user_id,
        "appointment_rescheduled",
        {
            "appointment_id": str(appointment_id),
            "from": old_start.isoformat(),
            "to": target[0].isoformat(),
        },
    )
    await publish_board(clinic_id, now=now)
    return out


async def mark_no_show(appointment_id: UUID, *, now: dt.datetime) -> dict:
    """Flip a still-waiting appointment past its grace window to `no_show`,
    release the slot and send the patient a rebook link.
    """
    grace = dt.timedelta(minutes=_grace_minutes())

    async with SessionLocal() as session:
        async with session.begin():
            appt = await _load(session, appointment_id)
            if appt.status != "booked":
                raise ApiError(
                    "CONFLICT", f"appointment is {appt.status}, not booked", status_code=409
                )
            if now < appt.slot_start + grace:
                raise ApiError(
                    "CONFLICT",
                    "grace period has not elapsed",
                    status_code=409,
                    details={"no_show_at": (appt.slot_start + grace).isoformat()},
                )
            appt.status = "no_show"
            await _close_queue_entries(session, appointment_id)
            patient_user_id = await _patient_user_id(session, appt.patient_id)
            clinic_id = appt.clinic_id
            out = _appointment_dict(appt)

    await _notify(
        patient_user_id,
        "appointment_no_show",
        {
            "appointment_id": str(appointment_id),
            "rebook_path": f"/appointments?rebook={appointment_id}",
        },
    )
    await publish_board(clinic_id, now=now)
    return out


async def sweep_no_shows(clinic_id: UUID, *, now: dt.datetime) -> list[dict]:
    """Every booked appointment at this clinic whose grace window expired
    while its queue entry never left `waiting`. Deterministic: ordered by
    slot then id, so a replay produces the same list in the same order.
    """
    grace = dt.timedelta(minutes=_grace_minutes())
    cutoff = now - grace

    async with SessionLocal() as session:
        appts = (
            (
                await session.execute(
                    select(Appointment)
                    .where(Appointment.clinic_id == clinic_id)
                    .where(Appointment.status == "booked")
                    .where(Appointment.slot_start <= cutoff)
                    .order_by(Appointment.slot_start, Appointment.id)
                )
            )
            .scalars()
            .all()
        )
        stale_ids = [a.id for a in appts]
        if not stale_ids:
            return []
        started = {
            row[0]
            for row in (
                await session.execute(
                    select(QueueEntry.appointment_id)
                    .where(QueueEntry.appointment_id.in_(stale_ids))
                    .where(QueueEntry.status.in_(["in_consult", "done"]))
                )
            ).all()
        }

    out: list[dict] = []
    for appointment_id in stale_ids:
        if appointment_id in started:
            continue
        out.append(await mark_no_show(appointment_id, now=now))
    return out


async def refer_out(
    appointment_id: UUID,
    *,
    target_facility_type: str,
    reason: str,
    now: dt.datetime,
    target_clinic_id: UUID | None = None,
) -> dict:
    """Send the patient up the PHC -> CHC -> SDH -> DH -> medical college
    ladder. Records the target facility type and reason, frees the slot, and
    notifies both the origin doctor and the patient. Never books at the
    target -- the receiving facility registers the patient itself, usually
    after a 108 transfer.
    """
    async with SessionLocal() as session:
        async with session.begin():
            appt = await _load(session, appointment_id)
            if appt.status in RELEASING_STATUSES:
                raise ApiError(
                    "CONFLICT", f"appointment is already {appt.status}", status_code=409
                )
            appt.status = "referred"
            await _close_queue_entries(session, appointment_id)
            patient_user_id = await _patient_user_id(session, appt.patient_id)
            doctor_user_id = await _doctor_user_id(session, appt.doctor_id)
            clinic_id = appt.clinic_id
            out = _appointment_dict(appt)

    payload = {
        "appointment_id": str(appointment_id),
        "target_facility_type": target_facility_type,
        "target_clinic_id": str(target_clinic_id) if target_clinic_id else None,
        "reason": reason,
    }
    await _notify(patient_user_id, "referral_out", payload)
    await _notify(doctor_user_id, "referral_out", payload)
    await publish_board(clinic_id, now=now)

    out["referral"] = payload
    return out


async def walk_in(
    *,
    clinic_id: UUID,
    patient_id: UUID,
    doctor_id: UUID,
    severity_esi: int,
    now: dt.datetime,
    priority_group: str | None = None,
) -> QueueEntryOut:
    """Register a patient with no appointment. The dominant path in an Indian
    government OPD, so it goes straight through the same `pq.enqueue` the
    booked path uses -- same priority key, same token counter, same board.
    """
    entry = QueueEntry(
        id=uuid4(),
        appointment_id=None,
        patient_id=patient_id,
        doctor_id=doctor_id,
        clinic_id=clinic_id,
        severity_esi=severity_esi,
        emergency=False,
        enqueued_at=now,
        status="waiting",
    )
    if priority_group:
        # read by pq.enqueue, side-channelled to Redis alongside the token
        entry.priority_group = priority_group
    out = await enqueue(entry, now=now)
    await publish_board(clinic_id, now=now)
    return out
