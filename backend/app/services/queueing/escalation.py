"""Emergency red-flag detection and referral-ladder escalation, layered over
`app.services.queueing.pq.escalate` (the CP1 re-key-to-head primitive).

Rule-based only -- red-flag phrases and facility floors both come from
`packs/emergency.yaml`, matched by plain substring search. No LLM anywhere in
this path (autonomy contract rule 6).
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from uuid import UUID

import yaml
from geopy.distance import geodesic

from app.core.logging import get_logger
from app.db.models.scheduling import Clinic, QueueEntry
from app.db.session import SessionLocal
from app.services.queueing import pq
from app.services.queueing.schemas import QueueEntryOut
from app.services.scheduling.repo import (
    _CLINIC_LOCALE_OVERRIDES,
    ClinicRow,
    _clinic_locale_default,
    all_clinics,
)

log = get_logger(__name__)

_PACKS_DIR = Path(__file__).resolve().parents[1] / "rules" / "packs"
_EMERGENCY_PACK = _PACKS_DIR / "emergency.yaml"
_OPTIMIZER_PACK = _PACKS_DIR / "optimizer.yaml"

_AMBULANCE_LINE_EN = "Call 108 for transfer"
_AMBULANCE_LINE_HI = "स्थानांतरण के लिए 108 पर कॉल करें"


@lru_cache(maxsize=1)
def _pack() -> dict:
    return yaml.safe_load(_EMERGENCY_PACK.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def _optimizer_pack() -> dict:
    return yaml.safe_load(_OPTIMIZER_PACK.read_text(encoding="utf-8")) or {}


def _facility_rank(facility_type: str) -> int:
    return _pack().get("facility_rank", {}).get(facility_type, -1)


def detect_red_flags(*texts: str) -> list[dict]:
    """Every `packs/emergency.yaml` red-flag entry whose `phrase` appears as a
    case-insensitive substring anywhere in `texts` (an escalation reason, or
    a triage session's `red_flags`/`rationale`).
    """
    blob = " ".join(t.lower() for t in texts if t)
    if not blob:
        return []
    return [flag for flag in _pack().get("red_flags", []) if flag["phrase"] in blob]


def should_escalate(severity_esi: int, *texts: str) -> bool:
    """Section 8 N2.3 trigger: `severity_esi <= 2` (RED) OR a red-flag phrase
    match, whichever fires first.
    """
    emergency_max = 2
    if severity_esi <= emergency_max:
        return True
    return bool(detect_red_flags(*texts))


async def _facility_type_of(clinic_row: ClinicRow) -> str:
    facility_type, _schemes = _CLINIC_LOCALE_OVERRIDES.get(
        clinic_row.clinic_id, _clinic_locale_default(clinic_row.is_emergency_capable)
    )
    return facility_type


async def _clinic_row(session, clinic_id: UUID) -> ClinicRow | None:
    clinic = await session.get(Clinic, clinic_id)
    if clinic is None:
        return None
    facility_type, schemes = _CLINIC_LOCALE_OVERRIDES.get(
        clinic.id, _clinic_locale_default(clinic.is_emergency_capable)
    )
    return ClinicRow(
        clinic_id=clinic.id,
        name=clinic.name,
        lat=clinic.lat,
        lng=clinic.lng,
        facility_type=facility_type,
        is_emergency_capable=clinic.is_emergency_capable,
        schemes=schemes,
        state=clinic.state,
        pin_code=clinic.pin_code,
    )


async def _find_transfer_target(origin: ClinicRow, required_rank: int) -> tuple[ClinicRow, float] | None:
    """Nearest clinic (excluding the origin) at or above `required_rank`,
    within `max_distance_km_rural` -- the more permissive of the two urban/
    rural cutoffs, since an emergency transfer suggestion should not be
    withheld just because a patient is technically outside the urban band.
    """
    max_km = _optimizer_pack().get("max_distance_km_rural", 60)
    candidates = await all_clinics()

    best: tuple[ClinicRow, float] | None = None
    for clinic in candidates:
        if clinic.clinic_id == origin.clinic_id:
            continue
        facility_type = clinic.facility_type
        if _facility_rank(facility_type) < required_rank:
            continue
        if required_rank >= _facility_rank("dh") and not clinic.is_emergency_capable:
            continue
        distance_km = geodesic((origin.lat, origin.lng), (clinic.lat, clinic.lng)).km
        if distance_km > max_km:
            continue
        if best is None or (distance_km, str(clinic.clinic_id)) < (best[1], str(best[0].clinic_id)):
            best = (clinic, distance_km)
    return best


async def _notify(user_id: UUID | None, type_: str, payload: dict) -> None:
    """TEMP-ADAPTER: `app.services.notify.notify(user_id, type_, payload)`
    (Pratyaksh's, section 4.1) has not shipped -- only a `not_implemented`
    stub route exists at `app/api/v1/notify.py`. Falls back to a no-op with a
    logged warning, following the same guarded-import pattern
    `app/rag/tool_bridge.py` already uses for `app.ml.tools`. Remove this
    guard once `app/services/notify.py` exists.
    """
    if user_id is None:
        return
    try:
        from app.services.notify import notify as _notify_fn  # type: ignore[import-not-found]
    except ImportError:
        log.warning("notify_unavailable", type_=type_)
        return
    try:
        await _notify_fn(user_id, type_, payload)
    except Exception as exc:  # noqa: BLE001
        log.warning("notify_failed", type_=type_, error=str(exc))


async def escalate_with_referral(entry_id: UUID, reason: str, *, now: dt.datetime) -> QueueEntryOut:
    """Full N2.3 escalation: re-key to the queue head (delegated to
    `pq.escalate`, unchanged CP1 behaviour), then a referral-ladder check --
    if the assigned clinic can't manage the flagged condition, find the
    nearest capable facility and append the transfer suggestion (facility
    type, distance, "Call 108 for transfer") to `reasons`/`reasons_hi`.
    Notifies the assigned doctor via `app.services.notify` (best-effort).
    Never dispatches an ambulance -- that stays a human phone call.
    """
    async with SessionLocal() as session:
        entry = await session.get(QueueEntry, entry_id)
        if entry is None:
            raise LookupError(f"queue entry {entry_id} not found")
        origin = await _clinic_row(session, entry.clinic_id)
        doctor_user_id = None  # Doctor has no user_id exposed on QueueEntry; notify is best-effort only

    hits = detect_red_flags(reason)
    required_rank = max(
        (_facility_rank(h["min_facility_type"]) for h in hits), default=0
    )

    out = await pq.escalate(entry_id, reason, now=now)

    await _notify(
        doctor_user_id,
        "emergency_escalated",
        {"queue_entry_id": str(entry_id), "reason": reason, "clinic_id": str(entry.clinic_id)},
    )

    if origin is None:
        return out

    needs_transfer = (not origin.is_emergency_capable) or (required_rank > _facility_rank(origin.facility_type))
    if not needs_transfer:
        return out

    target = await _find_transfer_target(origin, max(required_rank, _facility_rank("chc")))
    if target is None:
        return out

    clinic, distance_km = target
    transfer_en = (
        f"Refer to {clinic.name} ({clinic.facility_type.upper()}), "
        f"{distance_km:.1f} km - {_AMBULANCE_LINE_EN}"
    )
    transfer_hi = f"{clinic.name} भेजें, {distance_km:.1f} किमी - {_AMBULANCE_LINE_HI}"

    return out.model_copy(
        update={
            "reasons": [*out.reasons, transfer_en],
            "reasons_hi": [*out.reasons_hi, transfer_hi],
        }
    )
