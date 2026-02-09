from typing import Optional, List

from pydantic import BaseModel, Field


class ReasonBase(BaseModel):
    name: str


class ReasonCreate(ReasonBase):
    pass


class ReasonUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class ReasonResponse(ReasonBase):
    id: str
    is_active: bool = True
    created_at: str
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


class ReasonsResponse(BaseModel):
    reasons: List[ReasonResponse] = Field(default_factory=list)


class StateReasonsUpdate(BaseModel):
    reason_ids: List[str] = Field(default_factory=list)

