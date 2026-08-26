import datetime as dt

import pytest

from app.services.scheduling.repo import (
    availability_for,
    booked_slots,
    clinics_by_ids,
    doctors_by_specialty,
    queue_load,
)
from tests.services.conftest import CLINIC_CHC, CLINIC_DH, CLINIC_PHC, NOW, doctor_id


@pytest.mark.asyncio
async def test_doctors_by_specialty_returns_rows_with_expected_fields():
    rows = await doctors_by_specialty("cardiology", None)
    assert len(rows) >= 1
    row = rows[0]
    assert hasattr(row, "clinic_id")
    assert hasattr(row, "languages")
    assert hasattr(row, "fee_inr")
    assert row.languages, "languages must be populated (TEMP-ADAPTER default at minimum)"


@pytest.mark.asyncio
async def test_doctors_by_specialty_respects_max_fee():
    rows = await doctors_by_specialty("cardiology", max_fee=100.0)
    assert all(r.fee_inr <= 100.0 for r in rows)


@pytest.mark.asyncio
async def test_doctors_by_specialty_no_match_returns_empty():
    rows = await doctors_by_specialty("nonexistent_specialty", None)
    assert rows == []


@pytest.mark.asyncio
async def test_availability_for_batches_across_doctors():
    ids = [doctor_id(1), doctor_id(5)]
    out = await availability_for(ids, dt.date(2026, 1, 12), dt.date(2026, 1, 12))
    assert set(out.keys()) == set(ids)
    assert len(out[doctor_id(1)]) == 2  # morning + evening session
    assert all(a.doctor_id == doctor_id(1) for a in out[doctor_id(1)])


@pytest.mark.asyncio
async def test_availability_for_empty_input():
    assert await availability_for([], dt.date(2026, 1, 12), dt.date(2026, 1, 12)) == {}


@pytest.mark.asyncio
async def test_booked_slots_empty_when_no_appointments():
    ids = [doctor_id(1)]
    out = await booked_slots(ids, dt.date(2026, 1, 12), dt.date(2026, 1, 12))
    assert out == {doctor_id(1): []}


@pytest.mark.asyncio
async def test_queue_load_zero_when_no_queue_entries():
    out = await queue_load([CLINIC_PHC, CLINIC_CHC], now=NOW)
    assert out == {CLINIC_PHC: 0, CLINIC_CHC: 0}


@pytest.mark.asyncio
async def test_clinics_by_ids_carries_facility_type_and_schemes():
    out = await clinics_by_ids([CLINIC_PHC, CLINIC_DH])
    assert out[CLINIC_PHC].facility_type == "phc"
    assert out[CLINIC_PHC].is_emergency_capable is False
    assert out[CLINIC_DH].facility_type == "dh"
    assert out[CLINIC_DH].is_emergency_capable is True
    assert "pmjay" in out[CLINIC_DH].schemes


@pytest.mark.asyncio
async def test_clinics_by_ids_empty_input():
    assert await clinics_by_ids([]) == {}
