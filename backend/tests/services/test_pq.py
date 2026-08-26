"""Priority-queue tests. Needs a reachable Postgres + Redis (`make up`) --
this module's own `_clean_queue` fixture wipes `queue_entries` before every
test since, unlike `test_repo.py`/`test_optimizer.py`, these tests write
rows that would otherwise leak across tests sharing the same fixed `NOW`
and pollute each other's same-day snapshots.
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.db.models.scheduling import QueueEntry
from app.db.session import SessionLocal
from app.services.queueing.pq import enqueue, escalate, pop_next, snapshot
from tests.services.conftest import CLINIC_PHC, doctor_id, patient_id

NOW = dt.datetime(2026, 1, 12, 10, tzinfo=dt.timezone.utc)  # 15:30 IST, Monday


@pytest_asyncio.fixture(autouse=True)
async def _clean_queue() -> None:
    async with SessionLocal() as session:
        await session.execute(delete(QueueEntry))
        await session.commit()


def _entry(
    *,
    patient_i: int,
    doctor_i: int,
    severity: int,
    enqueued_at: dt.datetime,
    emergency: bool = False,
    priority_group: str | None = None,
    clinic_id: UUID = CLINIC_PHC,
) -> QueueEntry:
    e = QueueEntry(
        id=uuid4(),
        appointment_id=None,
        patient_id=patient_id(patient_i),
        doctor_id=doctor_id(doctor_i),
        clinic_id=clinic_id,
        severity_esi=severity,
        emergency=emergency,
        enqueued_at=enqueued_at,
        status="waiting",
    )
    if priority_group is not None:
        e.priority_group = priority_group
    return e


@pytest.mark.asyncio
async def test_enqueue_and_snapshot_have_positions_tokens_and_reasons():
    now = NOW
    await enqueue(_entry(patient_i=1, doctor_i=1, severity=4, enqueued_at=now), now=now)
    await enqueue(_entry(patient_i=2, doctor_i=1, severity=1, enqueued_at=now, emergency=True), now=now)

    q = await snapshot(CLINIC_PHC, now=now)
    assert q == sorted(q, key=lambda e: e.position)
    assert [e.position for e in q] == list(range(1, len(q) + 1))
    assert all(e.reasons and e.token for e in q)


@pytest.mark.asyncio
async def test_emergency_entry_is_at_the_head():
    now = NOW
    await enqueue(_entry(patient_i=3, doctor_i=1, severity=4, enqueued_at=now), now=now)
    emergency_out = await enqueue(
        _entry(patient_i=4, doctor_i=1, severity=1, enqueued_at=now, emergency=True), now=now
    )

    q = await snapshot(CLINIC_PHC, now=now)
    n_emergency = sum(1 for e in q if e.emergency)
    assert all(e.emergency for e in q[:n_emergency])
    assert q[0].id == emergency_out.id


@pytest.mark.asyncio
async def test_starvation_aging_green_beats_fresh_yellow():
    now = NOW
    old_enqueued = now - dt.timedelta(minutes=100)
    green_old = await enqueue(_entry(patient_i=5, doctor_i=2, severity=4, enqueued_at=old_enqueued), now=now)
    yellow_fresh = await enqueue(_entry(patient_i=6, doctor_i=2, severity=3, enqueued_at=now), now=now)

    q = await snapshot(CLINIC_PHC, now=now)
    ids = [e.id for e in q]
    assert ids.index(green_old.id) < ids.index(yellow_fresh.id)


@pytest.mark.asyncio
async def test_statutory_priority_outranks_plain_same_tier_but_never_beats_red():
    now = NOW
    plain = await enqueue(_entry(patient_i=7, doctor_i=3, severity=3, enqueued_at=now), now=now)
    pregnant = await enqueue(
        _entry(patient_i=8, doctor_i=3, severity=3, enqueued_at=now, priority_group="pregnant_third_trimester"),
        now=now,
    )
    red = await enqueue(_entry(patient_i=1, doctor_i=3, severity=1, enqueued_at=now, emergency=True), now=now)

    q = await snapshot(CLINIC_PHC, now=now)
    ids = [e.id for e in q]
    assert ids.index(red.id) < ids.index(pregnant.id) < ids.index(plain.id)


@pytest.mark.asyncio
async def test_pop_next_marks_in_consult_and_removes_from_waiting_snapshot():
    now = NOW
    entry = await enqueue(_entry(patient_i=2, doctor_i=4, severity=3, enqueued_at=now), now=now)

    popped = await pop_next(CLINIC_PHC, doctor_id(4), now=now)
    assert popped is not None
    assert popped.id == entry.id
    assert popped.status == "in_consult"

    q = await snapshot(CLINIC_PHC, now=now)
    assert entry.id not in [e.id for e in q]


@pytest.mark.asyncio
async def test_pop_next_returns_none_when_doctor_has_no_waiting_patients():
    now = NOW
    assert await pop_next(CLINIC_PHC, doctor_id(6), now=now) is None


@pytest.mark.asyncio
async def test_escalate_forces_red_and_moves_to_head():
    now = NOW
    plain = await enqueue(_entry(patient_i=3, doctor_i=5, severity=4, enqueued_at=now), now=now)

    escalated = await escalate(plain.id, "snakebite with bleeding gums", now=now)
    assert escalated.emergency is True
    assert escalated.triage_colour == "red"

    q = await snapshot(CLINIC_PHC, now=now)
    assert q[0].id == escalated.id
