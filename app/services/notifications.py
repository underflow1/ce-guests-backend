import json
import logging
from typing import Any, Dict

import httpx

from app.database import SessionLocal
from app.models.setting import Setting
from app.schemas.setting import NOTIFICATION_TYPES
from app.services.settings import build_default_notifications, normalize_notifications


logger = logging.getLogger(__name__)


def load_notifications_settings() -> Dict[str, Any]:
    db = SessionLocal()
    try:
        record = db.query(Setting).filter(Setting.key == "notifications").first()
        if not record or not record.value:
            return build_default_notifications()

        try:
            value = record.value
            notifications = normalize_notifications(json.loads(value))
            return notifications
        except Exception:
            logger.exception("Не удалось распарсить настройки notifications")
            return build_default_notifications()
    finally:
        db.close()


def should_send_notification(event_type: str, notifications: Dict[str, Any]) -> bool:
    enabled_types = notifications.get("enabled_notification_types") or []
    return event_type in enabled_types


def get_notification_title(event_type: str) -> str:
    for item in NOTIFICATION_TYPES:
        if item["code"] == event_type:
            return item["title"]
    return event_type


def format_notification_message(event_type: str, payload: Dict[str, Any]) -> str:
    title = get_notification_title(event_type)
    lines = [f"Событие: {title}"]

    change = payload.get("change") if isinstance(payload, dict) else None
    if isinstance(change, dict):
        actor = change.get("actor")
        if actor:
            lines.append(f"Действие: {actor}")
        entry = change.get("entry")
        if isinstance(entry, dict):
            if entry.get("name"):
                lines.append(f"Запись: {entry.get('name')}")
            if entry.get("responsible"):
                lines.append(f"Ответственный: {entry.get('responsible')}")
            if entry.get("datetime"):
                lines.append(f"Дата/время: {entry.get('datetime')}")
        if "deleted_count" in change:
            lines.append(f"Удалено записей: {change.get('deleted_count')}")

    return "\n".join(lines)


def send_max_via_green_api(url: str, chat_id: str, message: str) -> None:
    payload = {
        "chatId": chat_id,
        "message": message,
    }
    headers = {"Content-Type": "application/json"}
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        response_text = exc.response.text if exc.response is not None else ""
        logger.error(
            "Ошибка отправки уведомления через max_via_green_api: %s",
            response_text,
            exc_info=True,
        )
    except Exception:
        logger.exception("Ошибка отправки уведомления через max_via_green_api")


def send_telegram(bot_token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }
    try:
        response = httpx.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        response_text = exc.response.text if exc.response is not None else ""
        logger.error(
            "Ошибка отправки уведомления через telegram: %s",
            response_text,
            exc_info=True,
        )
    except Exception:
        logger.exception("Ошибка отправки уведомления через telegram")


def send_notifications_for_event(event_type: str, payload: Dict[str, Any]) -> None:
    try:
        notifications = load_notifications_settings()
        if not should_send_notification(event_type, notifications):
            return

        providers = notifications.get("providers") or {}
        message = format_notification_message(event_type, payload)

        max_provider = providers.get("max_via_green_api") or {}
        if max_provider.get("enabled"):
            url = max_provider.get("url")
            chat_id = max_provider.get("chat_id")
            if url and chat_id:
                send_max_via_green_api(url, chat_id, message)
            else:
                logger.warning("max_via_green_api включен, но url/chat_id отсутствуют")

        telegram_provider = providers.get("telegram") or {}
        if telegram_provider.get("enabled"):
            bot_token = telegram_provider.get("bot_token")
            chat_id = telegram_provider.get("chat_id")
            if bot_token and chat_id:
                send_telegram(bot_token, chat_id, message)
            else:
                logger.warning("telegram включен, но bot_token/chat_id отсутствуют")
    except Exception:
        logger.exception("Ошибка при отправке уведомлений")
