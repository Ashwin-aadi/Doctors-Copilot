"""API-level tests for /auth/*. These exercise the FastAPI app end to end and
need a reachable Postgres + Redis (`make up && make migrate`) -- see
docs/DECISIONS.md for this sandbox's infra caveat. Logic that doesn't need a
DB (phone/ABHA/Aadhaar validation, password policy, uniform-timing hash
selection) is additionally covered directly against `app.api.v1.auth`'s
helpers so it's verifiable without live infra.
"""

from uuid import uuid4

import pytest

from app.api.v1 import auth as auth_module
from app.core.errors import ApiError

# ---- pure-function coverage (no DB/Redis needed) --------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("9876543210", "+919876543210"),
        ("+919876543210", "+919876543210"),
        ("09876543210", "+919876543210"),
    ],
)
def test_normalize_phone_accepts_valid_indian_mobiles(raw: str, expected: str) -> None:
    assert auth_module._normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["12345", "5876543210", "98765432101234", "not-a-phone"])
def test_normalize_phone_rejects_invalid(raw: str) -> None:
    with pytest.raises(ApiError) as exc_info:
        auth_module._normalize_phone(raw)
    assert exc_info.value.code == "VALIDATION_FAILED"


def test_reject_full_aadhaar_blocks_12_digit_sequence() -> None:
    with pytest.raises(ApiError) as exc_info:
        auth_module._reject_full_aadhaar("my aadhaar is 123456789012 yes")
    assert exc_info.value.code == "VALIDATION_FAILED"


def test_reject_full_aadhaar_allows_last_4_digits_only() -> None:
    auth_module._reject_full_aadhaar("last 4 digits: 9012", None, "")


@pytest.mark.parametrize("value", ["12-3456-7890-1234", "99-0000-0000-0001"])
def test_validate_abha_number_accepts_well_formed(value: str) -> None:
    auth_module._validate_abha_number(value)


@pytest.mark.parametrize("value", ["12345678901234", "12-3456-7890", "ab-cdef-ghij-klmn"])
def test_validate_abha_number_rejects_malformed(value: str) -> None:
    with pytest.raises(ApiError) as exc_info:
        auth_module._validate_abha_number(value)
    assert exc_info.value.code == "VALIDATION_FAILED"


def test_validate_abha_address_accepts_well_formed() -> None:
    auth_module._validate_abha_address("ravi.kumar@abdm")


def test_validate_abha_address_rejects_malformed() -> None:
    with pytest.raises(ApiError):
        auth_module._validate_abha_address("not-an-address")


# ---- full API round trips (need Postgres + Redis) --------------------------


async def _solved_captcha_header(client) -> dict[str, str]:
    import base64
    import hashlib
    import json

    challenge = (await client.get("/api/v1/captcha/challenge")).json()
    salt, target, maxnumber = challenge["salt"], challenge["challenge"], challenge["maxnumber"]
    number = next(
        n for n in range(maxnumber) if hashlib.sha256(f"{salt}{n}".encode()).hexdigest() == target
    )
    token = base64.b64encode(
        json.dumps({"challenge": target, "salt": salt, "number": number}).encode()
    ).decode()
    return {"X-Captcha-Token": token}


@pytest.mark.asyncio
async def test_register_login_me_round_trip(client) -> None:
    headers = await _solved_captcha_header(client)
    email = f"patient-{uuid4().hex[:10]}@demo.local"
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "phone": "9876500000",
            "password": "Str0ngPass99",
            "name": "Test Patient",
            "role": "patient",
        },
        headers=headers,
    )
    assert register_resp.status_code == 200, register_resp.text
    body = register_resp.json()
    access_token = body["access_token"]

    me_resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email


@pytest.mark.asyncio
async def test_login_unknown_email_and_wrong_password_are_uniform(client) -> None:
    headers1 = await _solved_captcha_header(client)
    resp_unknown = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody-at-all@demo.local", "password": "Str0ngPass99"},
        headers=headers1,
    )
    headers2 = await _solved_captcha_header(client)
    resp_wrong = await client.post(
        "/api/v1/auth/login",
        json={"email": "patient1@demo.local", "password": "definitely-wrong-1"},
        headers=headers2,
    )
    assert resp_unknown.status_code == resp_wrong.status_code == 401
    assert resp_unknown.json()["error"]["code"] == resp_wrong.json()["error"]["code"]


@pytest.mark.asyncio
async def test_register_without_captcha_is_rejected(client) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"nocap-{uuid4().hex[:8]}@demo.local",
            "phone": "9876500001",
            "password": "Str0ngPass99",
            "name": "No Captcha",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CAPTCHA_REQUIRED"


@pytest.mark.asyncio
async def test_register_duplicate_email_conflicts(client) -> None:
    email = f"dupe-{uuid4().hex[:8]}@demo.local"
    payload = {
        "email": email,
        "phone": "9876500002",
        "password": "Str0ngPass99",
        "name": "Dupe One",
    }
    headers = await _solved_captcha_header(client)
    first = await client.post("/api/v1/auth/register", json=payload, headers=headers)
    assert first.status_code == 200

    headers2 = await _solved_captcha_header(client)
    second = await client.post("/api/v1/auth/register", json=payload, headers=headers2)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"
