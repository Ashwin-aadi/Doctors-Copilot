"""Asserts the full API surface from docs/API_CONTRACT.md is live in the OpenAPI
schema (even where the handler still returns NOT_IMPLEMENTED), and that /health
reports every dependency as reachable."""

import pytest

from app.main import app

EXPECTED_PATHS = {
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
    "/api/v1/captcha/challenge",
    "/api/v1/captcha/verify",
    "/api/v1/patients",
    "/api/v1/patients/{patient_id}",
    "/api/v1/patients/{patient_id}/consent",
    "/api/v1/files",
    "/api/v1/files/{file_id}",
    "/api/v1/approvals/lab-order/{lab_order_id}",
    "/api/v1/approvals/prescription/{prescription_id}",
    "/api/v1/audit",
    "/api/v1/notify",
    "/api/v1/notify/{notification_id}/read",
    "/api/v1/exports/{export_type}/{entity_id}.pdf",
    "/api/v1/doctors-profile",
    "/api/v1/doctors-profile/{doctor_id}",
    "/api/v1/triage/session",
    "/api/v1/triage/{session_id}/message",
    "/api/v1/triage/{session_id}/result",
    "/api/v1/chat/patient",
    "/api/v1/copilot/brief",
    "/api/v1/kg/patient/{patient_id}/timeline",
    "/api/v1/kg/patient/{patient_id}/context",
    "/api/v1/visits/{visit_id}",
    "/api/v1/visits/{visit_id}/advance",
    "/api/v1/documents/upload",
    "/api/v1/documents/{document_id}",
    "/api/v1/ml/entities",
    "/api/v1/ml/interactions",
    "/api/v1/ml/labs/flag",
    "/api/v1/ml/summary",
    "/api/v1/ml/medications/suggest",
    "/api/v1/doctors",
    "/api/v1/appointments",
    "/api/v1/appointments/{appointment_id}",
    "/api/v1/appointments/simulate",
    "/api/v1/queue/{clinic_id}",
    "/api/v1/queue/{queue_entry_id}/next",
    "/api/v1/queue/{queue_entry_id}/escalate",
    "/api/v1/lab-orders/recommend",
    "/api/v1/lab-orders/{lab_order_id}",
    "/api/v1/medications/generic",
    "/health",
}


def test_openapi_has_at_least_40_paths():
    schema = app.openapi()
    assert len(schema["paths"]) >= 40, len(schema["paths"])


@pytest.mark.parametrize("path", sorted(EXPECTED_PATHS))
def test_contracted_path_is_registered(path):
    schema = app.openapi()
    assert path in schema["paths"], f"missing from OpenAPI schema: {path}"


async def test_health_endpoint_all_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert all(v != "down" for v in body.values())


async def test_unimplemented_stub_returns_error_envelope(client):
    resp = await client.post("/api/v1/appointments/simulate")
    assert resp.status_code == 501
    body = resp.json()
    assert body["error"]["code"] == "NOT_IMPLEMENTED"
    assert "request_id" in body["error"]
