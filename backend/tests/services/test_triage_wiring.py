"""N2.1: a finalized triage result must actually reach `rank_doctors` and
`QueueEntry.severity_esi` on booking -- a triaged RED patient must not
silently book at the routine tier-4 default. Needs a reachable Postgres +
Redis (same infra caveat as the rest of `tests/services/`).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.db.models.clinical import TriageSession
from app.db.models.scheduling import QueueEntry
from app.db.session import SessionLocal
from app.schemas.triage import TriageResult, colour_for_esi
from tests.security.test_auth_api import _solved_captcha_header
from tests.services.conftest import patient_id


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    # Scoped to this module's fixture patients. Unscoped, the TriageSession
    # wipe hit rows the seeded demo visit still points at and failed on
    # `visits_triage_session_id_fkey`, taking the whole module down with it.
    ours = [patient_id(i) for i in range(1, 9)]

    async def _wipe() -> None:
        async with SessionLocal() as session:
            await session.execute(delete(QueueEntry).where(QueueEntry.patient_id.in_(ours)))
            await session.execute(
                delete(TriageSession).where(TriageSession.patient_id.in_(ours))
            )
            await session.commit()

    await _wipe()
    yield
    await _wipe()


async def _seed_finalized_triage(*, severity_esi: int, specialty: str) -> object:
    session_id = uuid4()
    result = TriageResult(
        session_id=session_id,
        patient_id=patient_id(1),
        severity_esi=severity_esi,
        triage_colour=colour_for_esi(severity_esi),
        specialty=specialty,
        red_flags=["pattern match: crushing chest pain"] if severity_esi <= 2 else [],
        suggested_labs=[],
        rationale="test fixture",
        citations=[],
        confidence=0.9,
    )
    async with SessionLocal() as session:
        session.add(TriageSession(id=session_id, patient_id=patient_id(1), transcript=[], result=result.model_dump(mode="json")))
        await session.commit()
    return session_id


@pytest.mark.asyncio
async def test_booking_with_triage_session_uses_triaged_severity_not_default(client, auth_headers):
    session_id = await _seed_finalized_triage(severity_esi=2, specialty="cardiology")
    captcha_headers = await _solved_captcha_header(client)

    resp = await client.post(
        "/api/v1/appointments",
        headers={**auth_headers("patient"), **captcha_headers},
        json={
            "patient_id": str(patient_id(1)),
            "specialty": "general_medicine",  # deliberately wrong -- triage should override
            "lat": 13.08, "lng": 80.27,
            "triage_session_id": str(session_id),
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # severity 2 is RED -- pq.enqueue's own emergency-max check must have
    # fired, and the queue entry must show tier 2, not the tier-4 default.
    assert body["queue"]["severity_esi"] == 2
    assert body["queue"]["triage_colour"] == "red"
    assert body["queue"]["emergency"] is True
    assert body["doctor"]["specialty"] == "cardiology"
