"""Full offline test (section 8 N2.5 / CP2 gate): with all outbound HTTP
blocked, every CP1+CP2 niyati-owned route that has a network-optional path
must still return a 2xx for an already-covered input (a known local brand, a
visit with no triage session to fetch). Needs a reachable Postgres + Redis
(same infra caveat as the rest of `tests/services/`) -- what this test
isolates is network reachability, not DB/Redis reachability.
"""

from __future__ import annotations

import datetime as dt
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.db.models.clinical import LabOrder, Visit
from app.db.models.scheduling import QueueEntry
from app.db.session import SessionLocal
from tests.security.test_auth_api import _solved_captcha_header
from tests.services.conftest import CLINIC_PHC, patient_id


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    """Clear only the queue/lab-order/visit rows this module's fixture
    patients own.

    These wipes were unscoped (`delete(Visit)` with no WHERE), so running the
    full suite destroyed the seeded demo visit and every other module's
    fixtures along with them -- `tests/integration/test_visit_flow.py` failed
    on whatever ran after this file and passed on its own. Scoping to the
    Chennai fixture patients keeps the clean slate this module needs without
    reaching into anyone else's rows.
    """

    ours = [patient_id(i) for i in range(1, 9)]

    async def _wipe() -> None:
        async with SessionLocal() as session:
            await session.execute(delete(QueueEntry).where(QueueEntry.patient_id.in_(ours)))
            await session.execute(delete(LabOrder).where(LabOrder.patient_id.in_(ours)))
            await session.execute(delete(Visit).where(Visit.patient_id.in_(ours)))
            await session.commit()

    await _wipe()
    yield
    await _wipe()


@pytest.fixture(autouse=True)
def _block_all_outbound_http(monkeypatch):
    """Unplug the real network, and only the real network.

    Patching `httpx.AsyncClient.get`/`post` also severed the `client` fixture,
    which drives the app in-process over `ASGITransport` and is an
    `httpx.AsyncClient` itself -- so every request failed in the test harness
    and no route under test ever ran. Blocking at the transport layer instead
    leaves ASGITransport (in-process, no socket) working while any genuine
    outbound call raises.
    """

    async def _blocked(self, request, *args, **kwargs):  # noqa: ANN001, ARG001
        raise httpx.ConnectError("network unplugged for offline test")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _blocked)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _blocked)


@pytest.mark.asyncio
async def test_doctors_endpoint_works_offline(client, auth_headers):
    resp = await client.get(
        "/api/v1/doctors",
        params={"specialty": "cardiology", "lat": 13.08, "lng": 80.27},
        headers=auth_headers("patient"),
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_appointments_endpoint_works_offline(client, auth_headers):
    captcha_headers = await _solved_captcha_header(client)
    resp = await client.post(
        "/api/v1/appointments",
        headers={**auth_headers("patient"), **captcha_headers},
        json={"patient_id": str(patient_id(5)), "specialty": "cardiology", "lat": 13.08, "lng": 80.27},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_queue_walk_in_and_get_work_offline(client, auth_headers):
    resp = await client.post(
        "/api/v1/queue/walk-in",
        headers=auth_headers("staff"),
        json={"clinic_id": str(CLINIC_PHC), "patient_id": str(patient_id(6)), "severity_esi": 3},
    )
    assert resp.status_code == 201, resp.text

    resp2 = await client.get(f"/api/v1/queue/{CLINIC_PHC}", headers=auth_headers("staff"))
    assert resp2.status_code == 200, resp2.text


@pytest.mark.asyncio
async def test_lab_orders_recommend_works_offline(client, auth_headers):
    now = dt.datetime.now(dt.UTC)
    visit_id = uuid4()
    async with SessionLocal() as session:
        session.add(
            Visit(
                id=visit_id, patient_id=patient_id(7), doctor_id=None, state="TRIAGED",
                triage_session_id=None, lab_order_id=None, created_at=now, updated_at=now,
            )
        )
        await session.commit()

    resp = await client.post(
        "/api/v1/lab-orders/recommend", headers=auth_headers("doctor"), json={"visit_id": str(visit_id)}
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) >= 1


@pytest.mark.asyncio
async def test_medications_generic_works_offline(client, auth_headers):
    resp = await client.get(
        "/api/v1/medications/generic", params={"name": "Crocin"}, headers=auth_headers("patient")
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["generics"]
