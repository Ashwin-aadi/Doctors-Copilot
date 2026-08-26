"""API-level tests for the N1.5 scheduling/queue endpoints. Needs a reachable
Postgres + Redis (`make up && make migrate`), same infra caveat as
`tests/security/test_auth_api.py`, whose solved-captcha helper this module
reuses rather than duplicating.
"""

from __future__ import annotations

import re

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.db.models.scheduling import QueueEntry
from app.db.session import SessionLocal
from tests.security.test_auth_api import _solved_captcha_header
from tests.services.conftest import CLINIC_PHC, patient_id

_TOKEN_RE = re.compile(r"^[A-Z]-\d{3}$")


@pytest_asyncio.fixture(autouse=True)
async def _clean_queue():
    async def _wipe() -> None:
        async with SessionLocal() as session:
            await session.execute(delete(QueueEntry))
            await session.commit()

    await _wipe()
    yield
    await _wipe()


@pytest.mark.asyncio
async def test_list_doctors_returns_bilingual_ranked_results(client, auth_headers):
    resp = await client.get(
        "/api/v1/doctors",
        params={"specialty": "cardiology", "lat": 13.08, "lng": 80.27, "language": "hi", "scheme": "pmjay"},
        headers=auth_headers("patient"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    assert len(body[0]["reasons"]) >= 1
    assert len(body[0]["reasons_hi"]) >= 1
    assert body[0]["score"] > 0


@pytest.mark.asyncio
async def test_list_doctors_requires_auth(client):
    resp = await client.get("/api/v1/doctors", params={"specialty": "cardiology"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_appointment_books_slot_and_enqueues(client, auth_headers):
    captcha_headers = await _solved_captcha_header(client)
    headers = {**auth_headers("patient"), **captcha_headers}
    resp = await client.post(
        "/api/v1/appointments",
        headers=headers,
        json={
            "patient_id": str(patient_id(1)),
            "specialty": "cardiology",
            "lat": 13.08,
            "lng": 80.27,
            "language": "hi",
            "scheme": "pmjay",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["appointment"]["id"]
    assert body["queue"]["position"] >= 1
    assert _TOKEN_RE.match(body["queue"]["token"])
    assert len(body["doctor"]["reasons"]) >= 1


@pytest.mark.asyncio
async def test_create_appointment_requires_captcha(client, auth_headers):
    resp = await client.post(
        "/api/v1/appointments",
        headers=auth_headers("patient"),
        json={"patient_id": str(patient_id(1)), "specialty": "cardiology"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CAPTCHA_REQUIRED"


@pytest.mark.asyncio
async def test_walk_in_creates_queue_entry_with_token(client, auth_headers):
    resp = await client.post(
        "/api/v1/queue/walk-in",
        headers=auth_headers("staff"),
        json={"clinic_id": str(CLINIC_PHC), "patient_id": str(patient_id(2)), "severity_esi": 3},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["position"] >= 1
    assert _TOKEN_RE.match(body["token"])


@pytest.mark.asyncio
async def test_get_queue_lists_todays_waiting_entries(client, auth_headers):
    await client.post(
        "/api/v1/queue/walk-in",
        headers=auth_headers("staff"),
        json={"clinic_id": str(CLINIC_PHC), "patient_id": str(patient_id(3)), "severity_esi": 2},
    )
    resp = await client.get(f"/api/v1/queue/{CLINIC_PHC}", headers=auth_headers("staff"))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    assert all(e["reasons"] and e["token"] for e in body)


@pytest.mark.asyncio
async def test_escalate_moves_entry_to_head(client, auth_headers):
    walk_in = await client.post(
        "/api/v1/queue/walk-in",
        headers=auth_headers("staff"),
        json={"clinic_id": str(CLINIC_PHC), "patient_id": str(patient_id(4)), "severity_esi": 4},
    )
    entry_id = walk_in.json()["id"]

    resp = await client.post(
        f"/api/v1/queue/{entry_id}/escalate",
        headers=auth_headers("doctor"),
        json={"reason": "snakebite with bleeding gums"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["emergency"] is True
    assert body["triage_colour"] == "red"
    assert body["position"] == 1
