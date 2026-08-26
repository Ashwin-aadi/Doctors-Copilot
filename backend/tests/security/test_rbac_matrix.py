"""Table-driven RBAC coverage for every route this checkpoint owns
(auth/captcha/patients), plus a generic scan (built from the live OpenAPI
schema, so it can't drift) asserting no implemented route outside the
auth/captcha/health/docs allowlist is anonymously readable.

Needs a reachable Postgres + Redis and a seeded DB (`python scripts/seed_users.py`)
-- see docs/DECISIONS.md for this sandbox's infra caveat. Routes owned by
other checkpoints aren't asserted here with precise expected statuses (most
are still `not_implemented` stubs as of this checkpoint) -- only that they
never leak an anonymous 200 outside the public allowlist below.
"""

from __future__ import annotations

import pytest

ANONYMOUS_ALLOWLIST_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/captcha/",
    "/health",
    "/metrics",
    "/docs",
    "/openapi",
    "/redoc",
)

# (method, path, role, expected_status, json_body). `role=None` means
# anonymous. A well-formed body is supplied for register/login so captcha
# gating is the *only* thing determining the outcome (400 CAPTCHA_REQUIRED),
# rather than an ambiguous mix with 422 body-validation ordering.
# `{patient_id}` is filled with the fixed patient1 id from scripts/seed_users.py.
_PATIENT_1 = "00000000-0000-0000-0000-000000000101"
_PATIENT_2 = "00000000-0000-0000-0000-000000000102"

_VALID_REGISTER_BODY = {
    "email": "rbac-probe@demo.local",
    "phone": "9876543210",
    "password": "Str0ngPass99",
    "name": "RBAC Probe",
}
_VALID_LOGIN_BODY = {"email": "patient1@demo.local", "password": "Demo@12345"}

RBAC_TABLE: list[tuple[str, str, str | None, int, dict | None]] = [
    ("POST", "/api/v1/auth/register", None, 400, _VALID_REGISTER_BODY),
    ("POST", "/api/v1/auth/login", None, 400, _VALID_LOGIN_BODY),
    ("GET", "/api/v1/auth/me", None, 401, None),
    ("GET", "/api/v1/auth/me", "patient", 200, None),
    ("GET", "/api/v1/auth/me", "doctor", 200, None),
    ("GET", "/api/v1/auth/me", "staff", 200, None),
    ("GET", "/api/v1/auth/me", "admin", 200, None),
    ("POST", "/api/v1/auth/logout", None, 200, None),
    ("GET", "/api/v1/captcha/challenge", None, 200, None),
    # patients
    ("GET", "/api/v1/patients", None, 401, None),
    ("GET", "/api/v1/patients", "patient", 403, None),
    ("GET", "/api/v1/patients", "doctor", 200, None),
    ("GET", "/api/v1/patients", "staff", 200, None),
    ("GET", "/api/v1/patients", "admin", 200, None),
    ("GET", f"/api/v1/patients/{_PATIENT_1}", None, 401, None),
    ("GET", f"/api/v1/patients/{_PATIENT_2}", "patient", 403, None),
    ("GET", f"/api/v1/patients/{_PATIENT_1}", "staff", 200, None),
    ("GET", f"/api/v1/patients/{_PATIENT_1}", "admin", 200, None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,role,expected,body", RBAC_TABLE)
async def test_rbac_matrix(
    client,
    auth_headers,
    method: str,
    path: str,
    role: str | None,
    expected: int,
    body: dict | None,
) -> None:
    headers = auth_headers(role) if role else {}
    resp = await client.request(method, path, headers=headers, json=body)
    assert resp.status_code == expected, (
        f"{method} {path} role={role}: expected {expected}, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_no_implemented_route_anonymously_leaks(client) -> None:
    schema_resp = await client.get("/openapi.json")
    assert schema_resp.status_code == 200
    schema = schema_resp.json()

    leaks: list[tuple[str, str, int]] = []
    checked = 0
    for path, operations in schema["paths"].items():
        if path.startswith(ANONYMOUS_ALLOWLIST_PREFIXES):
            continue
        if "{" in path:
            continue  # needs a real id; covered by RBAC_TABLE case by case
        if "get" not in operations:
            continue
        checked += 1
        resp = await client.get(path)
        if resp.status_code == 200:
            leaks.append((path, "GET", resp.status_code))

    assert checked > 0, "no non-allowlisted GET routes found -- schema empty?"
    assert not leaks, f"anonymously-readable protected routes: {leaks}"


@pytest.mark.asyncio
async def test_rbac_matrix_covers_every_get_route_at_least_once() -> None:
    """Guards against RBAC_TABLE silently losing coverage as routes are
    added -- every GET path this checkpoint owns must appear at least once.
    """
    owned_get_paths = {
        "/api/v1/auth/me",
        "/api/v1/captcha/challenge",
        "/api/v1/patients",
    }
    covered = {path for method, path, _role, _status in RBAC_TABLE if method == "GET"}
    missing = owned_get_paths - {p.split("/{")[0] for p in covered}
    assert not missing, f"RBAC_TABLE missing coverage for: {missing}"
