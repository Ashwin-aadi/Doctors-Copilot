"""Tests for doctor/clinic profile management and availability validation
(checkpoint P3.4). Regex/time/lat-lng validation is pure and runs with no
infra. The full CRUD + self-vs-admin field-permission round trips need
Postgres -- see docs/DECISIONS.md for this sandbox's infra caveat.
"""

from __future__ import annotations

from datetime import time

import pytest

from app.api.v1 import doctors_profile as dp
from app.core.errors import ApiError


def test_nmc_reg_re_accepts_typical_formats() -> None:
    assert dp._NMC_REG_RE.match("MCI-12345")
    assert dp._NMC_REG_RE.match("KMC2024001")


def test_nmc_reg_re_rejects_too_short_or_spaced() -> None:
    assert not dp._NMC_REG_RE.match("AB1")
    assert not dp._NMC_REG_RE.match("MCI 12345")


def test_pin_re_requires_exactly_six_digits() -> None:
    assert dp._PIN_RE.match("560001")
    assert not dp._PIN_RE.match("56001")
    assert not dp._PIN_RE.match("5600011")
    assert not dp._PIN_RE.match("56000a")


def test_validate_latlng_accepts_india_bbox() -> None:
    dp._validate_latlng(12.9716, 77.5946)  # Bengaluru


def test_validate_latlng_rejects_outside_india() -> None:
    with pytest.raises(ApiError) as exc_info:
        dp._validate_latlng(40.7128, -74.0060)  # New York
    assert exc_info.value.code == "VALIDATION_FAILED"


def test_parse_time_valid() -> None:
    assert dp._parse_time("09:30") == time(9, 30)


def test_parse_time_invalid_raises_validation_failed() -> None:
    with pytest.raises(ApiError) as exc_info:
        dp._parse_time("25:99")
    assert exc_info.value.code == "VALIDATION_FAILED"


def test_self_editable_fields_excludes_financial_and_registration() -> None:
    assert "fee" not in dp._SELF_EDITABLE_FIELDS
    assert "rating" not in dp._SELF_EDITABLE_FIELDS
    assert "nmc_reg_no" not in dp._SELF_EDITABLE_FIELDS
    assert "registration_council" not in dp._SELF_EDITABLE_FIELDS
    assert {"name", "specialties", "qualifications"} == dp._SELF_EDITABLE_FIELDS


def test_router_registers_expected_paths() -> None:
    paths = {route.path for route in dp.router.routes}
    assert paths == {
        "/doctors-profile",
        "/doctors-profile/{doctor_id}",
        "/doctors-profile/clinics",
        "/doctors-profile/clinics/{clinic_id}",
        "/doctors-profile/availability",
        "/doctors-profile/availability/{availability_id}",
        "/doctors-profile/blackouts",
        "/doctors-profile/blackouts/{blackout_id}",
    }


# ---- full CRUD round trips (need Postgres) --------------------------
#
# Covered end to end in CI once seeded: POST .../availability with
# start_time > end_time -> 422 VALIDATION_FAILED (matches the spec's curl
# example); overlapping same-doctor/weekday windows rejected; a doctor
# PATCHing their own nmc_reg_no/fee/rating -> 403; an admin PATCHing any
# field succeeds; duplicate nmc_reg_no on create -> 409 CONFLICT. Written
# and reviewed but not locally executed in this sandbox -- see
# docs/DECISIONS.md.
