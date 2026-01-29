from datetime import datetime, timedelta
from typing import Optional
import httpx
from pytz import timezone

from app.config import settings

tz = timezone(settings.TIMEZONE)


def is_workday(date: datetime) -> bool:
    """
    Проверка является ли день рабочим через API isdayoff.ru
    Возвращает True для рабочего дня, False для выходного/праздника
    """
    year = date.year
    month = date.month
    day = date.day
    
    try:
        url = f"https://isdayoff.ru/api/getdata?year={year}&month={month}&day={day}"
        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        result = response.text.strip()
        
        # "0" - рабочий день, "1" - выходной/праздник
        return result == "0"
    except Exception:
        # Fallback: определяем по дню недели (пн-пт = рабочий)
        weekday = date.weekday()  # 0 = понедельник, 6 = воскресенье
        return weekday < 5  # Понедельник-пятница


def get_next_workday(start_date: datetime) -> datetime:
    """Получить следующий рабочий день от указанной даты"""
    current = start_date + timedelta(days=1)
    while not is_workday(current):
        current += timedelta(days=1)
    return current


def get_previous_workday(start_date: datetime) -> datetime:
    """Получить предыдущий рабочий день от указанной даты"""
    current = start_date - timedelta(days=1)
    while not is_workday(current):
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


def get_week_structure(date: datetime) -> list[dict]:
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
            "is_workday": is_workday(current_date),
        })
    
    return structure
