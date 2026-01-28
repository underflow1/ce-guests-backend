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


def get_next_monday(start_date: datetime) -> datetime:
    """Получить следующий рабочий понедельник от указанной даты"""
    # Находим следующий понедельник
    days_ahead = 7 - start_date.weekday()  # Дней до следующего понедельника
    if days_ahead == 7:
        # Если сегодня понедельник, проверяем следующий понедельник
        days_ahead = 7
    next_monday = start_date + timedelta(days=days_ahead)
    
    # Если следующий понедельник не рабочий, ищем следующий рабочий понедельник
    while not is_workday(next_monday):
        next_monday += timedelta(days=7)
    
    return next_monday


def format_date(date: datetime) -> str:
    """Форматировать дату в формат YYYY-MM-DD"""
    return date.strftime("%Y-%m-%d")


def get_date_range_data(today: Optional[datetime] = None) -> dict:
    """
    Получить данные о диапазоне дат для фронта
    Возвращает: today, tomorrow, next_monday, date_from, date_to
    """
    if today is None:
        today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # Убеждаемся что дата в нужном часовом поясе
        if today.tzinfo is None:
            today = tz.localize(today)
        else:
            today = today.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    
    tomorrow = get_next_workday(today)
    next_monday = get_next_monday(today)
    date_from = today
    date_to = today + timedelta(days=8)  # От сегодня + 8 дней включительно
    
    return {
        "today": format_date(today),
        "tomorrow": format_date(tomorrow),
        "next_monday": format_date(next_monday),
        "date_from": format_date(date_from),
        "date_to": format_date(date_to),
    }
