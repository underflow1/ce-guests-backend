from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.services.production_calendar import get_calendar_day, is_production_calendar_enabled


def _fallback_by_weekday(date: datetime) -> bool:
    # 0 = понедельник, 6 = воскресенье
    return date.weekday() < 5


def is_workday(db: Session, date: datetime) -> bool:
    """
    Проверка рабочего дня:
    - если production_calendar.enabled = false -> fallback (пн-пт рабочие);
    - если enabled = true -> читаем из таблицы production_calendar_days;
      если даты нет в таблице, fallback (пн-пт рабочие).
    """
    if not is_production_calendar_enabled(db):
        return _fallback_by_weekday(date)

    date_key = date.strftime("%Y-%m-%d")
    row = get_calendar_day(db, date_key)
    if row is None:
        return _fallback_by_weekday(date)
    return bool(row.is_workday)


def get_next_workday(db: Session, start_date: datetime) -> datetime:
    """Получить следующий рабочий день от указанной даты"""
    current = start_date + timedelta(days=1)
    while not is_workday(db, current):
        current += timedelta(days=1)
    return current


def get_previous_workday(db: Session, start_date: datetime) -> datetime:
    """Получить предыдущий рабочий день от указанной даты"""
    current = start_date - timedelta(days=1)
    while not is_workday(db, current):
        current -= timedelta(days=1)
    return current


def format_date(date: datetime) -> str:
    """Форматировать дату в формат YYYY-MM-DD"""
    return date.strftime("%Y-%m-%d")


def get_week_start(date: datetime) -> datetime:
    """Получить понедельник недели для указанной даты"""
    days_since_monday = date.weekday()  # 0 = понедельник, 6 = воскресенье
    monday = date - timedelta(days=days_since_monday)
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def get_week_structure(db: Session, date: datetime) -> list[dict]:
    """
    Получить структуру недели (понедельник - воскресенье) для указанной даты
    Возвращает список из 7 дней с полями: date, weekday, is_workday
    """
    week_start = get_week_start(date)
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    structure = []
    for i in range(7):
        current_date = week_start + timedelta(days=i)
        structure.append({
            "date": format_date(current_date),
            "weekday": weekdays[i],
            "is_workday": is_workday(db, current_date),
        })
    
    return structure
