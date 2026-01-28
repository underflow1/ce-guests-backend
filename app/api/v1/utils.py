from fastapi import APIRouter, Depends
from datetime import datetime
from pytz import timezone

from app.config import settings
from app.services.workdays import get_date_range_data
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

tz = timezone(settings.TIMEZONE)


@router.get("/date-range")
def get_date_range(current_user: User = Depends(get_current_user)):
    """
    Получить диапазон дат для фронта (от сегодня + 8 дней)
    Использует часовой пояс из настроек
    """
    today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return get_date_range_data(today)
