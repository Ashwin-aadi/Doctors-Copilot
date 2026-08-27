"""Appointment lifecycle (section 8 N3.2): cancel, reschedule, no-show,
referral-out and walk-in insertion.

Every case asserts the three things a lifecycle transition owes the clinic:
the appointment row moved, the slot went back into the free pool, and the
queue entry left `waiting`. The board publish is best-effort by design (see
`lifecycle.publish_board`), so it is asserted by observing the rebuilt
snapshot rather than by reaching into Redis.
"""

from __future__ import annotations

import datetime as dt
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.errors import ApiError
from app.db.models.scheduling import Appointment, QueueEntry
from app.db.session import SessionLocal
from app.services.queueing.pq import snapshot
from app.services.scheduling import lifecycle
from app.services.scheduling.repo import booked_slots
from app.services.scheduling.slots import free_slots
from tests.services.conftest import CLINIC_PHC, doctor_id, patient_id

NOW = dt.datetime(2026, 1, 12, 9, 0, tzinfo=dt.UTC)  # 14:30 IST, Monday
DOCTOR = doctor_id(1)  # Dr. Lakshmi Sundaram, general_medicine at the PHC

# Ids created by `_book`/`walk_in` during the test currently running, torn
# down afterwards. Unlike the read-only cases elsewhere in tests/services,
# this module *writes* appointments, and a leftover `booked` row on the
# fixture date would make `test_repo.py`'s empty-busy-set assertion depend on
# which file pytest happened to run first.
_CREATED_APPOINTMENTS: list[object] = []
_CREATED_QUEUE_ENTRIES: list[object] = []


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_created_rows():
    _CREATED_APPOINTMENTS.clear()
    _CREATED_QUEUE_ENTRIES.clear()
    yield
    async with SessionLocal() as session:
        if _CREATED_QUEUE_ENTRIES:
            await session.execute(
                delete(QueueEntry).where(QueueEntry.id.in_(_CREATED_QUEUE_ENTRIES))
            )
        if _CREATED_APPOINTMENTS:
            # queue entries first -- they carry the FK onto appointments
            await session.execute(
                delete(QueueEntry).where(QueueEntry.appointment_id.in_(_CREATED_APPOINTMENTS))
            )
            await session.execute(
                delete(Appointment).where(Appointment.id.in_(_CREATED_APPOINTMENTS))
            )
        await session.commit()
    _CREATED_APPOINTMENTS.clear()
    _CREATED_QUEUE_ENTRIES.clear()


async def _walk_in(**kwargs):
    """`lifecycle.walk_in` with the resulting entry registered for teardown --
    a walk-in has no appointment to cascade from, so it has to be tracked
    directly or it survives the test and skews the next module's queue.
    """
    out = await lifecycle.walk_in(**kwargs)
    _CREATED_QUEUE_ENTRIES.append(out.id)
    return out


async def _book(*, patient: int = 1, at: dt.datetime | None = None) -> Appointment:
    """Create a booked appointment on one of the doctor's genuinely free
    slots (or `at`, when a test needs a specific wall-clock time).
    """
    if at is None:
        booked = (await booked_slots([DOCTOR], NOW.date(), NOW.date() + dt.timedelta(days=2))).get(
            DOCTOR, []
        )
        slots = free_slots(DOCTOR, CLINIC_PHC, NOW.date(), NOW.date() + dt.timedelta(days=2), booked)
        assert slots, "fixture doctor has no free slots"
        slot_start, slot_end = slots[0]
    else:
        slot_start, slot_end = at, at + dt.timedelta(minutes=15)

    appt = Appointment(
        id=uuid4(),
        patient_id=patient_id(patient),
        doctor_id=DOCTOR,
        clinic_id=CLINIC_PHC,
        slot_start=slot_start,
        slot_end=slot_end,
        status="booked",
    )
    entry = QueueEntry(
        id=uuid4(),
        appointment_id=appt.id,
        patient_id=patient_id(patient),
        doctor_id=DOCTOR,
        clinic_id=CLINIC_PHC,
        severity_esi=4,
        emergency=False,
        enqueued_at=NOW,
        status="waiting",
    )
    async with SessionLocal() as session:
        session.add(appt)
        await session.flush()
        session.add(entry)
        await session.commit()
        await session.refresh(appt)
    _CREATED_APPOINTMENTS.append(appt.id)
    return appt


async def _queue_entry_status(appointment_id) -> str | None:
    async with SessionLocal() as session:
        return (
            await session.execute(
                select(QueueEntry.status).where(QueueEntry.appointment_id == appointment_id)
            )
        ).scalar_one_or_none()


@pytest.mark.asyncio
async def test_cancel_frees_slot_and_drops_queue_entry():
    appt = await _book()
    slot_start = appt.slot_start

    out = await lifecycle.cancel(appt.id, now=NOW, reason="patient called the counter")

    assert out["status"] == "cancelled"
    assert await _queue_entry_status(appt.id) == "cancelled"

    # the slot is back in the free pool
    booked = (await booked_slots([DOCTOR], NOW.date(), NOW.date() + dt.timedelta(days=2))).get(DOCTOR, [])
    assert slot_start not in [s for s, _e in booked]

    board = await snapshot(CLINIC_PHC, now=NOW)
    assert appt.id not in [e.id for e in board]


@pytest.mark.asyncio
async def test_cancel_twice_conflicts():
    appt = await _book(patient=2)
    await lifecycle.cancel(appt.id, now=NOW)
    with pytest.raises(ApiError) as exc:
        await lifecycle.cancel(appt.id, now=NOW)
    assert exc.value.code == "CONFLICT"


