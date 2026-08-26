import datetime as dt

from app.services.scheduling.slots import IST, free_slots
from tests.services.conftest import CLINIC_CHC, CLINIC_PHC, doctor_id


def test_free_slots_sorted_non_overlapping_and_in_ist_sessions():
    slots = free_slots(doctor_id(1), CLINIC_PHC, dt.date(2026, 1, 12), dt.date(2026, 1, 13), booked=[])
    assert slots == sorted(slots)
    assert all(a < b for a, b in slots)
    assert all(slots[i][1] <= slots[i + 1][0] for i in range(len(slots) - 1))
    assert not any(13 <= a.astimezone(IST).hour < 17 for a, _ in slots), "slot inside IST lunch break"


def test_free_slots_respects_booked():
    baseline = free_slots(doctor_id(1), CLINIC_PHC, dt.date(2026, 1, 12), dt.date(2026, 1, 12), booked=[])
    assert baseline
    taken = [baseline[0]]
    remaining = free_slots(doctor_id(1), CLINIC_PHC, dt.date(2026, 1, 12), dt.date(2026, 1, 12), booked=taken)
    assert baseline[0] not in remaining
    assert len(remaining) == len(baseline) - 1


def test_free_slots_skips_sunday_for_phc():
    sunday = dt.date(2026, 1, 18)  # Sunday
    slots = free_slots(doctor_id(1), CLINIC_PHC, sunday, sunday, booked=[])
    assert slots == []


def test_free_slots_skips_gazetted_holiday():
    republic_day = dt.date(2026, 1, 26)  # Monday, gazetted holiday, in queue.yaml
    slots = free_slots(doctor_id(1), CLINIC_PHC, republic_day, republic_day, booked=[])
    assert slots == []


def test_free_slots_no_availability_returns_empty():
    slots = free_slots(doctor_id(1), CLINIC_CHC, dt.date(2026, 1, 12), dt.date(2026, 1, 12), booked=[])
    assert slots == []


def test_free_slots_deterministic_across_calls():
    a = free_slots(doctor_id(2), CLINIC_PHC, dt.date(2026, 1, 12), dt.date(2026, 1, 13), booked=[])
    b = free_slots(doctor_id(2), CLINIC_PHC, dt.date(2026, 1, 12), dt.date(2026, 1, 13), booked=[])
    assert a == b
