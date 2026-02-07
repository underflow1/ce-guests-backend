from typing import Optional, List
from pydantic import BaseModel, validator


class EntryBase(BaseModel):
    name: str
    responsible: Optional[str] = None
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


class EntryCreate(EntryBase):
    visit_goal_ids: List[str]

    @validator("visit_goal_ids")
    def validate_visit_goal_ids(cls, v):
        if not isinstance(v, list) or len(v) == 0:
            raise ValueError("Нужно выбрать хотя бы одну цель визита")
        return v


class EntryUpdate(BaseModel):
    """Схема для обновления исходных полей записи (детали визита)"""
    name: str
    responsible: Optional[str] = None
    visit_goal_ids: List[str]

    @validator("visit_goal_ids")
    def validate_visit_goal_ids(cls, v):
        if not isinstance(v, list) or len(v) == 0:
            raise ValueError("Нужно выбрать хотя бы одну цель визита")
        return v


class EntryDetailsUpdate(BaseModel):
    """Атомарное обновление деталей визита (только для черновика)"""
    name: str
    responsible: Optional[str] = None
    visit_goal_ids: List[str]

    @validator("visit_goal_ids")
    def validate_visit_goal_ids(cls, v):
        if not isinstance(v, list) or len(v) == 0:
            raise ValueError("Нужно выбрать хотя бы одну цель визита")
        return v


class EntryMeetingResultUpdate(BaseModel):
    """Атомарная установка/смена результата встречи"""
    meeting_result_id: str
    meeting_result_reason_id: Optional[str] = None


class EntryCompletedUpdate(BaseModel):
    completed: bool


class VisitCancelledUpdate(BaseModel):
    cancelled: bool


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
    state: int = 10
    current_pass_id: Optional[str] = None
    pass_status: Optional[str] = None
    visit_goal_ids: List[str] = []
    meeting_result_name: Optional[str] = None
    meeting_result_code: Optional[int] = None
    meeting_result_reason_id: Optional[str] = None
    meeting_result_reason_name: Optional[str] = None

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
