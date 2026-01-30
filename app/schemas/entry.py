from typing import Optional
from pydantic import BaseModel, validator


class EntryBase(BaseModel):
    name: str
    responsible: Optional[str] = None
    datetime: str  # ISO 8601 format: YYYY-MM-DDTHH:MM:SS
    is_completed: Optional[bool] = False

    @validator("datetime")
    def validate_datetime(cls, v):
        """Валидация формата datetime"""
        try:
            from datetime import datetime
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("datetime должен быть в формате ISO 8601 (YYYY-MM-DDTHH:MM:SS)")
        return v


class EntryCreate(EntryBase):
    pass


class EntryUpdate(BaseModel):
    """Схема для обновления записи через PUT (только name и responsible)"""
    name: str
    responsible: Optional[str] = None


class EntryCompletedUpdate(BaseModel):
    is_completed: bool


class VisitCancelledUpdate(BaseModel):
    is_cancelled: bool


class EntryMoveUpdate(BaseModel):
    """Схема для перемещения записи через PATCH /move (только datetime)"""
    datetime: str  # ISO 8601 format: YYYY-MM-DDTHH:MM:SS

    @validator("datetime")
    def validate_datetime(cls, v):
        """Валидация формата datetime"""
        try:
            from datetime import datetime
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("datetime должен быть в формате ISO 8601 (YYYY-MM-DDTHH:MM:SS)")
        return v


class EntryResponse(EntryBase):
    id: str
    created_by: str
    created_at: str
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None
    is_completed: bool
    is_cancelled: bool = False
    current_pass_id: Optional[str] = None
    pass_status: Optional[str] = None

    class Config:
        from_attributes = True


class CalendarDay(BaseModel):
    """Модель для одного дня в структуре календаря"""
    date: str  # YYYY-MM-DD
    weekday: str  # Monday, Tuesday, Wednesday, etc.
    is_workday: bool


class ReferenceDates(BaseModel):
    """Модель для ключевых дат (предыдущий и следующий рабочий день)"""
    previous_workday: str  # YYYY-MM-DD
    next_workday: str  # YYYY-MM-DD


class EntriesListResponse(BaseModel):
    entries: list[EntryResponse]
    reference_dates: ReferenceDates
    calendar_structure: list[CalendarDay]


class ResponsibleAutocompleteResponse(BaseModel):
    suggestions: list[str]
