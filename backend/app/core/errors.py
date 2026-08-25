import uuid
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

ErrorCode = Literal[
    "AUTH_INVALID_CREDENTIALS",
    "AUTH_TOKEN_EXPIRED",
    "AUTH_FORBIDDEN",
    "CAPTCHA_REQUIRED",
    "CAPTCHA_INVALID",
    "VALIDATION_FAILED",
    "NOT_FOUND",
    "LOCKED",
    "CONFLICT",
    "RATE_LIMITED",
    "UPSTREAM_UNAVAILABLE",
    "MODEL_UNAVAILABLE",
    "INTERNAL",
    "NOT_IMPLEMENTED",
]


class ApiError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _envelope(code: str, message: str, request_id: str, details: dict[str, Any]) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": details,
        }
    }


def _request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    return rid or request.headers.get("X-Request-ID") or str(uuid.uuid4())


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, _request_id(request), exc.details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "INTERNAL"
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail), _request_id(request), {}),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "VALIDATION_FAILED",
                "request validation failed",
                _request_id(request),
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=_envelope("INTERNAL", "internal server error", _request_id(request), {}),
        )


def not_implemented(detail: str = "not implemented yet") -> ApiError:
    return ApiError("NOT_IMPLEMENTED", detail, status_code=501)
