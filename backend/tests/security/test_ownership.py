"""Ownership and consent tests for /patients/*. Full API round trips need a
reachable Postgres (see docs/DECISIONS.md); the OpenAPI wiring and
_authorize_patient_access/_get_patient_or_403 logic are additionally
verified directly so the ownership rules are checkable without live infra.
"""

from uuid import uuid4

import pytest

from app.api.v1 import patients as patients_module
from app.core.deps import CurrentUser
from app.core.errors import ApiError


def test_router_registers_expected_paths() -> None:
    paths = {route.path for route in patients_module.router.routes}
    assert paths == {
        "/patients",
        "/patients/{patient_id}",
        "/patients/{patient_id}/consent/notice",
        "/patients/{patient_id}/consent",
    }


def test_consent_notice_versions_have_en_and_hi() -> None:
    from app.services.consent import CONSENT_NOTICES

    for version, notice in CONSENT_NOTICES.items():
        assert "en" in notice and "hi" in notice, version
        assert len(notice["en"]) > 20
        assert len(notice["hi"]) > 20


@pytest.mark.asyncio
async def test_authorize_patient_access_allows_staff_and_admin() -> None:
    patient_id = uuid4()
    for role in ("staff", "admin"):
        await patients_module._authorize_patient_access(
            db=None, user=CurrentUser(id=uuid4(), role=role), patient_id=patient_id
        )  # must not raise


@pytest.mark.asyncio
async def test_get_patient_or_403_never_leaks_not_found(monkeypatch) -> None:
    class _FakeDB:
        async def get(self, model, id_):
            return None

    with pytest.raises(ApiError) as exc_info:
        await patients_module._get_patient_or_403(_FakeDB(), uuid4())
    assert exc_info.value.code == "AUTH_FORBIDDEN"
    assert exc_info.value.status_code == 403


# ---- full API round trips (need Postgres + Redis) --------------------------


@pytest.mark.asyncio
async def test_patient_reading_another_patient_is_forbidden(client, auth_headers) -> None:
    other_patient_id = "00000000-0000-0000-0000-000000000102"
    resp = await client.get(
        f"/api/v1/patients/{other_patient_id}", headers=auth_headers("patient")
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "AUTH_FORBIDDEN"


@pytest.mark.asyncio
async def test_consent_grant_read_withdraw_round_trip(client, auth_headers) -> None:
    own_patient_id = "00000000-0000-0000-0000-000000000101"
    headers = auth_headers("patient")

    grant = await client.post(
        f"/api/v1/patients/{own_patient_id}/consent",
        json={
            "version": "1.0",
            "purpose": ["triage"],
            "data_categories": ["symptoms"],
            "language": "en",
            "granular_scopes": {"triage": True, "copilot": False},
        },
        headers=headers,
    )
    assert grant.status_code == 200, grant.text
    assert grant.json()["granular_scopes"]["triage"] is True

    read = await client.get(f"/api/v1/patients/{own_patient_id}/consent", headers=headers)
    assert read.status_code == 200
    assert read.json()["withdrawn_at"] is None

    withdrawn = await client.delete(f"/api/v1/patients/{own_patient_id}/consent", headers=headers)
    assert withdrawn.status_code == 200
    assert withdrawn.json()["withdrawn_at"] is not None
