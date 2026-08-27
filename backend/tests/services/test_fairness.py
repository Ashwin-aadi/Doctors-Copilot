"""Optimizer v2 (section 8 N3.3): travel bands, the session-capacity fairness
constraint, public-facility load sharing, and the golden ranking snapshot
that N3.1 asks for.

The pure scoring helpers (`_travel_score`, `_fairness`, `_load_sharing`) are
tested directly -- they take no DB and no clock, so they can be asserted
exactly rather than approximately, which is the point of keeping the rule
layer free of models.
"""

from __future__ import annotations

import datetime as dt
import statistics
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.db.models.scheduling import QueueEntry
from app.db.session import SessionLocal
from app.services.scheduling.optimizer import (
    _fairness,
    _load_sharing,
    _pack,
    _travel_score,
    rank_doctors,
)
from app.services.scheduling.repo import doctor_session_load
from tests.services.conftest import CLINIC_DH, CLINIC_PHC, doctor_id, patient_id

NOW = dt.datetime(2026, 1, 12, 9, 0, tzinfo=dt.UTC)  # 14:30 IST, Monday

_CREATED: list[object] = []


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    _CREATED.clear()
    yield
    if _CREATED:
        async with SessionLocal() as session:
            await session.execute(delete(QueueEntry).where(QueueEntry.id.in_(_CREATED)))
            await session.commit()
    _CREATED.clear()


async def _load_doctor(doctor: str, clinic, count: int) -> None:
    """Park `count` walk-in queue entries on a doctor for the fixture service
    day, which is what `doctor_session_load` counts.
    """
    async with SessionLocal() as session:
        for _ in range(count):
            entry = QueueEntry(
                id=uuid4(),
                appointment_id=None,
                patient_id=patient_id(1),
                doctor_id=doctor,
                clinic_id=clinic,
                severity_esi=4,
                emergency=False,
                enqueued_at=NOW,
                status="waiting",
            )
            session.add(entry)
            _CREATED.append(entry.id)
        await session.commit()


# --- travel bands ----------------------------------------------------------


def test_travel_bands_are_steeper_in_a_city_than_in_the_countryside():
    # 8 km: across a city in OPD traffic vs. a short rural ride. The whole
    # point of splitting the curves is that these two must not score alike.
    urban, _en, _hi = _travel_score(8.0, "dh")
    rural, _en2, _hi2 = _travel_score(8.0, "phc")
    assert rural > urban


@pytest.mark.parametrize(
    ("km", "facility", "expected"),
    [
        (0.5, "dh", 1.0),
        (2.99, "dh", 1.0),
        (3.0, "dh", 0.75),  # half-open on the upper bound
        (7.99, "dh", 0.75),
        (14.0, "dh", 0.45),
        (24.0, "dh", 0.2),
        (99.0, "dh", 0.05),  # final open-ended band
        (4.0, "phc", 1.0),
        (5.0, "phc", 0.8),
        (200.0, "phc", 0.1),
    ],
)
def test_travel_band_boundaries_are_exact_and_total(km, facility, expected):
    score, _en, _hi = _travel_score(km, facility)
    assert score == expected


def test_every_travel_band_carries_a_bilingual_label_under_60_chars():
    pack = _pack()
    for key in ("travel_bands_urban", "travel_bands_rural"):
        for band in pack[key]:
            assert band["label_en"] and band["label_hi"]
            assert len(band["label_en"]) <= 60
            assert len(band["label_hi"]) <= 60


# --- fairness curve --------------------------------------------------------


def test_fairness_is_flat_below_the_soft_threshold_then_decays_to_zero():
    assert _fairness(0, 50, 0.8) == 1.0
    assert _fairness(40, 50, 0.8) == 1.0  # exactly at the threshold
    assert _fairness(50, 50, 0.8) == 0.0  # at the cap
    mid = _fairness(45, 50, 0.8)
    assert 0.0 < mid < 1.0
    # monotonically non-increasing in load
    loads = [_fairness(n, 50, 0.8) for n in range(0, 51)]
    assert all(a >= b for a, b in zip(loads, loads[1:], strict=False))


def test_fairness_is_neutral_when_capacity_is_unset():
    assert _fairness(100, 0, 0.8) == 1.0


def test_load_sharing_penalises_only_above_the_mean():
    assert _load_sharing(3, 10.0) == 1.0
    assert _load_sharing(10, 10.0) == 1.0
    assert _load_sharing(20, 10.0) == 0.5
    assert _load_sharing(5, 0.0) == 1.0


# --- session capacity as a hard filter -------------------------------------


@pytest.mark.asyncio
async def test_doctor_at_the_session_cap_is_filtered_out_entirely():
    capacity = int(_pack()["max_patients_per_doctor_per_session"])
    phc_doctors = [doctor_id(1), doctor_id(2)]

    before = await rank_doctors(
        specialty="general_medicine", lat=None, lng=None, date_from=NOW, now=NOW
    )
    assert doctor_id(1) in [d.doctor_id for d in before]

    await _load_doctor(phc_doctors[0], CLINIC_PHC, capacity)

    after = await rank_doctors(
        specialty="general_medicine", lat=None, lng=None, date_from=NOW, now=NOW
    )
    assert doctor_id(1) not in [d.doctor_id for d in after], "a doctor at the cap is not offered"
    # the other PHC doctor is still available -- the filter is per-doctor
    assert doctor_id(2) in [d.doctor_id for d in after]


