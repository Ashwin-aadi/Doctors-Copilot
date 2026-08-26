"""Tests for app.core.captcha: challenge generation and single-use, atomic
verification. Needs a reachable Redis -- see docs/DECISIONS.md.
"""

import hashlib

import pytest

from app.core import captcha
from app.core.errors import ApiError


def _solve(salt: str, target: str, maxnumber: int) -> int:
    for n in range(maxnumber):
        if hashlib.sha256(f"{salt}{n}".encode()).hexdigest() == target:
            return n
    raise AssertionError("challenge not solvable within maxnumber")


@pytest.mark.asyncio
async def test_challenge_shape() -> None:
    challenge = await captcha.create_challenge()
    assert challenge["algorithm"] == "SHA-256"
    assert set(challenge) == {"algorithm", "challenge", "salt", "maxnumber"}
    assert challenge["challenge"] == hashlib.sha256(
        f"{challenge['salt']}{_solve(challenge['salt'], challenge['challenge'], challenge['maxnumber'])}".encode()
    ).hexdigest()


@pytest.mark.asyncio
async def test_verify_solution_success_then_replay_fails() -> None:
    challenge = await captcha.create_challenge()
    number = _solve(challenge["salt"], challenge["challenge"], challenge["maxnumber"])

    await captcha.verify_solution(challenge["challenge"], challenge["salt"], number)

    with pytest.raises(ApiError) as exc_info:
        await captcha.verify_solution(challenge["challenge"], challenge["salt"], number)
    assert exc_info.value.code == "CAPTCHA_INVALID"


@pytest.mark.asyncio
async def test_verify_solution_rejects_wrong_number() -> None:
    challenge = await captcha.create_challenge()
    correct = _solve(challenge["salt"], challenge["challenge"], challenge["maxnumber"])
    wrong = correct + 1

    with pytest.raises(ApiError) as exc_info:
        await captcha.verify_solution(challenge["challenge"], challenge["salt"], wrong)
    assert exc_info.value.code == "CAPTCHA_INVALID"


@pytest.mark.asyncio
async def test_verify_solution_rejects_unknown_challenge() -> None:
    with pytest.raises(ApiError) as exc_info:
        await captcha.verify_solution("not-a-real-challenge", "salt", 0)
    assert exc_info.value.code == "CAPTCHA_INVALID"


@pytest.mark.asyncio
async def test_verify_captcha_token_roundtrip() -> None:
    import base64
    import json

    challenge = await captcha.create_challenge()
    number = _solve(challenge["salt"], challenge["challenge"], challenge["maxnumber"])
    token = base64.b64encode(
        json.dumps(
            {"challenge": challenge["challenge"], "salt": challenge["salt"], "number": number}
        ).encode()
    ).decode()
    await captcha.verify_captcha_token(token)


@pytest.mark.asyncio
async def test_verify_captcha_token_rejects_malformed_base64() -> None:
    with pytest.raises(ApiError) as exc_info:
        await captcha.verify_captcha_token("not-valid-base64!!!")
    assert exc_info.value.code == "CAPTCHA_INVALID"
