import json
import logging
from datetime import date as date_class, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.production_calendar_day import ProductionCalendarDay
from app.models.setting import Setting

logger = logging.getLogger(__name__)

PRODUCTION_CALENDAR_SETTING_KEY = "production_calendar"
PRODUCTION_CALENDAR_META_SETTING_KEY = "production_calendar_meta"


def normalize_production_calendar(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {"enabled": False}
    return {"enabled": bool(value.get("enabled"))}


def get_production_calendar_settings(db: Session) -> dict[str, bool]:
    row = db.query(Setting).filter(Setting.key == PRODUCTION_CALENDAR_SETTING_KEY).first()
    if not row or not row.value:
        return {"enabled": False}

    try:
        payload = json.loads(row.value)
    except json.JSONDecodeError:
        return {"enabled": False}
    return normalize_production_calendar(payload)


def is_production_calendar_enabled(db: Session) -> bool:
    return bool(get_production_calendar_settings(db).get("enabled"))


def _days_in_year(year: int) -> int:
    first = date_class(year, 1, 1)
    next_first = date_class(year + 1, 1, 1)
    return (next_first - first).days


def get_production_calendar_status(db: Session, year: int) -> dict[str, Any]:
    loaded_days_count = (
        db.query(ProductionCalendarDay)
        .filter(ProductionCalendarDay.year == year)
        .count()
    )
    expected_days_count = _days_in_year(year)
    missing_days_count = max(expected_days_count - loaded_days_count, 0)
    meta = get_production_calendar_meta(db)
    return {
        "current_year": year,
        "loaded_days_count": loaded_days_count,
        "expected_days_count": expected_days_count,
        "missing_days_count": missing_days_count,
        "is_loaded_for_current_year": loaded_days_count > 0,
        "is_complete_for_current_year": loaded_days_count >= expected_days_count,
        "last_loaded_at": meta.get("last_loaded_at"),
        "last_cleared_at": meta.get("last_cleared_at"),
    }


def _parse_year_payload(payload: str, year: int) -> list[dict[str, Any]]:
    normalized_payload = "".join(payload.split())
    expected_days = _days_in_year(year)
    if len(normalized_payload) < expected_days:
        raise ValueError(
            f"Некорректный ответ isdayoff.ru: ожидалось {expected_days} символов, получено {len(normalized_payload)}"
        )

    # Если пришло больше, используем только нужное количество символов.
    normalized_payload = normalized_payload[:expected_days]

    jan_first = datetime(year, 1, 1)
    rows: list[dict[str, Any]] = []
    for offset, char in enumerate(normalized_payload):
        current_date = jan_first + timedelta(days=offset)
        # 0,2,4 считаем рабочими; 1 считаем выходным.
        is_workday = char in {"0", "2", "4"}
        rows.append(
            {
                "date": current_date.strftime("%Y-%m-%d"),
                "year": year,
                "is_workday": is_workday,
            }
        )
    return rows


def load_production_calendar_year(db: Session, year: int) -> dict[str, Any]:
    url = f"https://isdayoff.ru/api/getdata?year={year}&pre=1"
    logger.info("Загружаем производственный календарь за %s год", year)

    response = httpx.get(url, timeout=15.0)
    response.raise_for_status()
    rows = _parse_year_payload(response.text, year)

    db.query(ProductionCalendarDay).filter(ProductionCalendarDay.year == year).delete()
    db.add_all([ProductionCalendarDay(**row) for row in rows])
    db.flush()

    return get_production_calendar_status(db, year)


def clear_production_calendar_year(db: Session, year: int) -> dict[str, Any]:
    db.query(ProductionCalendarDay).filter(ProductionCalendarDay.year == year).delete()
    db.flush()
    return get_production_calendar_status(db, year)


def get_calendar_day(db: Session, date_key: str) -> ProductionCalendarDay | None:
    return (
        db.query(ProductionCalendarDay)
        .filter(ProductionCalendarDay.date == date_key)
        .first()
    )


def get_production_calendar_meta(db: Session) -> dict[str, str | None]:
    row = db.query(Setting).filter(Setting.key == PRODUCTION_CALENDAR_META_SETTING_KEY).first()
    if not row or not row.value:
        return {"last_loaded_at": None, "last_cleared_at": None}
    try:
        payload = json.loads(row.value)
        if not isinstance(payload, dict):
            return {"last_loaded_at": None, "last_cleared_at": None}
        return {
            "last_loaded_at": payload.get("last_loaded_at"),
            "last_cleared_at": payload.get("last_cleared_at"),
        }
    except json.JSONDecodeError:
        return {"last_loaded_at": None, "last_cleared_at": None}


def set_production_calendar_meta(
    db: Session,
    *,
    last_loaded_at: str | None = None,
    last_cleared_at: str | None = None,
    updated_by: str | None = None,
) -> None:
    row = db.query(Setting).filter(Setting.key == PRODUCTION_CALENDAR_META_SETTING_KEY).first()
    current_meta = get_production_calendar_meta(db)
    if last_loaded_at is not None:
        current_meta["last_loaded_at"] = last_loaded_at
    if last_cleared_at is not None:
        current_meta["last_cleared_at"] = last_cleared_at

    value = json.dumps(current_meta, ensure_ascii=False)
    timestamp = datetime.now().isoformat()
    if row:
        row.value = value
        row.updated_at = timestamp
        row.updated_by = updated_by
    else:
        db.add(
            Setting(
                key=PRODUCTION_CALENDAR_META_SETTING_KEY,
                value=value,
                updated_at=timestamp,
                updated_by=updated_by,
            )
        )
