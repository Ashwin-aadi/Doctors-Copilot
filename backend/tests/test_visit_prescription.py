"""Prescription draft endpoints on the visit.

The doctor's pad has to survive a page reload, which means the draft is
server-side from the first save. These walk that: nothing there to begin with,
a draft written, read back, replaced, and -- once signed -- refused.
"""

from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.db.models.clinical import Prescription

VISIT_ID = UUID("00000000-0000-0000-0000-000000000301")


@pytest_asyncio.fixture
async def clean_prescriptions(db):
    """The seeded visit is shared with every other test and with the running
    dev database, so anything written here is removed again either way.
    """

    async def _clear() -> None:
        await db.execute(delete(Prescription).where(Prescription.visit_id == VISIT_ID))
        await db.commit()

    await _clear()
    yield db
    await _clear()


@pytest.mark.asyncio
async def test_undrafted_visit_reports_not_found(client, auth_headers, clean_prescriptions):
    res = await client.get(
        f"/api/v1/visits/{VISIT_ID}/prescription", headers=auth_headers("doctor")
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_save_creates_then_replaces_the_draft(client, auth_headers, clean_prescriptions):
    headers = auth_headers("doctor")

    created = await client.put(
        f"/api/v1/visits/{VISIT_ID}/prescription",
        headers=headers,
        json={
            "items": [
                {
                    "name": "Paracetamol 500mg",
                    "dose": "1 tab",
                    "frequency": "TDS",
                    "duration": "3 days",
                }
            ]
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["locked"] is False
    assert [item["name"] for item in body["items"]] == ["Paracetamol 500mg"]

    read_back = await client.get(f"/api/v1/visits/{VISIT_ID}/prescription", headers=headers)
    assert read_back.json()["id"] == body["id"]

    # Removing a medicine is a replacement, not an append -- a doctor who
    # takes a drug off the pad must not find it still prescribed.
    replaced = await client.put(
        f"/api/v1/visits/{VISIT_ID}/prescription",
        headers=headers,
        json={"items": [{"name": "ORS sachets", "frequency": "after each loose stool"}]},
    )
    assert [item["name"] for item in replaced.json()["items"]] == ["ORS sachets"]
    assert replaced.json()["id"] == body["id"]


@pytest.mark.asyncio
async def test_patient_may_not_write_a_prescription(client, auth_headers, clean_prescriptions):
    res = await client.put(
        f"/api/v1/visits/{VISIT_ID}/prescription",
        headers=auth_headers("patient"),
        json={"items": [{"name": "Amoxicillin 500mg"}]},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_signed_prescription_cannot_be_edited(client, auth_headers, clean_prescriptions):
    db = clean_prescriptions
    headers = auth_headers("doctor")

    await client.put(
        f"/api/v1/visits/{VISIT_ID}/prescription",
        headers=headers,
        json={"items": [{"name": "Paracetamol 500mg"}]},
    )
    record = (
        await db.execute(select(Prescription).where(Prescription.visit_id == VISIT_ID))
    ).scalar_one()
    record.locked = True
    await db.commit()

    res = await client.put(
        f"/api/v1/visits/{VISIT_ID}/prescription",
        headers=headers,
        json={"items": [{"name": "Ibuprofen 400mg"}]},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "LOCKED"
