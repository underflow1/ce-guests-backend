from typing import Optional, List
from pydantic import BaseModel, field_validator


class PermissionBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None


class PermissionResponse(PermissionBase):
    id: str

    class Config:
        from_attributes = True


class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None
    interface_type: str = "user"

    @field_validator('interface_type')
    @classmethod
    def validate_interface_type(cls, v: str) -> str:
        if v not in ["user", "guard", "user_new"]:
            raise ValueError('interface_type должен быть "user", "guard" или "user_new"')
        return v


class RoleCreate(RoleBase):
    permission_ids: List[str] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    interface_type: Optional[str] = None
    permission_ids: Optional[List[str]] = None

    @field_validator('interface_type')
    @classmethod
    def validate_interface_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ["user", "guard", "user_new"]:
            raise ValueError('interface_type должен быть "user", "guard" или "user_new"')
        return v


class RoleResponse(RoleBase):
    id: str
    created_at: str
    permissions: List[PermissionResponse] = []

    class Config:
        from_attributes = True


class RoleWithPermissions(RoleResponse):
    permission_ids: List[str] = []
