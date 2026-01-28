from typing import Optional
from pydantic import BaseModel


class PermissionBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None


class PermissionResponse(PermissionBase):
    id: str

    class Config:
        from_attributes = True
