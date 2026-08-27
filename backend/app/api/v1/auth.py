"""Authentication and captcha endpoints.

Request/response bodies are defined locally in this file rather than reused
from `app/schemas/auth.py` (Ashwin's, not touched here -- same pattern
`app/api/v1/documents.py` already uses for its own local `DocumentUploadIn`):
the spec's register/login/me payloads (phone, name, ABHA fields, `user:{...}`
nesting) don't match the existing stub schemas, and `app/schemas/` is off
limits per the ownership rules. See docs/DECISIONS.md.
"""

import re
import time
import uuid
from uuid import UUID

import phonenumbers
from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.captcha import create_challenge, verify_captcha_token
from app.core.config import get_settings
from app.core.deps import CurrentUser, get_current_user, require_captcha
from app.core.errors import ApiError
from app.core.ratelimit import (
    clear_login_failures,
    is_login_locked,
    limiter,
    login_lock_retry_after,
    record_login_failure,
)
from app.db.models.patient import Patient
from app.db.models.scheduling import Doctor
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(tags=["auth"])

_AADHAAR_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")
_ABHA_NUMBER_RE = re.compile(r"^\d{2}-\d{4}-\d{4}-\d{4}$")
_ABHA_ADDRESS_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+$")

# Uniform-timing target: a real bcrypt hash checked on every login attempt for
# an email that doesn't exist, so an unknown-email 401 costs the same wall
# clock time as a wrong-password 401 (no user-enumeration timing signal).
_DUMMY_PASSWORD_HASH = security.hash_password("dummy-constant-time-comparison-target-9")


class RegisterRequest(BaseModel):
    email: EmailStr
    phone: str
    password: str
    name: str
    role: str = "patient"
    abha_number: str | None = None
    abha_address: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class UserProfile(BaseModel):
    id: UUID
    email: str
    role: str
    name: str | None = None
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfile


def _normalize_phone(raw: str) -> str:
    try:
        parsed = phonenumbers.parse(raw, "IN")
    except phonenumbers.NumberParseException as exc:
        raise ApiError("VALIDATION_FAILED", "invalid mobile number", status_code=422) from exc

    national = str(parsed.national_number)
    if (
        parsed.country_code != 91
        or not phonenumbers.is_valid_number(parsed)
        or len(national) != 10
        or national[0] not in "6789"
    ):
        raise ApiError(
            "VALIDATION_FAILED",
            "phone must be a valid Indian mobile number (10 digits, starting 6-9)",
            status_code=422,
        )
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def _reject_full_aadhaar(*values: str | None) -> None:
    for value in values:
        if value and _AADHAAR_RE.search(value):
            raise ApiError(
                "VALIDATION_FAILED",
                "a full Aadhaar number must never be submitted; only the last 4 digits "
                "may be stored, and only via the patient profile",
                status_code=422,
            )


def _validate_abha_number(value: str) -> None:
    if not _ABHA_NUMBER_RE.match(value):
        raise ApiError(
            "VALIDATION_FAILED", "abha_number must look like xx-xxxx-xxxx-xxxx", status_code=422
        )


def _validate_abha_address(value: str) -> None:
    if not _ABHA_ADDRESS_RE.match(value):
        raise ApiError(
            "VALIDATION_FAILED", "abha_address must look like name@abdm", status_code=422
        )


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        "refresh_token",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.refresh_token_days * 86400,
        path="/",
    )


async def _resolve_display_name(db: AsyncSession, user: User) -> str | None:
    if user.role == "patient":
        result = await db.execute(select(Patient.name).where(Patient.user_id == user.id))
        return result.scalar_one_or_none()
    if user.role == "doctor":
        result = await db.execute(select(Doctor.name).where(Doctor.user_id == user.id))
        return result.scalar_one_or_none()
    return None


async def _token_response(db: AsyncSession, user: User, access: str, refresh: str) -> TokenResponse:
    claims = security.decode_token(access)
    name = await _resolve_display_name(db, user)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=claims["exp"] - claims["iat"],
        user=UserProfile(id=user.id, email=user.email, role=user.role, name=name, is_active=user.is_active),
    )


