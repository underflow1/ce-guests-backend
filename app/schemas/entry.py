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


class EntryUpdate(EntryBase):
    pass


class EntryCompletedUpdate(BaseModel):
    is_completed: bool


class EntryResponse(EntryBase):
    id: str
    created_by: str
    created_at: str
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None
    is_completed: bool

    class Config:
        from_attributes = True


class EntriesListResponse(BaseModel):
    entries: list[EntryResponse]
    date_range: dict[str, str]  # {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}


class ResponsibleAutocompleteResponse(BaseModel):
    suggestions: list[str]
