"""Doctor ranking: hard filters (specialty ladder, facility floor, fee cap,
horizon availability) followed by a weighted score. Pure with respect to
`now` -- every dynamic input (`now`, `date_from`) is a parameter, never a
wall-clock read.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from uuid import UUID

import yaml
from geopy.distance import geodesic

from app.services.scheduling.repo import (
    DoctorRow,
    availability_for,  # noqa: F401  (re-exported for callers that expect it here)
    booked_slots,
    clinics_by_ids,
    doctor_session_load,
    doctors_by_specialty,
    queue_load,
)
from app.services.scheduling.schemas import DoctorRankedOut
from app.services.scheduling.slots import free_slots

_PACKS_DIR = Path(__file__).resolve().parents[1] / "rules" / "packs"
_OPTIMIZER_PACK = _PACKS_DIR / "optimizer.yaml"

_FACILITY_RANK = {"phc": 0, "chc": 1, "sdh": 2, "dh": 3, "medical_college": 4}


@lru_cache(maxsize=1)
def _pack() -> dict:
    return yaml.safe_load(_OPTIMIZER_PACK.read_text(encoding="utf-8")) or {}


def _candidate_specialties(specialty: str) -> list[tuple[str, float]]:
    """(specialty, specialty_match_score) pairs to search, exact first."""
    pack = _pack()
    out = [(specialty, 1.0)]
    for related in pack.get("related_specialties", {}).get(specialty, []):
        out.append((related, 0.6))
    return out


def _reason(en: str, hi: str) -> tuple[str, str]:
    return (en, hi)


def _travel_bands(facility_type: str) -> list[dict]:
    """N3.3: the urban or rural travel curve for this facility's catchment.

    A PHC/CHC catchment is rural by definition; a district hospital or a
    private hospital sits in a town or city. Falls back to the rural curve,
    which is the more forgiving of the two -- under-rewarding a nearby urban
    clinic is a much smaller error than telling a rural patient that a 25 km
    trip is nothing.
    """
    pack = _pack()
    urban = set(pack.get("urban_facility_types", []))
    key = "travel_bands_urban" if facility_type in urban else "travel_bands_rural"
    return pack.get(key, [])


def _travel_score(distance_km: float, facility_type: str) -> tuple[float, str, str]:
    """Score plus the band's bilingual label. Bands are half-open on the
    upper bound and the final band has `to: null`, so every distance lands in
    exactly one band and the result is total.
    """
    for band in _travel_bands(facility_type):
        upper = band.get("to")
        if upper is None or distance_km < float(upper):
            return float(band.get("score", 0.0)), band.get("label_en", ""), band.get("label_hi", "")
    return 0.0, "", ""


def _fairness(session_load: int, capacity: int, soft_threshold: float) -> float:
    """1.0 while the doctor is comfortably under load, falling linearly to 0
    between the soft threshold and the hard cap.

    The hard cap itself is enforced as a filter before scoring -- this term
    only shapes the ordering of doctors who are all still admissible, so that
    the last few slots of a session spread out instead of piling onto
    whoever happens to rank highest on the other factors.
    """
    if capacity <= 0:
        return 1.0
    utilisation = session_load / capacity
    if utilisation <= soft_threshold:
        return 1.0
    if utilisation >= 1.0:
        return 0.0
    return (1.0 - utilisation) / (1.0 - soft_threshold)


def _load_sharing(clinic_load: int, mean_public_load: float) -> float:
    """Penalise a public facility carrying more than its share of the
    candidate set's queue, so an over-subscribed DH stops absorbing cases a
    nearby CHC could take. 1.0 at or below the mean, decaying above it.
    Private capacity is excluded by the caller -- it is not a public resource
    to balance.
    """
    if mean_public_load <= 0:
        return 1.0
    if clinic_load <= mean_public_load:
        return 1.0
    return mean_public_load / clinic_load


async def rank_doctors(
    *,
    specialty: str,
    lat: float | None,
    lng: float | None,
    date_from: dt.datetime,
    horizon_days: int = 7,
    max_fee: float | None = None,
    language: str | None = None,
    scheme: str | None = None,
    now: dt.datetime,
) -> list[DoctorRankedOut]:
    pack = _pack()
    weights = pack.get("weights", {})
    horizon_days = pack.get("horizon_days", horizon_days)

    # 1. gather candidates across exact + related specialties, keep the best match per doctor
    best_match: dict[UUID, float] = {}
    rows_by_id: dict[UUID, DoctorRow] = {}
    for cand_specialty, match_score in _candidate_specialties(specialty):
        rows = await doctors_by_specialty(cand_specialty, max_fee)
        for row in rows:
            if match_score > best_match.get(row.doctor_id, -1.0):
                best_match[row.doctor_id] = match_score
                rows_by_id[row.doctor_id] = row

    if not rows_by_id:
        return []

    doctor_ids = list(rows_by_id.keys())
    clinic_ids = list({row.clinic_id for row in rows_by_id.values()})

    clinics = await clinics_by_ids(clinic_ids)
    date_to = date_from.date() + dt.timedelta(days=horizon_days)
    booked = await booked_slots(doctor_ids, date_from.date(), date_to)
    loads = await queue_load(clinic_ids, now=now)
    session_loads = await doctor_session_load(doctor_ids, now=now)

    # N3.3 fairness: a doctor already at the session cap is removed from the
    # candidate set entirely. A soft penalty alone would still hand them the
    # 51st patient whenever they out-scored everyone else on distance or
    # language, which is exactly the pile-up the constraint exists to stop.
    session_capacity = int(pack.get("max_patients_per_doctor_per_session", 50))
    soft_threshold = float(pack.get("fairness_soft_threshold", 0.8))

    # facility floor for the *requested* specialty (a related-specialty match
    # never lowers the bar -- the case still needs the requested level of care)
    min_facility = pack.get("min_facility_type", {}).get(specialty)
    min_facility_rank = _FACILITY_RANK.get(min_facility, -1) if min_facility else -1
    max_distance_rural = pack.get("max_distance_km_rural", 60)
    free_facility_types = set(pack.get("free_facility_types", []))

    candidates: list[dict] = []
    for doctor_id in doctor_ids:
        row = rows_by_id[doctor_id]
        clinic = clinics.get(row.clinic_id)
        if clinic is None:
            continue
        if min_facility_rank >= 0 and _FACILITY_RANK.get(clinic.facility_type, -1) < min_facility_rank:
            continue

        session_load = session_loads.get(doctor_id, 0)
        if session_load >= session_capacity:
            continue

        distance_km: float | None = None
        if lat is not None and lng is not None:
            distance_km = geodesic((lat, lng), (clinic.lat, clinic.lng)).km
            if distance_km > max_distance_rural:
                continue

        slots = free_slots(doctor_id, row.clinic_id, date_from.date(), date_to, booked.get(doctor_id, []))
        if not slots:
            continue
        next_slot = slots[0][0]

        candidates.append(
            {
                "row": row,
                "clinic": clinic,
                "specialty_match": best_match[doctor_id],
                "distance_km": distance_km,
                "next_slot": next_slot,
                "queue_load": loads.get(row.clinic_id, 0),
                "session_load": session_load,
            }
        )

    if not candidates:
        return []

    max_fee_in_set = max((c["row"].fee_inr for c in candidates), default=0.0) or 0.0

    # Load-sharing baseline: the mean queue load across the *public* clinics
    # in this candidate set. Computed per call rather than globally, so the
    # comparison is always "against the alternatives this patient actually
    # has", not against every facility in the state.
    load_sharing_types = set(pack.get("load_sharing_facility_types", []))
    public_loads = [
        c["queue_load"] for c in candidates if c["clinic"].facility_type in load_sharing_types
    ]
    mean_public_load = sum(public_loads) / len(public_loads) if public_loads else 0.0

    ranked: list[DoctorRankedOut] = []
    for c in candidates:
        row: DoctorRow = c["row"]
        clinic = c["clinic"]
        reasons: list[tuple[str, str]] = []

        specialty_score = c["specialty_match"]
        if specialty_score >= 1.0:
            reasons.append(_reason(f"Exact match for {specialty.replace('_', ' ')}", "विशेषज्ञता से पूर्ण मेल"))
        else:
            reasons.append(_reason("Related specialist available", "संबंधित विशेषज्ञ उपलब्ध"))

        hours_until = max(0.0, (c["next_slot"] - now).total_seconds() / 3600)
        availability_score = 1 / (1 + hours_until / 6)
        if hours_until < 1:
            reasons.append(_reason("Next slot within the hour", "अगला स्लॉट एक घंटे में"))
        else:
            reasons.append(_reason(f"Next slot in {round(hours_until)} h", f"अगला स्लॉट {round(hours_until)} घंटे में"))

        if c["distance_km"] is None:
            distance_score = 1.0
        else:
            # N3.3: travel bands, not the raw-km curve CP1 used.
            distance_score, band_en, band_hi = _travel_score(
                c["distance_km"], clinic.facility_type
            )
            reasons.append(
                _reason(
                    f"{band_en}, {c['distance_km']:.1f} km away".lstrip(", "),
                    f"{band_hi}, {c['distance_km']:.1f} किमी दूर".lstrip(", "),
                )
            )

        queue_score = 1 / (1 + c["queue_load"] / 5)
        if c["queue_load"] > 0:
            reasons.append(_reason(f"{c['queue_load']} waiting", f"{c['queue_load']} प्रतीक्षा में"))

        if language is None:
            language_score = 1.0
        elif language in row.languages:
            language_score = 1.0
            reasons.append(_reason(f"Speaks {language.upper()}", "आपकी भाषा बोलते हैं"))
        elif "en" in row.languages:
            language_score = 0.5
            reasons.append(_reason("Speaks English", "अंग्रेजी बोलते हैं"))
        else:
            language_score = 0.0

        if scheme is None:
            scheme_score = 1.0
        elif scheme in clinic.schemes:
            scheme_score = 1.0
            reasons.append(_reason(f"{scheme.upper()} empanelled - no charge", f"{scheme.upper()} में सूचीबद्ध - कोई शुल्क नहीं"))
        else:
            scheme_score = 0.0

        rating_score = row.rating / 5

        if clinic.facility_type in free_facility_types:
            fee_penalty = 0.0
        elif max_fee_in_set > 0:
            fee_penalty = row.fee_inr / max_fee_in_set
        else:
            fee_penalty = 0.0

        fairness_score = _fairness(c["session_load"], session_capacity, soft_threshold)
        if fairness_score < 1.0:
            reasons.append(
                _reason("Nearing today's patient limit", "आज की मरीज़ सीमा के करीब")
            )

        if clinic.facility_type in load_sharing_types:
            load_sharing_score = _load_sharing(c["queue_load"], mean_public_load)
        else:
            load_sharing_score = 1.0

        score = (
            weights.get("specialty", 0) * specialty_score
            + weights.get("availability", 0) * availability_score
            + weights.get("distance", 0) * distance_score
            + weights.get("queue", 0) * queue_score
            + weights.get("language", 0) * language_score
            + weights.get("scheme", 0) * scheme_score
            + weights.get("rating", 0) * rating_score
            + pack.get("weights_fairness", 0) * fairness_score
            + pack.get("weights_load_sharing", 0) * load_sharing_score
            - weights.get("fee", 0) * fee_penalty
        )

        ranked.append(
            DoctorRankedOut(
                doctor_id=row.doctor_id,
                name=row.name,
                specialty=specialty,
                clinic_id=clinic.clinic_id,
                clinic_name=clinic.name,
                distance_km=round(c["distance_km"], 2) if c["distance_km"] is not None else 0.0,
                next_slot=c["next_slot"],
                queue_load=c["queue_load"],
                rating=row.rating,
                fee=row.fee_inr,
                nmc_reg_no=row.nmc_reg_no,
                score=round(score, 6),
                reasons=[en for en, _hi in reasons],
                reasons_hi=[hi for _en, hi in reasons],
            )
        )

    ranked.sort(key=lambda d: (-d.score, d.next_slot, str(d.doctor_id)))
    return ranked