@router.post("/auth/register", dependencies=[Depends(require_captcha)])
@limiter.limit("3/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    response: Response,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    _reject_full_aadhaar(body.name, body.abha_number, body.abha_address, body.phone)

    email = body.email.lower()
    phone = _normalize_phone(body.phone)

    if body.abha_number:
        _validate_abha_number(body.abha_number)
    if body.abha_address:
        _validate_abha_address(body.abha_address)

    security.validate_password_policy(body.password)

    role = body.role or "patient"
    if role != "patient":
        is_admin = False
        if authorization and authorization.startswith("Bearer "):
            try:
                caller = await get_current_user(authorization=authorization, db=db)
                is_admin = caller.role == "admin"
            except ApiError:
                is_admin = False
        if not is_admin:
            raise ApiError(
                "AUTH_FORBIDDEN",
                "only patients may self-register; other roles require an admin",
                status_code=403,
            )

    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise ApiError("CONFLICT", "an account with this email already exists", status_code=409)

    user = User(
        email=email,
        phone=phone,
        password_hash=security.hash_password(body.password),
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    if role == "patient":
        db.add(Patient(user_id=user.id, name=body.name, abha_id=body.abha_number))

    await db.commit()
    await db.refresh(user)

    access, refresh = await security.issue_token_pair(
        user.id,
        user.role,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, refresh)
    return await _token_response(db, user, access, refresh)


def _rate_limited_response(request: Request, retry_after: int, message: str) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": message,
                "request_id": request_id,
                "details": {},
            }
        },
    )
    response.headers["Retry-After"] = str(retry_after)
    return response


