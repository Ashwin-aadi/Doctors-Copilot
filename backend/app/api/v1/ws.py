"""Live visit and queue streams.

Both sockets authenticate on connect from a `token` query parameter -- browsers
cannot set an Authorization header on a WebSocket handshake -- and close with
1008 if the token is missing or invalid. A 20 second heartbeat keeps proxies
from dropping an idle clinic display, and doubles as the liveness check that
detects a client that has gone away without a close frame.
"""

from __future__ import annotations

import asyncio
import contextlib
from uuid import UUID

import orjson
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core import events
from app.core.deps import CurrentUser
from app.core.logging import get_logger

router = APIRouter(tags=["ws"])
log = get_logger(__name__)

HEARTBEAT_SECONDS = 20


async def _authenticate(websocket: WebSocket, token: str | None) -> CurrentUser | None:
    if not token:
        await websocket.close(code=1008, reason="token query parameter is required")
        return None
    try:
        from app.core import security

        claims = security.decode_token(token)
        if claims.get("typ") != "access":
            raise ValueError("not an access token")
        return CurrentUser(id=UUID(claims["sub"]), role=claims.get("role", ""))
    except Exception as exc:  # noqa: BLE001
        log.info("ws_auth_rejected", error=str(exc))
        await websocket.close(code=1008, reason="invalid token")
        return None


async def _pump(websocket: WebSocket, channel: str) -> None:
    """Forward Redis messages to the socket, heartbeating while it is quiet."""

    async with events.subscribe(channel) as pubsub:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=HEARTBEAT_SECONDS
            )
            if message is None:
                await websocket.send_text(orjson.dumps({"type": "heartbeat"}).decode())
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode()
            await websocket.send_text(data)


async def _serve(websocket: WebSocket, channel: str, token: str | None, hello: dict) -> None:
    await websocket.accept()
    user = await _authenticate(websocket, token)
    if user is None:
        return

    await websocket.send_text(orjson.dumps({"type": "connected", **hello}).decode())

    pump = asyncio.create_task(_pump(websocket, channel))
    try:
        # Reading serves only to notice a client disconnecting; the stream is
        # one-directional, so anything the client sends is ignored.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.info("ws_closed", channel=channel, error=str(exc))
    finally:
        pump.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await pump


@router.websocket("/ws/visit/{visit_id}")
async def ws_visit(
    websocket: WebSocket, visit_id: UUID, token: str | None = Query(default=None)
) -> None:
    await _serve(
        websocket,
        events.visit_channel(str(visit_id)),
        token,
        {"channel": "visit", "visit_id": str(visit_id)},
    )


@router.websocket("/ws/queue/{clinic_id}")
async def ws_queue(
    websocket: WebSocket, clinic_id: UUID, token: str | None = Query(default=None)
) -> None:
    await _serve(
        websocket,
        events.queue_channel(str(clinic_id)),
        token,
        {"channel": "queue", "clinic_id": str(clinic_id)},
    )
