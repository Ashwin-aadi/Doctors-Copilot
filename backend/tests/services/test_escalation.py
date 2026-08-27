"""Emergency escalation tests. Pack/pure-function tests need no DB;
`test_escalate_from_phc_suggests_transfer_to_dh` needs a reachable Postgres +
Redis (same infra caveat as the rest of `tests/services/`).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from sqlalchemy import delete

from app.db.models.scheduling import QueueEntry
from app.db.session import SessionLocal
from app.services.queueing.escalation import (
    detect_red_flags,
    escalate_with_referral,
    should_escalate,
)
from app.services.queueing.pq import enqueue
from tests.services.conftest import CLINIC_PHC, doctor_id, patient_id

# Resolved from this file, not the working directory: `make test` runs
# pytest with `backend/` as cwd, so a repo-root-relative path never
# resolves. Mirrors how app/rag/triage_rag.py locates its own data dir.
_BACKEND = Path(__file__).resolve().parents[2]
_PACK_PATH = _BACKEND / "app/services/rules/packs/emergency.yaml"

NOW = dt.datetime(2026, 1, 12, 10, tzinfo=dt.UTC)  # 15:30 IST, Monday


def test_pack_has_at_least_35_red_flags_and_mandatory_coverage():
    flags = yaml.safe_load(open(_PACK_PATH, encoding="utf-8"))["red_flags"]
    assert len(flags) >= 35, len(flags)
    blob = " ".join(str(x).lower() for x in flags)
    for term in ["snake", "poison", "partum", "eclamp", "trauma", "neonat", "heat"]:
        assert term in blob, term


def test_detect_red_flags_matches_snakebite_phrase():
    hits = detect_red_flags("patient reports snakebite with bleeding gums")
    assert hits
    assert any(h["category"] == "snakebite" for h in hits)


def test_detect_red_flags_case_insensitive_and_no_match_returns_empty():
    assert detect_red_flags("CHEST PAIN WITH SWEATING")
    assert detect_red_flags("mild cold, runny nose") == []


def test_should_escalate_on_red_severity_even_without_red_flag_text():
    assert should_escalate(2, "") is True
    assert should_escalate(4, "") is False
    assert should_escalate(4, "road traffic accident polytrauma") is True


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
async def test_escalate_with_referral_forces_red_and_moves_to_head():
    from uuid import uuid4

    entry = QueueEntry(
        id=uuid4(), appointment_id=None, patient_id=patient_id(1), doctor_id=doctor_id(1),
        clinic_id=CLINIC_PHC, severity_esi=4, emergency=False, enqueued_at=NOW, status="waiting",
    )
    out = await enqueue(entry, now=NOW)

    escalated = await escalate_with_referral(out.id, "snakebite with bleeding gums", now=NOW)
    assert escalated.emergency is True
    assert escalated.triage_colour == "red"
    assert escalated.position == 1
    # PHC is not emergency-capable in the Chennai fixture -- a snakebite red
    # flag needs at least a CHC, so a transfer suggestion with "108" must
    # appear in reasons.
    assert any("108" in r for r in escalated.reasons)


@pytest.mark.asyncio
async def test_escalate_without_red_flag_still_forces_red_but_no_transfer_needed_text():
    """A plain escalation reason with no matched red-flag phrase still forces
    RED (the existing CP1 contract), but shouldn't fabricate a transfer
    suggestion when nothing in the pack matched.
    """
    from uuid import uuid4

    entry = QueueEntry(
        id=uuid4(), appointment_id=None, patient_id=patient_id(2), doctor_id=doctor_id(1),
        clinic_id=CLINIC_PHC, severity_esi=4, emergency=False, enqueued_at=NOW, status="waiting",
    )
    out = await enqueue(entry, now=NOW)

    escalated = await escalate_with_referral(out.id, "doctor's clinical judgement", now=NOW)
    assert escalated.emergency is True
    # PHC still isn't emergency-capable, so even a judgement call (no pack
    # match) escalated to RED gets the generic CHC-and-above referral floor.
    assert any("108" in r for r in escalated.reasons)
