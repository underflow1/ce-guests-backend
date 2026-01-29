from datetime import datetime, timedelta
from typing import Optional
from functools import lru_cache
import httpx
import logging
from pytz import timezone

from app.config import settings

tz = timezone(settings.TIMEZONE)
logger = logging.getLogger(__name__)


def _is_workday_uncached(date: datetime) -> bool:
    """
    Внутренняя функция проверки рабочего дня без кеширования
    """
    year = date.year
    month = date.month
    day = date.day
    
    try:
        url = f"https://isdayoff.ru/api/getdata?year={year}&month={month}&day={day}"
        logger.debug(f"HTTP запрос к isdayoff.ru для {year}-{month:02d}-{day:02d}")
        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        result = response.text.strip()
        
        # "0" - рабочий день, "1" - выходной/праздник
        is_work = result == "0"
        logger.debug(f"Результат для {year}-{month:02d}-{day:02d}: {'рабочий' if is_work else 'выходной'}")
        return is_work
    except Exception as e:
        # Fallback: определяем по дню недели (пн-пт = рабочий)
        logger.warning(f"Ошибка при запросе к isdayoff.ru для {year}-{month:02d}-{day:02d}: {e}, используем fallback")
        weekday = date.weekday()  # 0 = понедельник, 6 = воскресенье
        return weekday < 5  # Понедельник-пятница


@lru_cache(maxsize=100)
def _is_workday_cached(date_key: str) -> bool:
    """
    Кешированная версия проверки рабочего дня
    date_key в формате "YYYY-MM-DD"
    """
    date_obj = datetime.strptime(date_key, "%Y-%m-%d")
    return _is_workday_uncached(date_obj)


def is_workday(date: datetime) -> bool:
    """
    Проверка является ли день рабочим через API isdayoff.ru
    Возвращает True для рабочего дня, False для выходного/праздника
    Использует кеширование для оптимизации повторных запросов
    """
    # Преобразуем datetime в строку для кеширования (только дата, без времени)
    date_key = date.strftime("%Y-%m-%d")
    return _is_workday_cached(date_key)


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
