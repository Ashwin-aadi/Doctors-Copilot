"""Password hashing and JWT access/refresh token issuance, rotation and
revocation.

Refresh tokens carry a `fam` (family) claim shared by every token descended
from one login. Rotation moves the presented jti onto the Redis denylist and
mints a new jti in the same family; if a jti that is *already* denylisted is
presented again (a stolen, already-rotated-away refresh token being replayed),
the entire family is denylisted -- one reuse revokes every token in that
lineage, not just the one presented.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.redis_client import redis_client

ALGORITHM = "HS256"
_BCRYPT_ROUNDS = 12

_COMMON_PASSWORDS_PATH = Path(__file__).parent / "data" / "common_passwords.txt"

_DENYLIST_PREFIX = "auth:denylist:"
_REFRESH_ACTIVE_PREFIX = "auth:refresh:active:"
_REFRESH_FAMILY_PREFIX = "auth:refresh:family:"


def _load_common_passwords() -> frozenset[str]:
    if not _COMMON_PASSWORDS_PATH.exists():
        return frozenset()
    return frozenset(
        line.strip().lower()
        for line in _COMMON_PASSWORDS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


COMMON_PASSWORDS = _load_common_passwords()


def _bcrypt_bytes(password: str) -> bytes:
    # bcrypt only examines the first 72 bytes of the input; truncate ourselves
    # so a very long password doesn't raise instead of just losing entropy
    # past that point (bcrypt>=4.1 raises ValueError on >72 bytes rather than
    # silently truncating, unlike passlib's older bcrypt wrapper).
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_bytes(password), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode(
        "ascii"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_bytes(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def validate_password_policy(password: str) -> None:
    """>=10 chars, >=1 letter, >=1 digit, not in the common-password list."""
    if len(password) < 10:
        raise ApiError(
            "VALIDATION_FAILED", "password must be at least 10 characters", status_code=422
        )
    if not any(c.isalpha() for c in password):
        raise ApiError(
            "VALIDATION_FAILED", "password must contain at least one letter", status_code=422
        )
    if not any(c.isdigit() for c in password):
        raise ApiError(
            "VALIDATION_FAILED", "password must contain at least one digit", status_code=422
        )
    if password.lower() in COMMON_PASSWORDS:
        raise ApiError(
            "VALIDATION_FAILED", "password is too common, choose another", status_code=422
        )


def _encode(payload: dict) -> str:
    settings = get_settings()
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ApiError(
            "AUTH_TOKEN_EXPIRED", "invalid or expired token", status_code=401
        ) from exc


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    settings = get_settings()
    now = int(time.time())
    return _encode(
        {
            "sub": str(user_id),
            "role": role,
            "typ": "access",
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": now + settings.access_token_minutes * 60,
        }
    )


def create_refresh_token(user_id: uuid.UUID, role: str, family: str | None = None) -> str:
    settings = get_settings()
    now = int(time.time())
    return _encode(
        {
            "sub": str(user_id),
            "role": role,
            "typ": "refresh",
            "jti": uuid.uuid4().hex,
            "fam": family or uuid.uuid4().hex,
            "iat": now,
            "exp": now + settings.refresh_token_days * 86400,
        }
    )


async def _register_refresh(claims: dict) -> None:
    ttl = max(int(claims["exp"] - time.time()), 1)
    jti, fam, sub = claims["jti"], claims["fam"], claims["sub"]
    await redis_client.set(f"{_REFRESH_ACTIVE_PREFIX}{jti}", f"{sub}:{fam}", ex=ttl)
    await redis_client.sadd(f"{_REFRESH_FAMILY_PREFIX}{fam}", jti)
    await redis_client.expire(f"{_REFRESH_FAMILY_PREFIX}{fam}", ttl)


async def issue_token_pair(
    user_id: uuid.UUID, role: str, family: str | None = None
) -> tuple[str, str]:
    access = create_access_token(user_id, role)
    refresh = create_refresh_token(user_id, role, family)
    await _register_refresh(decode_token(refresh))
    return access, refresh


async def revoke(jti: str, ttl: int) -> None:
    if ttl > 0:
        await redis_client.set(f"{_DENYLIST_PREFIX}{jti}", "1", ex=ttl)
    await redis_client.delete(f"{_REFRESH_ACTIVE_PREFIX}{jti}")


async def is_denylisted(jti: str) -> bool:
    return bool(await redis_client.exists(f"{_DENYLIST_PREFIX}{jti}"))


def _refresh_ttl_seconds() -> int:
    return get_settings().refresh_token_days * 86400


async def _revoke_family(fam: str) -> None:
    key = f"{_REFRESH_FAMILY_PREFIX}{fam}"
    members = await redis_client.smembers(key)
    ttl = _refresh_ttl_seconds()
    for jti in members:
        await revoke(jti, ttl)
    await redis_client.delete(key)


async def rotate_refresh(token: str) -> tuple[str, str]:
    claims = decode_token(token)
    if claims.get("typ") != "refresh":
        raise ApiError("AUTH_INVALID_CREDENTIALS", "not a refresh token", status_code=401)

    jti = claims["jti"]
    fam = claims["fam"]

    if await is_denylisted(jti):
        await _revoke_family(fam)
        raise ApiError(
            "AUTH_INVALID_CREDENTIALS", "refresh token reuse detected", status_code=401
        )

    active = await redis_client.get(f"{_REFRESH_ACTIVE_PREFIX}{jti}")
    if active is None:
        raise ApiError(
            "AUTH_INVALID_CREDENTIALS", "refresh token is not active", status_code=401
        )

    remaining = max(int(claims["exp"] - time.time()), 1)
    await revoke(jti, remaining)

    user_id = uuid.UUID(claims["sub"])
    role = claims["role"]
    access = create_access_token(user_id, role)
    refresh = create_refresh_token(user_id, role, family=fam)
    await _register_refresh(decode_token(refresh))
    return access, refresh
