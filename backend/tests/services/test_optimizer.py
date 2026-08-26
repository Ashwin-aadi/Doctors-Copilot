import datetime as dt

import pytest

from app.services.scheduling.optimizer import rank_doctors
from tests.services.conftest import CLINIC_DH

NOW = dt.datetime(2026, 1, 12, 9, tzinfo=dt.UTC)  # 14:30 IST, Monday


@pytest.mark.asyncio
async def test_rank_doctors_returns_scored_bilingual_results():
    r = await rank_doctors(
        specialty="cardiology", lat=13.08, lng=80.27, date_from=NOW, language="hi", scheme="pmjay", now=NOW
    )
    assert r
    assert r[0].score >= r[-1].score
    assert all(d.reasons and d.reasons_hi for d in r)
    assert all(len(d.reasons) == len(d.reasons_hi) for d in r)


@pytest.mark.asyncio
async def test_rank_doctors_deterministic_across_calls():
    kw = dict(specialty="cardiology", lat=13.08, lng=80.27, date_from=NOW, language="hi", scheme="pmjay", now=NOW)
    r1 = await rank_doctors(**kw)
    r2 = await rank_doctors(**kw)
    assert [d.doctor_id for d in r1] == [d.doctor_id for d in r2]
    assert [d.score for d in r1] == [d.score for d in r2]


@pytest.mark.asyncio
async def test_rank_doctors_enforces_specialty_facility_floor():
    # cardiology's min_facility_type is "dh" -- only the district hospital
    # clinic qualifies in the Chennai fixture, even though the PHC/CHC are
    # reachable and have free slots for their own specialties.
    r = await rank_doctors(specialty="cardiology", lat=None, lng=None, date_from=NOW, now=NOW)
    assert r
    assert all(d.clinic_id == CLINIC_DH for d in r)


@pytest.mark.asyncio
async def test_rank_doctors_respects_max_fee():
    r = await rank_doctors(specialty="general_medicine", lat=None, lng=None, date_from=NOW, max_fee=0.0, now=NOW)
    assert r
    assert all(d.fee <= 0.0 for d in r)


@pytest.mark.asyncio
async def test_rank_doctors_unknown_specialty_returns_empty():
    r = await rank_doctors(specialty="nonexistent_specialty", lat=None, lng=None, date_from=NOW, now=NOW)
    assert r == []


@pytest.mark.asyncio
async def test_rank_doctors_related_specialty_scores_lower_than_exact():
    # general_medicine is listed as related to cardiology at 0.6 vs 1.0 exact;
    # with no facility floor filtering (min_facility_type only trims for the
    # requested specialty itself) confirm the ordering favours exact matches.
    r = await rank_doctors(specialty="cardiology", lat=None, lng=None, date_from=NOW, now=NOW)
    assert r
    assert r[0].specialty == "cardiology"
