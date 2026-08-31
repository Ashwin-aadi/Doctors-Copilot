"""Unit tests for app.core.security: password hashing/policy and JWT
issuance/rotation/revocation. Rotation/denylist tests need a reachable Redis
(same as the rest of this suite) -- see docs/DECISIONS.md for this sandbox's
infra caveat.
"""

import uuid

import pytest
from jose import jwt

from app.core import security
from app.core.config import get_settings
from app.core.errors import ApiError


def test_hash_and_verify_password_roundtrip() -> None:
    hashed = security.hash_password("Str0ngPass99")
    assert security.verify_password("Str0ngPass99", hashed)
    assert not security.verify_password("wrong-password", hashed)


def test_verify_password_rejects_garbage_hash() -> None:
    assert not security.verify_password("whatever12", "not-a-bcrypt-hash")


def test_password_policy_rejects_only_an_empty_password() -> None:
    with pytest.raises(ApiError) as exc_info:
        security.validate_password_policy("")
    assert exc_info.value.code == "VALIDATION_FAILED"


@pytest.mark.parametrize(
    "password",
    ["short1a", "1234567890123", "onlylettersnodigits", "password123", "Str0ngPass99"],
    ids=["short", "no-letters", "no-digits", "common", "long-and-mixed"],
)
def test_password_policy_accepts_anything_non_empty(password: str) -> None:
    security.validate_password_policy(password)


def test_access_token_claims() -> None:
    user_id = uuid.uuid4()
    token = security.create_access_token(user_id, "patient")
    settings = get_settings()
    claims = jwt.decode(token, settings.secret_key, algorithms=[security.ALGORITHM])
    assert claims["sub"] == str(user_id)
    assert claims["role"] == "patient"
    assert claims["typ"] == "access"
    assert "jti" in claims
    assert claims["exp"] - claims["iat"] == settings.access_token_minutes * 60


def test_refresh_token_claims() -> None:
    user_id = uuid.uuid4()
    token = security.create_refresh_token(user_id, "doctor")
    claims = security.decode_token(token)
    assert claims["typ"] == "refresh"
    assert "fam" in claims
    settings = get_settings()
    assert claims["exp"] - claims["iat"] == settings.refresh_token_days * 86400


def test_decode_token_rejects_garbage() -> None:
    with pytest.raises(ApiError) as exc_info:
        security.decode_token("not-a-jwt")
    assert exc_info.value.code == "AUTH_TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_issue_rotate_and_reuse_revokes_family() -> None:
    user_id = uuid.uuid4()
    access1, refresh1 = await security.issue_token_pair(user_id, "patient")
    assert security.decode_token(access1)["typ"] == "access"

    access2, refresh2 = await security.rotate_refresh(refresh1)
    assert access2 != access1
    assert refresh2 != refresh1

    # replaying the now-rotated-away refresh1 must fail and revoke refresh2 too
    with pytest.raises(ApiError) as exc_info:
        await security.rotate_refresh(refresh1)
    assert exc_info.value.code == "AUTH_INVALID_CREDENTIALS"

    with pytest.raises(ApiError):
        await security.rotate_refresh(refresh2)


@pytest.mark.asyncio
async def test_revoke_denylists_jti() -> None:
    user_id = uuid.uuid4()
    token = security.create_access_token(user_id, "patient")
    claims = security.decode_token(token)
    assert not await security.is_denylisted(claims["jti"])
    await security.revoke(claims["jti"], ttl=60)
    assert await security.is_denylisted(claims["jti"])
