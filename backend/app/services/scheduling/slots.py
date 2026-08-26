"""Slot generation: expand weekly Availability templates into concrete slots.

`free_slots` is frozen as a synchronous, no-`db`-argument function (CP1
interface freeze), so unlike the rest of this package it opens its own
short-lived *sync* SQLAlchemy session rather than an async one -- the
`postgresql+psycopg` driver supports both over the same DSN. Its only
dynamic inputs are the caller-supplied `booked` list and whatever is
currently committed to `availabilities`/`clinics`; it never reads the wall
clock. See docs/DECISIONS.md for the reasoning.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.scheduling import Availability, Clinic
from app.services.scheduling.repo import _CLINIC_LOCALE_OVERRIDES, _clinic_locale_default

IST = ZoneInfo("Asia/Kolkata")

_PACKS_DIR = Path(__file__).resolve().parents[1] / "rules" / "packs"
_QUEUE_PACK = _PACKS_DIR / "queue.yaml"

_sync_engine = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return _sync_engine


@lru_cache(maxsize=1)
def _queue_pack() -> dict:
    if not _QUEUE_PACK.exists():
        return {}
    return yaml.safe_load(_QUEUE_PACK.read_text(encoding="utf-8")) or {}


def _holidays() -> set[dt.date]:
    return {dt.date.fromisoformat(s) for s in _queue_pack().get("holidays", [])}


def _travel_minutes() -> int:
    return int(_queue_pack().get("inter_clinic_travel_minutes", 30))


def _availability_templates(doctor_id: UUID) -> list[Availability]:
    stmt = (
        select(Availability)
        .where(Availability.doctor_id == doctor_id)
        .order_by(Availability.clinic_id, Availability.weekday, Availability.start_time)
    )
    with Session(_get_sync_engine()) as session:
        return list(session.execute(stmt).scalars().all())


def _clinic_facility_lookup(clinic_ids: list[UUID]) -> dict[UUID, tuple[str, bool]]:
    if not clinic_ids:
        return {}
    stmt = select(Clinic).where(Clinic.id.in_(clinic_ids))
    with Session(_get_sync_engine()) as session:
        rows = session.execute(stmt).scalars().all()
    out: dict[UUID, tuple[str, bool]] = {}
    for c in rows:
        facility_type, _schemes = _CLINIC_LOCALE_OVERRIDES.get(
            c.id, _clinic_locale_default(c.is_emergency_capable)
        )
        out[c.id] = (facility_type, c.is_emergency_capable)
    return out


def _is_closed(d: dt.date, facility_type: str, is_emergency_capable: bool, holidays: set[dt.date]) -> bool:
    if is_emergency_capable:
        return False
    if d.weekday() == 6 and facility_type in ("phc", "chc"):
        return True
    return d in holidays


def _generate_day_slots(
    templates_for_day: list[Availability], d: dt.date
) -> list[tuple[dt.datetime, dt.datetime]]:
    slots: list[tuple[dt.datetime, dt.datetime]] = []
    for a in templates_for_day:
        cursor = dt.datetime.combine(d, a.start_time, tzinfo=IST)
        session_end = dt.datetime.combine(d, a.end_time, tzinfo=IST)
        step = dt.timedelta(minutes=a.slot_minutes)
        while cursor + step <= session_end:
            slots.append((cursor, cursor + step))
            cursor += step
    return slots


def _overlaps(a_start: dt.datetime, a_end: dt.datetime, b_start: dt.datetime, b_end: dt.datetime) -> bool:
    return a_start < b_end and a_end > b_start


def free_slots(
    doctor_id: UUID,
    clinic_id: UUID,
    date_from: dt.date,
    date_to: dt.date,
    booked: list[tuple[dt.datetime, dt.datetime]],
) -> list[tuple[dt.datetime, dt.datetime]]:
    templates = _availability_templates(doctor_id)
    own_templates = [a for a in templates if a.clinic_id == clinic_id]
    other_templates = [a for a in templates if a.clinic_id != clinic_id]

    other_clinic_ids = {a.clinic_id for a in other_templates}
    facility_lookup = _clinic_facility_lookup([clinic_id, *other_clinic_ids])
    facility_type, is_emergency_capable = facility_lookup.get(clinic_id, ("phc", False))
    holidays = _holidays()
    travel_gap = dt.timedelta(minutes=_travel_minutes())

    result: list[tuple[dt.datetime, dt.datetime]] = []
    d = date_from
    while d <= date_to:
        weekday = d.weekday()
        own_today = [a for a in own_templates if a.weekday == weekday and a.valid_from <= d <= a.valid_to]
        if own_today and not _is_closed(d, facility_type, is_emergency_capable, holidays):
            other_today = [
                a for a in other_templates if a.weekday == weekday and a.valid_from <= d <= a.valid_to
            ]
            busy = [
                (s - travel_gap, e + travel_gap) for s, e in _generate_day_slots(other_today, d)
            ]
            for s_ist, e_ist in _generate_day_slots(own_today, d):
                if any(_overlaps(s_ist, e_ist, bs, be) for bs, be in busy):
                    continue
                s_utc, e_utc = s_ist.astimezone(dt.timezone.utc), e_ist.astimezone(dt.timezone.utc)
                if any(_overlaps(s_utc, e_utc, bs, be) for bs, be in booked):
                    continue
                result.append((s_utc, e_utc))
        d += dt.timedelta(days=1)

    result.sort()
    return result
