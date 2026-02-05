from typing import Optional, List
from pydantic import BaseModel, Field


class MeetingResultBase(BaseModel):
    name: str


class MeetingResultCreate(MeetingResultBase):
    pass


class MeetingResultUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[int] = None
    is_active: Optional[bool] = None


class MeetingResultResponse(MeetingResultBase):
    id: str
    code: Optional[int] = None
    is_active: bool

    class Config:
        from_attributes = True


class MeetingResultsResponse(BaseModel):
    results: List[MeetingResultResponse] = Field(default_factory=list)


class MeetingResultReasonBase(BaseModel):
    name: str


class MeetingResultReasonCreate(MeetingResultReasonBase):
    pass


class MeetingResultReasonUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    meeting_result_id: Optional[str] = None


class MeetingResultReasonResponse(MeetingResultReasonBase):
    id: str
    meeting_result_id: str
    is_active: bool

    class Config:
        from_attributes = True


class MeetingResultReasonsResponse(BaseModel):
    reasons: List[MeetingResultReasonResponse] = Field(default_factory=list)
