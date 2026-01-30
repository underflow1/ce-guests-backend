import json
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.setting import Setting
from app.models.user import User
from app.api.deps import get_current_active_admin
from app.schemas.setting import (
    SettingsUpdateRequest,
    SettingsResponse,
    NOTIFICATION_TYPE_CODES,
)
from app.services.auth import get_current_timestamp
from app.services.settings import (
    build_default_notifications,
    normalize_notifications,
    build_settings_metadata,
)

router = APIRouter()


def build_settings_response(notifications: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "notifications": notifications,
        "metadata": build_settings_metadata(),
    }


@router.get("/settings", response_model=SettingsResponse, response_model_exclude_none=True)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Получить текущие настройки (только для админов)"""
    records = db.query(Setting).all()
    settings_data: Dict[str, Any] = {}

    for record in records:
        if record.value:
            try:
                settings_data[record.key] = json.loads(record.value)
            except json.JSONDecodeError:
                settings_data[record.key] = {}
        else:
            settings_data[record.key] = {}

    notifications = normalize_notifications(settings_data.get("notifications"))
    return build_settings_response(notifications)


@router.put("/settings", response_model=SettingsResponse, response_model_exclude_none=True)
def update_settings(
    payload: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Обновить настройки (только для админов)"""
    notifications = payload.notifications

    # Валидация активных провайдеров
    max_provider = notifications.providers.max_via_green_api
    if max_provider.enabled and (
        not max_provider.base_url
        or not max_provider.instance_id
        or not max_provider.api_token
        or not max_provider.chat_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для max_via_green_api обязательны base_url, instance_id, api_token и chat_id",
        )

    telegram_provider = notifications.providers.telegram
    if telegram_provider.enabled and (not telegram_provider.bot_token or not telegram_provider.chat_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для telegram обязательны bot_token и chat_id",
        )

    # Валидация типов уведомлений
    invalid_types = [
        notification_type
        for notification_type in notifications.enabled_notification_types
        if notification_type not in NOTIFICATION_TYPE_CODES
    ]
    if invalid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недопустимые типы уведомлений: {', '.join(invalid_types)}",
        )

    notifications_dict = notifications.dict(exclude_none=True)
    value = json.dumps(notifications_dict, ensure_ascii=False)

    setting = db.query(Setting).filter(Setting.key == "notifications").first()
    timestamp = get_current_timestamp()

    if setting:
        setting.value = value
        setting.updated_at = timestamp
        setting.updated_by = current_user.id
    else:
        setting = Setting(
            id=str(uuid.uuid4()),
            key="notifications",
            value=value,
            updated_at=timestamp,
            updated_by=current_user.id,
        )
        db.add(setting)

    db.commit()
    db.refresh(setting)

    normalized = normalize_notifications(notifications_dict)
    return build_settings_response(normalized)
