import asyncio
import sys
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.events import lifespan
from app.core.middleware import RequestContextMiddleware
from app.core.middleware_audit import AuditMiddleware  # P2.4, see docs/DECISIONS.md
from app.core.ratelimit import limiter  # P2.5, see docs/DECISIONS.md

settings = get_settings()

app = FastAPI(title="Doctor's Copilot API", version="0.1.0", lifespan=lifespan)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    retry_after = "60"
    response = JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": "too many requests, please try again later",
                "request_id": request_id,
                "details": {},
            }
        },
    )
    response.headers["Retry-After"] = retry_after
    return response


app.add_middleware(RequestContextMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(api_router)