@pytest.mark.asyncio
async def test_soft_penalty_reorders_before_the_hard_cap_bites():
    capacity = int(_pack()["max_patients_per_doctor_per_session"])
    # 90% loaded: past the 0.8 soft threshold, still under the hard cap
    await _load_doctor(doctor_id(1), CLINIC_PHC, int(capacity * 0.9))

    ranked = await rank_doctors(
        specialty="general_medicine", lat=None, lng=None, date_from=NOW, now=NOW
    )
    by_id = {d.doctor_id: d for d in ranked}
    assert doctor_id(1) in by_id, "still admissible below the hard cap"
    assert any("limit" in r.lower() for r in by_id[doctor_id(1)].reasons)
    # and it now scores below its equally-qualified, unloaded colleague
    assert by_id[doctor_id(1)].score < by_id[doctor_id(2)].score


@pytest.mark.asyncio
async def test_session_load_counts_walk_ins_for_the_service_day():
    await _load_doctor(doctor_id(2), CLINIC_PHC, 3)
    loads = await doctor_session_load([doctor_id(2)], now=NOW)
    assert loads[doctor_id(2)] == 3
    # a different service day sees none of them
    next_day = NOW + dt.timedelta(days=1)
    assert (await doctor_session_load([doctor_id(2)], now=next_day))[doctor_id(2)] == 0


@pytest.mark.asyncio
async def test_load_spread_is_tighter_than_a_winner_takes_all_assignment():
    """Once the leading doctor crosses the soft threshold, a repeated
    book-rank-#1 loop starts spreading onto their colleague instead of
    piling on.

    Deliberately *not* asserted below the threshold: the fairness term is
    flat there by design. Spreading load across equally-idle doctors would
    trade away specialty, distance and language match for no real benefit,
    so `_fairness` stays neutral until the session is genuinely filling up.
    """
    capacity = int(_pack()["max_patients_per_doctor_per_session"])
    threshold = float(_pack()["fairness_soft_threshold"])

    # put the stronger-rated PHC doctor just past the soft threshold
    await _load_doctor(doctor_id(1), CLINIC_PHC, int(capacity * threshold) + 2)

    # `general_medicine` also matches doctors seeded by scripts/seed_users.py
    # in a separate id namespace; this case is about how the two *Chennai*
    # PHC doctors share load, so the pick is taken from that pair only.
    fixture_pair = {doctor_id(1), doctor_id(2)}

    picks: list[object] = []
    for _ in range(8):
        ranked = await rank_doctors(
            specialty="general_medicine", lat=None, lng=None, date_from=NOW, now=NOW
        )
        chosen = next(d.doctor_id for d in ranked if d.doctor_id in fixture_pair)
        picks.append(chosen)
        await _load_doctor(chosen, CLINIC_PHC, 1)

    counts: dict[object, int] = {}
    for p in picks:
        counts[p] = counts.get(p, 0) + 1

    assert doctor_id(2) in counts, "load never moved off the over-subscribed doctor"
    # a winner-takes-all loop would put all 8 on one doctor (pstdev == 4.0)
    spread = statistics.pstdev(list(counts.values()))
    assert spread < 4.0


# --- determinism / golden snapshot (N3.1) ----------------------------------


@pytest.mark.asyncio
async def test_ranking_is_byte_identical_across_repeated_calls():
    kw = dict(
        specialty="cardiology",
        lat=13.08,
        lng=80.27,
        date_from=NOW,
        language="hi",
        scheme="pmjay",
        now=NOW,
    )
    runs = [await rank_doctors(**kw) for _ in range(3)]
    serialised = [[d.model_dump(mode="json") for d in run] for run in runs]
    assert serialised[0] == serialised[1] == serialised[2]


@pytest.mark.asyncio
async def test_golden_ranking_snapshot_for_the_chennai_fixture():
    """N3.1's gate: the deterministic Chennai fixture produces this exact
    ranking. If a weight or band changes deliberately, update the expected
    block below *and* the sweep table in docs/RULES.md -- an unexplained
    change here means the optimizer stopped being reproducible.
    """
    ranked = await rank_doctors(
        specialty="cardiology",
        lat=13.08,
        lng=80.27,
        date_from=NOW,
        language="hi",
        scheme="pmjay",
        now=NOW,
    )
    # cardiology's facility floor is `dh`, so the related-specialty
    # general_medicine doctors at the PHC are filtered out before scoring --
    # a cardiac case is not routed to a primary health centre.
    assert [d.doctor_id for d in ranked] == [doctor_id(5)]
    assert [d.clinic_id for d in ranked] == [CLINIC_DH]
    assert [round(d.score, 6) for d in ranked] == sorted(
        [round(d.score, 6) for d in ranked], reverse=True
    )
    assert all(d.reasons and d.reasons_hi for d in ranked)
