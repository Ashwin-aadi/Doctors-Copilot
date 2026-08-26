"""Self-hosted proof-of-work captcha (ALTCHA-style) -- no third-party vendor
or API key. See docs/CAPTCHA.md for the full protocol, payload shapes and a
copy-paste JS solver.

Challenge: server picks a random `salt` and a random `number` in
`[0, CAPTCHA_DIFFICULTY)`, computes `challenge = sha256(salt + str(number))`,
and stores `challenge -> salt` in Redis with a TTL. The `number` itself is
never sent to the client.

Solve (client): brute-force `n` from 0 until `sha256(salt + str(n)) ==
challenge`.

Verify: client sends base64(JSON({challenge, salt, number})) as
`X-Captcha-Token`. The server re-derives the hash and atomically pops the
Redis entry (`GETDEL`) so a second verify of the same challenge always 400s,
even under a concurrent replay -- single-use is enforced by the atomicity of
the delete, not by a separate `used` flag.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.redis_client import redis_client

ALGORITHM_NAME = "SHA-256"
_KEY_PREFIX = "captcha:"


def _hash(salt: str, number: int) -> str:
    return hashlib.sha256(f"{salt}{number}".encode()).hexdigest()


async def create_challenge() -> dict:
    settings = get_settings()
    salt = os.urandom(16).hex()
    number = int.from_bytes(os.urandom(4), "big") % settings.captcha_difficulty
    challenge = _hash(salt, number)

    await redis_client.set(
        f"{_KEY_PREFIX}{challenge}", salt, ex=settings.captcha_ttl_seconds
    )

    return {
        "algorithm": ALGORITHM_NAME,
        "challenge": challenge,
        "salt": salt,
        "maxnumber": settings.captcha_difficulty,
    }


async def verify_solution(challenge: str, salt: str, number: int) -> None:
    stored_salt = await redis_client.getdel(f"{_KEY_PREFIX}{challenge}")
    if stored_salt is None:
        raise ApiError(
            "CAPTCHA_INVALID",
            "captcha challenge expired, unknown, or already used",
            status_code=400,
        )
    if stored_salt != salt or _hash(salt, number) != challenge:
        raise ApiError("CAPTCHA_INVALID", "captcha solution is incorrect", status_code=400)


async def verify_captcha_token(token: str) -> None:
    try:
        raw = base64.b64decode(token, validate=True)
        payload = json.loads(raw)
        challenge = str(payload["challenge"])
        salt = str(payload["salt"])
        number = int(payload["number"])
    except (binascii.Error, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ApiError("CAPTCHA_INVALID", "malformed captcha token", status_code=400) from exc

    await verify_solution(challenge, salt, number)
