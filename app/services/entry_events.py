import asyncio
import json
import logging
from typing import Any

import anyio
from fastapi import WebSocket

from app.services.notifications import send_notifications_for_event

logger = logging.getLogger(__name__)


class EntryEventManager:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, int] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, week_offset: int = 0) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[websocket] = int(week_offset)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(websocket, None)

    async def broadcast(self, payload: dict) -> None:
        message = json.dumps(payload, ensure_ascii=False)
        async with self._lock:
            connections = list(self._connections.keys())

        for websocket in connections:
            try:
                await websocket.send_text(message)
            except Exception:
                logger.debug("WS send failed, removing connection", exc_info=True)
                await self.disconnect(websocket)

    async def get_active_week_offsets(self) -> set[int]:
        async with self._lock:
            return {int(week_offset) for week_offset in self._connections.values()}

    async def broadcast_with_week_data(
        self,
        event_type: str,
        change_data: dict,
        data_by_week_offset: dict[int, dict[str, Any]],
        default_week_offset: int = 0,
    ) -> None:
        async with self._lock:
            connections = list(self._connections.items())

        for websocket, week_offset in connections:
            try:
                payload = {
                    "type": event_type,
                    "data": data_by_week_offset.get(week_offset)
                    or data_by_week_offset.get(default_week_offset)
                    or {},
                    "change": change_data,
                }
                await websocket.send_text(json.dumps(payload, ensure_ascii=False))
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


def get_active_week_offsets() -> set[int]:
    try:
        return anyio.from_thread.run(manager.get_active_week_offsets)
    except RuntimeError:
        logger.debug("WS offsets snapshot skipped: no running event loop")
        return set()


def broadcast_entry_event_with_data(
    event_type: str,
    change_data: dict,
    data_by_week_offset: dict[int, dict[str, Any]],
    default_week_offset: int = 0,
) -> None:
    """
    Отправка WebSocket события с полной структурой данных недели
    персонально для каждого week_offset подключения.

    Args:
        event_type: Тип события (entry_created, entry_updated, etc.)
        change_data: Данные об изменении (для поля change)
        data_by_week_offset: Карта week_offset -> полные данные (entries, reference_dates, calendar_structure)
        default_week_offset: Fallback-оффсет, если для конкретного сокета нет данных
    """
    payload_for_notifications = {
        "type": event_type,
        "data": data_by_week_offset.get(default_week_offset) or {},
        "change": change_data,
    }
    try:
        anyio.from_thread.run(
            manager.broadcast_with_week_data,
            event_type,
            change_data,
            data_by_week_offset,
            default_week_offset,
        )
    except RuntimeError:
        logger.debug("WS broadcast skipped: no running event loop")
    send_notifications_for_event(event_type, payload_for_notifications)
