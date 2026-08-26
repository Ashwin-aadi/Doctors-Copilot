"""Append-only audit trail middleware (checkpoint P2.4).

Every mutating request (`POST`/`PATCH`/`PUT`/`DELETE`) is logged as an
`AuditLog` row: actor/role decoded best-effort from the bearer token (never
fails or blocks the request if decoding fails -- an anonymous mutation,
e.g. `/auth/register`, is still logged with a null actor), the route
*template* (so `/patients/{patient_id}` groups regardless of which id was
hit) as `action`, a best-effort `entity`/`entity_id` from the first path
segment and path params, IP, user agent, and a SHA-256 `diff_hash` of the
raw request body -- never the body itself, so no personal + health data
(DPDP/SPDI) ends up sitting in the audit trail.

A failure to write the audit row never fails the underlying request; it's
logged via structlog and swallowed, since audit logging is a compliance
control, not a request-blocking one, and a Redis/Postgres blip on the
audit path should never turn into a 500 for an otherwise-successful
mutation.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core import security
from app.db.models.audit import AuditLog
from app.db.session import SessionLocal

logger = structlog.get_logger("audit")

MUTATING_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})


def _decode_actor(request: Request) -> tuple[UUID | None, str | None]:
    authorization = request.headers.get("authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None, None
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = security.decode_token(token)
    except Exception:
        return None, None

    actor_id: UUID | None = None
    sub = claims.get("sub")
    if sub:
        try:
            actor_id = UUID(str(sub))
        except ValueError:
            actor_id = None
    return actor_id, claims.get("role")


def route_template_for(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if path else request.url.path


def entity_and_id_for(request: Request, route_template: str) -> tuple[str, str | None]:
    parts = [p for p in route_template.strip("/").split("/") if p]
    if parts[:2] == ["api", "v1"]:
        parts = parts[2:]
    entity = parts[0] if parts else "unknown"

    entity_id: str | None = None
    if request.path_params:
        entity_id = str(next(iter(request.path_params.values())))
    return entity, entity_id


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in MUTATING_METHODS:
            return await call_next(request)

        body = await request.body()
        response = await call_next(request)

        try:
            await self._record(request, body)
        except Exception:
            logger.warning("audit_write_failed", path=request.url.path, method=request.method)

        return response

    async def _record(self, request: Request, body: bytes) -> None:
        actor_id, role = _decode_actor(request)
        route_template = route_template_for(request)
        entity, entity_id = entity_and_id_for(request, route_template)
        diff_hash = hashlib.sha256(body).hexdigest() if body else None

        entry = AuditLog(
            actor_id=actor_id,
            role=role,
            action=f"{request.method} {route_template}",
            entity=entity,
            entity_id=entity_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            diff_hash=diff_hash,
            ts=datetime.now(UTC),
        )
        async with SessionLocal() as session:
            session.add(entry)
            await session.commit()
