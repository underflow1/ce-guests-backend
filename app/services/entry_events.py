import asyncio
import json
import logging

import anyio
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class EntryEventManager:
    def __init__(self) -> None:
        self._connections = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, payload: dict) -> None:
        message = json.dumps(payload, ensure_ascii=False)
        async with self._lock:
            connections = list(self._connections)

        for websocket in connections:
            try:
                await websocket.send_text(message)
            except Exception:
                logger.debug("WS send failed, removing connection", exc_info=True)
                await self.disconnect(websocket)

    async def send_ping(self, websocket: WebSocket, interval: float = 25.0) -> None:
        while True:
            await asyncio.sleep(interval)
            await websocket.send_text(json.dumps({"type": "ping"}))


manager = EntryEventManager()


def broadcast_entry_event(payload: dict) -> None:
    try:
        anyio.from_thread.run(manager.broadcast, payload)
    except RuntimeError:
        logger.debug("WS broadcast skipped: no running event loop")


def broadcast_entry_event_with_data(event_type: str, change_data: dict, data: dict) -> None:
    """
    Отправка WebSocket события с полной структурой данных недели
    
    Args:
        event_type: Тип события (entry_created, entry_updated, etc.)
        change_data: Данные об изменении (для поля change)
        data: Полные данные недели (entries, reference_dates, calendar_structure)
    """
    payload = {
        "type": event_type,
        "data": data,
        "change": change_data,
    }
    broadcast_entry_event(payload)
