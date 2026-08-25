from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])


@router.websocket("/ws/visit/{visit_id}")
async def ws_visit(websocket: WebSocket, visit_id: UUID) -> None:
    await websocket.accept()
    try:
        await websocket.close(code=1013, reason="visit stream lands in A3.5")
    except WebSocketDisconnect:
        pass


@router.websocket("/ws/queue/{clinic_id}")
async def ws_queue(websocket: WebSocket, clinic_id: UUID) -> None:
    await websocket.accept()
    try:
        await websocket.close(code=1013, reason="queue stream lands in A3.5")
    except WebSocketDisconnect:
        pass
