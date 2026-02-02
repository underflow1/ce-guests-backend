from typing import Optional, List
from pydantic import BaseModel, Field


class VisitGoalBase(BaseModel):
    name: str


class VisitGoalCreate(VisitGoalBase):
    pass


class VisitGoalUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class VisitGoalResponse(VisitGoalBase):
    id: str
    is_active: bool

    class Config:
        from_attributes = True


class VisitGoalsResponse(BaseModel):
    goals: List[VisitGoalResponse] = Field(default_factory=list)