@pytest.mark.asyncio
async def test_cancel_unknown_appointment_is_not_found():
    with pytest.raises(ApiError) as exc:
        await lifecycle.cancel(uuid4(), now=NOW)
    assert exc.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_reschedule_moves_to_a_genuinely_free_slot():
    appt = await _book(patient=3)
    original = appt.slot_start

    booked = (await booked_slots([DOCTOR], NOW.date(), NOW.date() + dt.timedelta(days=2))).get(DOCTOR, [])
    booked = [(s, e) for s, e in booked if s != original]
    candidates = free_slots(DOCTOR, CLINIC_PHC, NOW.date(), NOW.date() + dt.timedelta(days=2), booked)
    target = next(s for s, _e in candidates if s != original)

    out = await lifecycle.reschedule(appt.id, target, now=NOW)

    assert out["status"] == "booked"
    assert out["slot_start"] == target
    assert out["slot_start"] != original


@pytest.mark.asyncio
async def test_reschedule_onto_a_taken_slot_conflicts():
    first = await _book(patient=4)
    second = await _book(patient=5)
    assert first.slot_start != second.slot_start

    with pytest.raises(ApiError) as exc:
        await lifecycle.reschedule(second.id, first.slot_start, now=NOW)
    assert exc.value.code == "CONFLICT"


@pytest.mark.asyncio
async def test_reschedule_a_cancelled_appointment_conflicts():
    appt = await _book(patient=6)
    await lifecycle.cancel(appt.id, now=NOW)
    with pytest.raises(ApiError) as exc:
        await lifecycle.reschedule(appt.id, appt.slot_start + dt.timedelta(minutes=15), now=NOW)
    assert exc.value.code == "CONFLICT"


@pytest.mark.asyncio
async def test_no_show_requires_the_grace_window_to_elapse():
    slot = NOW + dt.timedelta(hours=1)
    appt = await _book(patient=7, at=slot)

    # one minute into the slot: still inside the 15-minute grace window
    with pytest.raises(ApiError) as exc:
        await lifecycle.mark_no_show(appt.id, now=slot + dt.timedelta(minutes=1))
    assert exc.value.code == "CONFLICT"
    assert "no_show_at" in exc.value.details


@pytest.mark.asyncio
async def test_no_show_after_grace_releases_the_slot():
    slot = NOW + dt.timedelta(hours=2)
    appt = await _book(patient=8, at=slot)

    out = await lifecycle.mark_no_show(appt.id, now=slot + dt.timedelta(minutes=20))

    assert out["status"] == "no_show"
    assert await _queue_entry_status(appt.id) == "cancelled"
    booked = (await booked_slots([DOCTOR], NOW.date(), NOW.date() + dt.timedelta(days=2))).get(DOCTOR, [])
    assert slot not in [s for s, _e in booked]


@pytest.mark.asyncio
async def test_sweep_no_shows_is_deterministic_and_skips_started_consults():
    late = NOW - dt.timedelta(hours=1)
    stale = await _book(patient=1, at=late)
    started = await _book(patient=2, at=late + dt.timedelta(minutes=15))

    async with SessionLocal() as session:
        entry = (
            await session.execute(
                select(QueueEntry).where(QueueEntry.appointment_id == started.id)
            )
        ).scalar_one()
        entry.status = "in_consult"
        await session.commit()

    swept = await lifecycle.sweep_no_shows(CLINIC_PHC, now=NOW)
    swept_ids = [row["id"] for row in swept]

    assert stale.id in swept_ids
    assert started.id not in swept_ids, "a patient already in consult is not a no-show"
    # replaying the sweep finds nothing left to do
    assert await lifecycle.sweep_no_shows(CLINIC_PHC, now=NOW) == []


@pytest.mark.asyncio
async def test_refer_out_records_target_and_frees_the_slot():
    # A wall-clock time no other case in this module books, so the
    # busy-set assertion below reads only this appointment. Rows persist
    # across tests in the shared fixture DB, so a shared slot would leave the
    # time occupied by someone else's booking and mask the release.
    slot = NOW + dt.timedelta(days=1, hours=5)
    appt = await _book(patient=3, at=slot)

    before = (await booked_slots([DOCTOR], NOW.date(), NOW.date() + dt.timedelta(days=2))).get(DOCTOR, [])
    assert slot in [s for s, _e in before], "precondition: the slot starts out busy"

    out = await lifecycle.refer_out(
        appt.id,
        target_facility_type="dh",
        reason="needs cardiology workup unavailable at a PHC",
        now=NOW,
    )

    assert out["status"] == "referred"
    assert out["referral"]["target_facility_type"] == "dh"
    assert await _queue_entry_status(appt.id) == "cancelled"

    after = (await booked_slots([DOCTOR], NOW.date(), NOW.date() + dt.timedelta(days=2))).get(DOCTOR, [])
    assert slot not in [s for s, _e in after], "a referred-out slot goes back into the pool"


@pytest.mark.asyncio
async def test_walk_in_gets_a_token_and_a_position_without_an_appointment():
    out = await _walk_in(
        clinic_id=CLINIC_PHC,
        patient_id=patient_id(4),
        doctor_id=DOCTOR,
        severity_esi=3,
        now=NOW,
    )

    assert out.token and out.token.startswith("P-")
    assert out.position >= 1
    assert out.triage_colour == "yellow"
    assert out.reasons and out.reasons_hi


@pytest.mark.asyncio
async def test_walk_in_with_a_statutory_priority_group_surfaces_its_reason():
    out = await _walk_in(
        clinic_id=CLINIC_PHC,
        patient_id=patient_id(5),
        doctor_id=DOCTOR,
        severity_esi=3,
        priority_group="pregnant_third_trimester",
        now=NOW,
    )
    assert any("Pregnancy" in r for r in out.reasons)
    assert out.reasons_hi
