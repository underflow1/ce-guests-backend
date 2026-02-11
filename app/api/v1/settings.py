import json
import uuid
from datetime import datetime
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin
from app.database import get_db
from app.models.setting import Setting
from app.models.user import User
from app.schemas.setting import NOTIFICATION_TYPE_CODES, SettingsResponse, SettingsUpdateRequest
from app.services.auth import get_current_timestamp
from app.services.production_calendar import (
    clear_production_calendar_year,
    get_production_calendar_status,
    load_production_calendar_year,
    set_production_calendar_meta,
)
from app.services.settings import build_settings_metadata, normalize_notifications, normalize_pass_integration, normalize_production_calendar

router = APIRouter()


def _read_settings_data(db: Session) -> Dict[str, Any]:
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
    return settings_data


def build_settings_response(
    db: Session,
    notifications: Dict[str, Any],
    pass_integration: Dict[str, Any],
    production_calendar: Dict[str, Any],
) -> Dict[str, Any]:
    current_year = datetime.now().year
    return {
        "notifications": notifications,
        "pass_integration": pass_integration,
        "production_calendar": {
            **production_calendar,
            "status": get_production_calendar_status(db=db, year=current_year),
        },
        "metadata": build_settings_metadata(),
    }


@router.get("/settings", response_model=SettingsResponse, response_model_exclude_none=True)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Получить текущие настройки (только для админов)"""
    settings_data = _read_settings_data(db)

    notifications = normalize_notifications(settings_data.get("notifications"))
    pass_integration = normalize_pass_integration(settings_data.get("pass_integration"))
    production_calendar = normalize_production_calendar(settings_data.get("production_calendar"))
    return build_settings_response(db, notifications, pass_integration, production_calendar)


@router.put("/settings", response_model=SettingsResponse, response_model_exclude_none=True)
def update_settings(
    payload: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Обновить настройки (только для админов)"""
    notifications = payload.notifications
    pass_integration = payload.pass_integration
    production_calendar = payload.production_calendar

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

    # Совместимость: устаревшие коды уведомлений игнорируем вместо ошибки
    valid_enabled_types = []
    seen_types = set()
    for notification_type in notifications.enabled_notification_types:
        if notification_type not in NOTIFICATION_TYPE_CODES:
            continue
        if notification_type in seen_types:
            continue
        seen_types.add(notification_type)
        valid_enabled_types.append(notification_type)
    notifications.enabled_notification_types = valid_enabled_types

    # Валидация pass_integration
    if pass_integration.enabled and (
        not pass_integration.base_url
        or not pass_integration.login
        or not pass_integration.password
        or not pass_integration.object
        or not pass_integration.corpa
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для pass_integration обязательны base_url, login, password, object и corpa",
        )

    notifications_dict = notifications.dict(exclude_none=True)
    value = json.dumps(notifications_dict, ensure_ascii=False)

    notifications_setting = db.query(Setting).filter(Setting.key == "notifications").first()
    pass_setting = db.query(Setting).filter(Setting.key == "pass_integration").first()
    calendar_setting = db.query(Setting).filter(Setting.key == "production_calendar").first()
    timestamp = get_current_timestamp()

    if notifications_setting:
        notifications_setting.value = value
        notifications_setting.updated_at = timestamp
        notifications_setting.updated_by = current_user.id
    else:
        notifications_setting = Setting(
            id=str(uuid.uuid4()),
            key="notifications",
            value=value,
            updated_at=timestamp,
            updated_by=current_user.id,
        )
        db.add(notifications_setting)

    pass_dict = pass_integration.dict(exclude_none=True)
    pass_value = json.dumps(pass_dict, ensure_ascii=False)
    if pass_setting:
        pass_setting.value = pass_value
        pass_setting.updated_at = timestamp
        pass_setting.updated_by = current_user.id
    else:
        pass_setting = Setting(
            id=str(uuid.uuid4()),
            key="pass_integration",
            value=pass_value,
            updated_at=timestamp,
            updated_by=current_user.id,
        )
        db.add(pass_setting)

    production_calendar_dict = production_calendar.dict(exclude_none=True)
    production_calendar_value = json.dumps(production_calendar_dict, ensure_ascii=False)
    if calendar_setting:
        calendar_setting.value = production_calendar_value
        calendar_setting.updated_at = timestamp
        calendar_setting.updated_by = current_user.id
    else:
        calendar_setting = Setting(
            id=str(uuid.uuid4()),
            key="production_calendar",
            value=production_calendar_value,
            updated_at=timestamp,
            updated_by=current_user.id,
        )
        db.add(calendar_setting)

    db.commit()
    db.refresh(notifications_setting)
    db.refresh(pass_setting)
    db.refresh(calendar_setting)

    normalized = normalize_notifications(notifications_dict)
    normalized_pass = normalize_pass_integration(pass_dict)
    normalized_calendar = normalize_production_calendar(production_calendar_dict)
    return build_settings_response(db, normalized, normalized_pass, normalized_calendar)


@router.post("/settings/production-calendar/load-current-year", response_model=SettingsResponse, response_model_exclude_none=True)
def load_current_year_production_calendar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    year = datetime.now().year
    try:
        load_production_calendar_year(db, year)
        set_production_calendar_meta(
            db,
            last_loaded_at=get_current_timestamp(),
            updated_by=current_user.id,
        )
        db.commit()
    except httpx.HTTPError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Не удалось загрузить производственный календарь: {str(exc)}",
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )

    settings_data = _read_settings_data(db)
    notifications = normalize_notifications(settings_data.get("notifications"))
    pass_integration = normalize_pass_integration(settings_data.get("pass_integration"))
    production_calendar = normalize_production_calendar(settings_data.get("production_calendar"))
    return build_settings_response(db, notifications, pass_integration, production_calendar)


@router.delete("/settings/production-calendar/current-year", response_model=SettingsResponse, response_model_exclude_none=True)
def clear_current_year_production_calendar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    year = datetime.now().year
    clear_production_calendar_year(db, year)
    set_production_calendar_meta(
        db,
        last_cleared_at=get_current_timestamp(),
        updated_by=current_user.id,
    )
    db.commit()

    settings_data = _read_settings_data(db)
    notifications = normalize_notifications(settings_data.get("notifications"))
    pass_integration = normalize_pass_integration(settings_data.get("pass_integration"))
    production_calendar = normalize_production_calendar(settings_data.get("production_calendar"))
    return build_settings_response(db, notifications, pass_integration, production_calendar)
