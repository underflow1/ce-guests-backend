from typing import Dict, List
from pydantic import BaseModel, Field

from app.schemas.reason import ReasonResponse
from app.schemas.visit_goal import VisitGoalResponse


class ReferenceDataResponse(BaseModel):
    visit_goals: List[VisitGoalResponse] = Field(default_factory=list)
    reasons: List[ReasonResponse] = Field(default_factory=list)
    reasons_by_state: Dict[str, List[ReasonResponse]] = Field(default_factory=dict)
    pass_ordering_enabled: bool = False
    production_calendar_enabled: bool = False
    production_calendar_loaded_for_current_year: bool = False
    production_calendar_fallback_active: bool = False