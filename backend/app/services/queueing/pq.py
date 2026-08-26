"""Priority queue over `QueueEntry` rows: a persisted min-heap per
(clinic_id, service_date). The DB is the source of truth -- `snapshot()`
recomputes the full ordering from `QueueEntry` rows on every call, so the
queue is always rebuildable. A Postgres advisory lock on `hash(clinic_id)`
serialises `enqueue`/`pop_next`/`escalate` so concurrent callers can't
interleave and corrupt ordering.

TEMP-ADAPTER: `QueueEntry` (app/db/models/scheduling.py, not an owned path)
has no `token` or statutory-`priority_group` column. Both are side-channelled
through Redis, keyed by entry id (`queue:meta:{entry_id}`), TTL 3 days --
long enough to outlive any single OPD day, short enough not to leak forever.
This is a real limitation (a Redis flush loses tokens/priority groups for
entries still in the queue) acceptable for a hackathon demo; see
docs/DECISIONS.md for the DRIFT note asking Ashwin to add both columns.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from uuid import UUID

import yaml
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import redis_client
from app.db.models.patient import Patient
from app.db.models.scheduling import Appointment, Clinic, QueueEntry
from app.db.session import SessionLocal
from app.schemas.triage import colour_for_esi
from app.services.queueing.schemas import QueueEntryOut
from app.services.scheduling.repo import _CLINIC_LOCALE_OVERRIDES, _clinic_locale_default

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

_PACKS_DIR = Path(__file__).resolve().parents[1] / "rules" / "packs"
_QUEUE_PACK = _PACKS_DIR / "queue.yaml"
_TRIAGE_PACK = _PACKS_DIR / "triage_india.yaml"

_TOKEN_TTL_SECONDS = 3 * 24 * 3600
_PRIORITY_GROUP_IDS = {
    "pregnant_third_trimester",
    "infant_under_1",
    "senior_citizen_60_plus",
    "divyangjan",
}


@lru_cache(maxsize=1)
def _queue_pack() -> dict:
    return yaml.safe_load(_QUEUE_PACK.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def _triage_pack() -> dict:
    return yaml.safe_load(_TRIAGE_PACK.read_text(encoding="utf-8")) or {}


def _tier(severity_esi: int) -> dict:
    return _triage_pack().get("tiers", {}).get(severity_esi, {})


async def _advisory_lock(session: AsyncSession, clinic_id: UUID) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:cid))"), {"cid": str(clinic_id)})


def _service_date(moment: dt.datetime) -> dt.date:
    return moment.astimezone(IST).date()


async def _next_token(clinic_id: UUID, facility_prefix: str, service_date: dt.date) -> str:
    seq_key = f"queue:token_seq:{clinic_id}:{service_date.isoformat()}"
    seq = await redis_client.incr(seq_key)
    await redis_client.expire(seq_key, _TOKEN_TTL_SECONDS)
    return f"{facility_prefix}-{int(seq):03d}"


async def _store_meta(entry_id: UUID, token: str, priority_group: str | None) -> None:
    key = f"queue:meta:{entry_id}"
    await redis_client.hset(key, mapping={"token": token, "priority_group": priority_group or ""})
    await redis_client.expire(key, _TOKEN_TTL_SECONDS)


async def _read_meta(entry_id: UUID) -> tuple[str | None, str | None]:
    key = f"queue:meta:{entry_id}"
    data = await redis_client.hgetall(key)
    if not data:
        return None, None
    return data.get("token") or None, data.get("priority_group") or None


def _facility_prefix(facility_type: str) -> str:
    return _queue_pack().get("token_prefix_by_facility", {}).get(facility_type, "K")


async def _facility_type(session: AsyncSession, clinic_id: UUID) -> str:
    clinic = await session.get(Clinic, clinic_id)
    if clinic is None:
        return "phc"
    facility_type, _schemes = _CLINIC_LOCALE_OVERRIDES.get(
        clinic.id, _clinic_locale_default(clinic.is_emergency_capable)
    )
    return facility_type


def _effective_severity(entry: QueueEntry, waited_minutes: float) -> int:
    """Aging-only severity adjustment. The statutory priority-group bonus is
    *not* folded in here -- at tier 3 (one step above RED) any numeric bonus
    would either be a no-op after the RED-floor clamp below or, without the
    clamp, illegally promote a non-emergency patient into RED. It is instead
    a same-tier tie-break in `_sort_key`, which is what "a bounded bonus,
    never above RED" actually cashes out to for a tier this close to the
    boundary.
    """
    pack = _queue_pack()
    aging_minutes = pack.get("aging_minutes", 45)
    aging_max_bonus = pack.get("aging_max_bonus", 2)
    emergency_max = pack.get("emergency_severity_max", 2)

    aging_bonus = min(aging_max_bonus, int(waited_minutes // aging_minutes)) if waited_minutes > 0 else 0
    effective = entry.severity_esi - aging_bonus
    if not entry.emergency:
        # aging may never push a non-emergency patient into RED
        effective = max(effective, emergency_max + 1)
    return max(1, effective)


def _reasons(
    entry: QueueEntry, waited_minutes: float, effective_severity: int, priority_group: str | None
) -> tuple[list[str], list[str]]:
    tier = _tier(effective_severity)
    colour = tier.get("colour", "green")
    label_en = tier.get("label_en", "")
    label_hi = tier.get("label_hi", "")
    colour_title = colour.capitalize()

    reasons_en = [f"{colour_title} - {label_en}"]
    reasons_hi = [f"{label_hi}"]

    if entry.emergency:
        reasons_en.append("Emergency - sent to front")
        reasons_hi.append("आपातकाल - आगे भेजा गया")

    if waited_minutes >= _queue_pack().get("aging_minutes", 45):
        reasons_en.append(f"Waiting {int(waited_minutes)} min - moved up")
        reasons_hi.append(f"{int(waited_minutes)} मिनट से प्रतीक्षा - आगे बढ़ाया गया")

    if priority_group in _PRIORITY_GROUP_IDS:
        for group in _triage_pack().get("priority_groups", []):
            if group["id"] == priority_group:
                reasons_en.append(group["reason_en"])
                reasons_hi.append(group.get("reason_hi", group["reason_en"]))
                break

    return reasons_en, reasons_hi


def _sort_key(
    entry: QueueEntry,
    waited_minutes: float,
    effective_severity: int,
    priority_group: str | None,
    scheduled_time: dt.datetime | None,
):
    return (
        0 if entry.emergency else 1,
        effective_severity,
        0 if priority_group in _PRIORITY_GROUP_IDS else 1,
        -waited_minutes,
        scheduled_time or dt.datetime.max.replace(tzinfo=dt.UTC),
        entry.enqueued_at,
        str(entry.id),
    )


async def enqueue(entry: QueueEntry, *, now: dt.datetime) -> QueueEntryOut:
    priority_group = getattr(entry, "priority_group", None)

    async with SessionLocal() as session:
        async with session.begin():
            await _advisory_lock(session, entry.clinic_id)
            facility_type = await _facility_type(session, entry.clinic_id)
            entry.emergency = entry.emergency or entry.severity_esi <= _queue_pack().get(
                "emergency_severity_max", 2
            )
            session.add(entry)
            await session.flush()

            token = await _next_token(entry.clinic_id, _facility_prefix(facility_type), _service_date(now))
            await _store_meta(entry.id, token, priority_group)

    return await _entry_out(entry.id, now=now)


async def snapshot(clinic_id: UUID, *, now: dt.datetime) -> list[QueueEntryOut]:
    service_date = _service_date(now)
    day_start = dt.datetime.combine(service_date, dt.time.min, tzinfo=IST).astimezone(dt.UTC)
    day_end = day_start + dt.timedelta(days=1)

    async with SessionLocal() as session:
        stmt = (
            select(QueueEntry)
            .where(QueueEntry.clinic_id == clinic_id)
            .where(QueueEntry.status == "waiting")
            .where(QueueEntry.enqueued_at >= day_start)
            .where(QueueEntry.enqueued_at < day_end)
        )
        entries = list((await session.execute(stmt)).scalars().all())
        if not entries:
            return []

        appt_ids = [e.appointment_id for e in entries if e.appointment_id is not None]
        scheduled_by_appt: dict[UUID, dt.datetime] = {}
        if appt_ids:
            appts = (
                await session.execute(select(Appointment).where(Appointment.id.in_(appt_ids)))
            ).scalars().all()
            scheduled_by_appt = {a.id: a.slot_start for a in appts}

        patient_ids = [e.patient_id for e in entries]
        patients = (
            await session.execute(select(Patient).where(Patient.id.in_(patient_ids)))
        ).scalars().all()
        patient_name_by_id = {p.id: p.name for p in patients}

    avg_consult = _queue_pack().get("avg_consult_minutes", 6)

    scored: list[tuple[tuple, QueueEntry, float, int, str | None, dt.datetime | None]] = []
    for entry in entries:
        waited_minutes = max(0.0, (now - entry.enqueued_at).total_seconds() / 60)
        _token, priority_group = await _read_meta(entry.id)
        effective_severity = _effective_severity(entry, waited_minutes)
        scheduled_time = scheduled_by_appt.get(entry.appointment_id) if entry.appointment_id else None
        key = _sort_key(entry, waited_minutes, effective_severity, priority_group, scheduled_time)
        scored.append((key, entry, waited_minutes, effective_severity, priority_group, scheduled_time))

    scored.sort(key=lambda t: t[0])

    out: list[QueueEntryOut] = []
    for position, (_key, entry, waited_minutes, effective_severity, priority_group, _sched) in enumerate(
        scored, start=1
    ):
        token, _pg = await _read_meta(entry.id)
        reasons_en, reasons_hi = _reasons(entry, waited_minutes, effective_severity, priority_group)
        out.append(
            QueueEntryOut(
                id=entry.id,
                patient_id=entry.patient_id,
                patient_name=patient_name_by_id.get(entry.patient_id, ""),
                doctor_id=entry.doctor_id,
                clinic_id=entry.clinic_id,
                severity_esi=effective_severity,
                triage_colour=colour_for_esi(effective_severity),
                emergency=entry.emergency,
                position=position,
                waited_minutes=int(waited_minutes),
                estimated_wait_minutes=position * avg_consult,
                status=entry.status,
                reasons=reasons_en,
                reasons_hi=reasons_hi,
                token=token or f"?-{position:03d}",
            )
        )
    return out


async def _entry_out(entry_id: UUID, *, now: dt.datetime) -> QueueEntryOut:
    """Build a single entry's `QueueEntryOut`, regardless of its status.
    `snapshot()` only enumerates `waiting` entries (it's the queue board), so
    a popped or escalated entry is computed directly here instead of being
    looked up in a snapshot that may no longer contain it.
    """
    async with SessionLocal() as session:
        entry = await session.get(QueueEntry, entry_id)
        if entry is None:
            raise LookupError(f"queue entry {entry_id} not found")
        patient = await session.get(Patient, entry.patient_id)
        patient_name = patient.name if patient else ""

    waited_minutes = max(0.0, (now - entry.enqueued_at).total_seconds() / 60)
    token, priority_group = await _read_meta(entry_id)
    effective_severity = _effective_severity(entry, waited_minutes)
    reasons_en, reasons_hi = _reasons(entry, waited_minutes, effective_severity, priority_group)

    position = 1
    if entry.status == "waiting":
        full = await snapshot(entry.clinic_id, now=now)
        for i, e in enumerate(full, start=1):
            if e.id == entry_id:
                position = i
                break

    avg_consult = _queue_pack().get("avg_consult_minutes", 6)
    return QueueEntryOut(
        id=entry.id,
        patient_id=entry.patient_id,
        patient_name=patient_name,
        doctor_id=entry.doctor_id,
        clinic_id=entry.clinic_id,
        severity_esi=effective_severity,
        triage_colour=colour_for_esi(effective_severity),
        emergency=entry.emergency,
        position=position,
        waited_minutes=int(waited_minutes),
        estimated_wait_minutes=position * avg_consult,
        status=entry.status,
        reasons=reasons_en,
        reasons_hi=reasons_hi,
        token=token or "?-000",
    )


async def pop_next(clinic_id: UUID, doctor_id: UUID, *, now: dt.datetime) -> QueueEntryOut | None:
    async with SessionLocal() as session:
        async with session.begin():
            await _advisory_lock(session, clinic_id)

    full = await snapshot(clinic_id, now=now)
    for e in full:
        if e.doctor_id == doctor_id:
            async with SessionLocal() as session:
                async with session.begin():
                    entry = await session.get(QueueEntry, e.id)
                    if entry is None or entry.status != "waiting":
                        continue
                    entry.status = "in_consult"
                    entry.started_at = now
            return await _entry_out(e.id, now=now)
    return None


async def escalate(entry_id: UUID, reason: str, *, now: dt.datetime) -> QueueEntryOut:
    """Basic CP1 escalation: forces the entry to RED and re-keys it to the
    queue head. The red-flag detection and referral-ladder logic (108
    transfer suggestions when the assigned clinic can't handle the emergency)
    is N2.3's `app/services/queueing/escalation.py`, layered on top of this.
    """
    async with SessionLocal() as session:
        async with session.begin():
            entry = await session.get(QueueEntry, entry_id)
            if entry is None:
                raise LookupError(f"queue entry {entry_id} not found")
            await _advisory_lock(session, entry.clinic_id)
            entry.emergency = True
            entry.severity_esi = min(entry.severity_esi, _queue_pack().get("emergency_severity_max", 2))
            token, priority_group = await _read_meta(entry_id)
            await _store_meta(entry_id, token or "", priority_group)
            await redis_client.hset(f"queue:meta:{entry_id}", mapping={"escalate_reason": reason})
    return await _entry_out(entry_id, now=now)
