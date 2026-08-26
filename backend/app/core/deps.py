"""Auth dependencies: `get_current_user`, `require_role`, `require_self_or_role`
and `require_captcha` -- the frozen interface the whole team imports.

Real JWT verification lands here (CP1 P1.1), replacing the `test-{role}-token`
placeholder the rest of the team was building against; `CurrentUser`'s shape
(`id`, `role`) is unchanged so callers like `app/api/v1/documents.py` and
`backend/tests/conftest.py`'s `auth_headers` fixture keep working once that
fixture is switched to mint real tokens (see docs/DECISIONS.md).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.errors import ApiError
from app.db.models.user import User
from app.db.session import get_db


@dataclass
class CurrentUser:
    id: UUID
    role: str
    email: str | None = None


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError("AUTH_INVALID_CREDENTIALS", "missing bearer token", status_code=401)

    token = authorization.removeprefix("Bearer ").strip()
    claims = security.decode_token(token)

    if claims.get("typ") != "access":
        raise ApiError("AUTH_INVALID_CREDENTIALS", "not an access token", status_code=401)

    if await security.is_denylisted(claims["jti"]):
        raise ApiError("AUTH_TOKEN_EXPIRED", "token has been revoked", status_code=401)

    user = await db.get(User, UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise ApiError("AUTH_INVALID_CREDENTIALS", "user not found or inactive", status_code=401)

    return CurrentUser(id=user.id, role=user.role, email=user.email)


def require_role(*roles: str) -> Callable:
    async def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise ApiError("AUTH_FORBIDDEN", "insufficient role for this action", status_code=403)
        return user

    return _dep


def require_self_or_role(param: str, *roles: str) -> Callable:
    """Allow `roles` unconditionally, or a caller whose own Patient/Doctor
    profile matches the `param` path value (patient reading/writing their own
    record). Never distinguishes "not yours" from "doesn't exist" in the
    response -- both are a bare 403.
    """

    async def _dep(
        request: Request,
        user: CurrentUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> CurrentUser:
        if user.role in roles:
            return user

        raw_value = request.path_params.get(param)
        if raw_value is not None:
            try:
                target_id = UUID(str(raw_value))
            except ValueError:
                target_id = None

            if target_id is not None:
                from app.db.models.patient import Patient
                from app.db.models.scheduling import Doctor

                patient_result = await db.execute(
                    select(Patient.user_id).where(Patient.id == target_id)
                )
                owner_id = patient_result.scalar_one_or_none()
                if owner_id is None:
                    doctor_result = await db.execute(
                        select(Doctor.user_id).where(Doctor.id == target_id)
                    )
                    owner_id = doctor_result.scalar_one_or_none()

                if owner_id is not None and owner_id == user.id:
                    return user

        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)

    return _dep


async def require_captcha(x_captcha_token: str | None = Header(default=None)) -> None:
    from app.core.captcha import verify_captcha_token

    if not x_captcha_token:
        raise ApiError("CAPTCHA_REQUIRED", "X-Captcha-Token header is required", status_code=400)
    await verify_captcha_token(x_captcha_token)


def require_consent(scope: str) -> Callable:
    """Block triage/copilot routes for a patient who hasn't granted (or has
    withdrawn) consent covering `scope`. For Ashwin's triage/copilot routes:
    `Depends(require_consent("triage"))` alongside a `patient_id` path param.
    """

    async def _dep(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> None:
        from app.services.consent import get_active_consent

        raw_patient_id = request.path_params.get("patient_id")
        if raw_patient_id is None:
            raise ApiError("VALIDATION_FAILED", "patient_id path param required", status_code=422)

        patient_id = UUID(str(raw_patient_id))
        consent = await get_active_consent(db, patient_id)
        if consent is None or not consent.get("granular_scopes", {}).get(scope):
            raise ApiError(
                "AUTH_FORBIDDEN",
                f"patient has not consented to '{scope}'",
                status_code=403,
            )

    return _dep
