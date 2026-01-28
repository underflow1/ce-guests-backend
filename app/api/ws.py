import asyncio
import json
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.models.user import User
from app.services.auth import decode_access_token
from app.services.entry_events import manager as entry_event_manager

router = APIRouter()


def get_user_from_token(token: str) -> Optional[User]:
    payload = decode_access_token(token)
    if payload is None:
        return None

    user_id: str = payload.get("sub")
    if not user_id:
        return None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None or not user.is_active:
            return None
        return user
    finally:
        db.close()


@router.websocket("/ws/entries")
async def entries_websocket(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    user = get_user_from_token(token)
    if not user:
        await websocket.close(code=1008)
        return

    await entry_event_manager.connect(websocket)
    ping_task = asyncio.create_task(entry_event_manager.send_ping(websocket))

    try:
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue

            if payload.get("type") == "pong":
                continue
    except WebSocketDisconnect:
        pass
    finally:
        ping_task.cancel()
        await entry_event_manager.disconnect(websocket)
