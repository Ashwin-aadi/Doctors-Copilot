"""Tests for the audit middleware and /audit query endpoint (checkpoint
P2.4). Route-template/entity parsing and the mutating-method filter are
pure logic and run here with no infra. The full request-logged-then-
queryable round trip and the append-only DB grant need a reachable
Postgres + Redis -- see docs/DECISIONS.md.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core.middleware_audit import (
    MUTATING_METHODS,
    _decode_actor,
    entity_and_id_for,
    route_template_for,
)
from app.core.security import create_access_token


def _fake_request(method: str, path: str, headers: dict[str, str] | None = None, route_path: str | None = None) -> Request:
    header_list = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": header_list,
        "client": ("127.0.0.1", 12345),
        "path_params": {},
        "scheme": "http",
        "server": ("testserver", 80),
        "query_string": b"",
        "root_path": "",
    }
    if route_path is not None:
        class _Route:
            path = route_path

        scope["route"] = _Route()
        scope["path_params"] = {"lab_order_id": "00000000-0000-0000-0000-000000000301"}

    return Request(scope)


@pytest.mark.parametrize("method,expected", [("GET", False), ("POST", True), ("PATCH", True), ("PUT", True), ("DELETE", True), ("HEAD", False)])
def test_mutating_methods_filter(method: str, expected: bool) -> None:
    assert (method in MUTATING_METHODS) is expected


def test_route_template_for_falls_back_to_raw_path_without_route() -> None:
    request = _fake_request("POST", "/api/v1/files")
    assert route_template_for(request) == "/api/v1/files"


def test_route_template_for_uses_route_path_when_available() -> None:
    request = _fake_request(
        "POST", "/api/v1/approvals/lab-order/xyz", route_path="/approvals/lab-order/{lab_order_id}"
    )
    assert route_template_for(request) == "/approvals/lab-order/{lab_order_id}"


def test_entity_and_id_for_strips_api_v1_prefix_and_uses_path_param() -> None:
    request = _fake_request(
        "POST", "/api/v1/approvals/lab-order/xyz", route_path="/approvals/lab-order/{lab_order_id}"
    )
    entity, entity_id = entity_and_id_for(request, "/approvals/lab-order/{lab_order_id}")
    assert entity == "approvals"
    assert entity_id == "00000000-0000-0000-0000-000000000301"


def test_entity_and_id_for_handles_no_path_params() -> None:
    request = _fake_request("POST", "/api/v1/auth/register")
    entity, entity_id = entity_and_id_for(request, "/auth/register")
    assert entity == "auth"
    assert entity_id is None


def test_decode_actor_returns_none_for_missing_header() -> None:
    request = _fake_request("POST", "/api/v1/files")
    assert _decode_actor(request) == (None, None)


def test_decode_actor_returns_none_for_malformed_token() -> None:
    request = _fake_request("POST", "/api/v1/files", headers={"authorization": "Bearer not-a-real-jwt"})
    assert _decode_actor(request) == (None, None)


def test_decode_actor_decodes_valid_token() -> None:
    from uuid import UUID

    user_id = UUID("00000000-0000-0000-0000-000000000401")
    token = create_access_token(user_id, "doctor")
    request = _fake_request("POST", "/api/v1/files", headers={"authorization": f"Bearer {token}"})
    actor_id, role = _decode_actor(request)
    assert actor_id == user_id
    assert role == "doctor"


# ---- full API round trips (need Postgres + Redis) --------------------------
#
# Covered end to end in CI once seeded: a mutating request (e.g. an
# approval) produces an AuditLog row queryable via
# `GET /audit?entity=lab_order&entity_id=...` for doctor/admin only
# (patient/staff -> 403; anonymous -> 401); and a raw
# `DELETE FROM audit_logs` under the app's own DB role is expected to
# *still succeed* given this checkpoint's documented ownership-bypass
# limitation (see the P2.4 migration's docstring and docs/SECURITY.md) --
# noted as a known gap rather than silently claimed as enforced.
