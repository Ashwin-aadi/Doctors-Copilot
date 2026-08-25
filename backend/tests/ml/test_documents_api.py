"""API tests for POST /documents/upload and GET /documents/{document_id}.

Needs the local infra up (`make up && make migrate && make seed`) for a real
Postgres row and a seeded patient/user to authenticate as. The end-to-end test
runs the worker's job function inline rather than going through a live
`rq worker` process, so it stays deterministic in CI without depending on a
second process being started -- `make worker &` + the documented curl script
is the true queue-to-completion check.
"""

import asyncio
from pathlib import Path
from uuid import uuid4

from app.workers.ocr_worker import process_document

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "ml" / "fixtures"
SEEDED_PATIENT_ID = "00000000-0000-0000-0000-000000000101"


def _cbc_file() -> dict:
    return {"file": ("cbc.pdf", (FIXTURES_DIR / "cbc.pdf").read_bytes(), "application/pdf")}


async def test_upload_requires_auth(client):
    resp = await client.post(
        "/api/v1/documents/upload",
        data={"patient_id": SEEDED_PATIENT_ID},
        files=_cbc_file(),
    )
    assert resp.status_code == 401


async def test_upload_multipart_creates_queued_document(client, auth_headers):
    resp = await client.post(
        "/api/v1/documents/upload",
        headers=auth_headers("doctor"),
        data={"patient_id": SEEDED_PATIENT_ID},
        files=_cbc_file(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["patient_id"] == SEEDED_PATIENT_ID
    assert body["labs"] == []


async def test_get_unknown_document_404s(client, auth_headers):
    resp = await client.get(f"/api/v1/documents/{uuid4()}", headers=auth_headers("doctor"))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_get_requires_auth(client):
    resp = await client.get(f"/api/v1/documents/{uuid4()}")
    assert resp.status_code == 401


async def test_upload_then_process_yields_structured_labs(client, auth_headers):
    resp = await client.post(
        "/api/v1/documents/upload",
        headers=auth_headers("doctor"),
        data={"patient_id": SEEDED_PATIENT_ID},
        files=_cbc_file(),
    )
    document_id = resp.json()["id"]

    await asyncio.to_thread(process_document, document_id)

    resp = await client.get(f"/api/v1/documents/{document_id}", headers=auth_headers("doctor"))
    body = resp.json()
    assert body["status"] == "done"
    assert body["engine"]
    assert len(body["labs"]) >= 5
    assert body["labs"][0]["confidence"] > 0