@router.post("/auth/login", dependencies=[Depends(require_captcha)], response_model=None)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse | JSONResponse:
    email = body.email.lower()

    # Progressive lockout: 5 consecutive failures locks the *account* for 15
    # minutes, independent of the 5/min/IP slowapi limit above -- this one
    # is keyed by email so it survives an attacker rotating source IPs.
    if await is_login_locked(email):
        retry_after = await login_lock_retry_after(email)
        return _rate_limited_response(
            request, retry_after, "account temporarily locked after repeated failed logins"
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_ok = security.verify_password(body.password, password_hash)

    if user is None or not password_ok or not user.is_active:
        await record_login_failure(email)
        raise ApiError(
            "AUTH_INVALID_CREDENTIALS", "incorrect email or password", status_code=401
        )

    await clear_login_failures(email)
    access, refresh = await security.issue_token_pair(
        user.id,
        user.role,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, refresh)
    return await _token_response(db, user, access, refresh)


@router.post("/auth/refresh")
async def refresh_endpoint(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    token = request.cookies.get("refresh_token")
    if not token:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        token = (payload or {}).get("refresh_token")

    if not token:
        raise ApiError("AUTH_INVALID_CREDENTIALS", "refresh token required", status_code=401)

    access, new_refresh = await security.rotate_refresh(
        token,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    claims = security.decode_token(access)
    user = await db.get(User, UUID(claims["sub"]))
    if user is None:
        raise ApiError("AUTH_INVALID_CREDENTIALS", "user not found", status_code=401)

    _set_refresh_cookie(response, new_refresh)
    return await _token_response(db, user, access, new_refresh)


@router.post("/auth/logout")
async def logout(
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        try:
            claims = security.decode_token(token)
            remaining = max(int(claims["exp"] - time.time()), 1)
            await security.revoke(claims["jti"], remaining)
        except ApiError:
            pass

    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            claims = security.decode_token(refresh_token)
            remaining = max(int(claims["exp"] - time.time()), 1)
            await security.revoke(claims["jti"], remaining)
        except ApiError:
            pass

    response.delete_cookie("refresh_token", path="/")
    return {"status": "ok"}


@router.get("/auth/me")
async def me(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, current_user.id)
    if user is None:
        raise ApiError("NOT_FOUND", "user not found", status_code=404)

    profile: dict = {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "name": await _resolve_display_name(db, user),
    }

    if user.role == "patient":
        result = await db.execute(select(Patient).where(Patient.user_id == user.id))
        patient = result.scalar_one_or_none()
        if patient is not None:
            profile["patient"] = {
                "id": patient.id,
                "name": patient.name,
                "dob": patient.dob,
                "sex": patient.sex,
                "state": patient.state,
                "pin_code": patient.pin_code,
                "abha_id": patient.abha_id,
            }
    elif user.role == "doctor":
        result = await db.execute(select(Doctor).where(Doctor.user_id == user.id))
        doctor = result.scalar_one_or_none()
        if doctor is not None:
            profile["doctor"] = {
                "id": doctor.id,
                "name": doctor.name,
                "specialties": doctor.specialties,
                "qualifications": doctor.qualifications,
                "nmc_reg_no": doctor.nmc_reg_no,
                "clinic_id": doctor.clinic_id,
            }

    return profile


@router.get("/captcha/challenge")
async def captcha_challenge() -> dict:
    return await create_challenge()


@router.post("/captcha/verify")
async def captcha_verify(x_captcha_token: str | None = Header(default=None)) -> dict:
    if not x_captcha_token:
        raise ApiError("CAPTCHA_REQUIRED", "X-Captcha-Token header is required", status_code=400)
    await verify_captcha_token(x_captcha_token)
    return {"status": "ok"}


# ---------------------------------------------------------- P3.5 sessions --


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/auth/password/forgot")
async def forgot_password(
    body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Always returns 200, even for an unknown email -- never lets a caller
    learn whether an account exists from this endpoint's response."""
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if user is not None and user.is_active:
        token = security.create_reset_token(user.id)
        reset_link = f"{get_settings().frontend_url}/reset-password?token={token}"
        try:
            from app.services.notify import send_email

            await send_email(
                user.email,
                "Doctor's Copilot: reset your password",
                f"Use this link within 30 minutes to reset your password: {reset_link}",
            )
        except Exception:
            pass  # best-effort; never let delivery failure leak account existence either
    return {"status": "ok"}


@router.post("/auth/password/reset")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict:
    user_id = await security.consume_reset_token(body.token)
    security.validate_password_policy(body.new_password)

    user = await db.get(User, user_id)
    if user is None:
        raise ApiError("AUTH_INVALID_CREDENTIALS", "account no longer exists", status_code=401)

    user.password_hash = security.hash_password(body.new_password)
    await db.commit()
    await security.revoke_all_sessions(user.id)
    return {"status": "ok"}


@router.post("/auth/password/change")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.get(User, current_user.id)
    if user is None:
        raise ApiError("NOT_FOUND", "user not found", status_code=404)

    if not security.verify_password(body.current_password, user.password_hash):
        raise ApiError(
            "AUTH_INVALID_CREDENTIALS", "current password is incorrect", status_code=401
        )
    security.validate_password_policy(body.new_password)

    user.password_hash = security.hash_password(body.new_password)
    await db.commit()

    # Keep the session making this request alive; revoke every other one.
    refresh_token = request.cookies.get("refresh_token")
    except_jti = None
    if refresh_token:
        try:
            except_jti = security.decode_token(refresh_token).get("jti")
        except ApiError:
            except_jti = None
    await security.revoke_all_sessions(user.id, except_jti=except_jti)
    return {"status": "ok"}


@router.get("/auth/sessions")
async def list_sessions(current_user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return await security.list_sessions(current_user.id)


@router.delete("/auth/sessions/{jti}")
async def delete_session(
    jti: str, current_user: CurrentUser = Depends(get_current_user)
) -> dict:
    revoked = await security.revoke_session(current_user.id, jti)
    if not revoked:
        raise ApiError("AUTH_FORBIDDEN", "not permitted", status_code=403)
    return {"status": "ok"}
