from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator


class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str
    is_admin: bool = False
    role_id: Optional[str] = None

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError('Пароль должен содержать минимум 6 символов')
        return v


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    role_id: Optional[str] = None

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) < 6:
            raise ValueError('Пароль должен содержать минимум 6 символов')
        return v


class RoleInfo(BaseModel):
    id: str
    name: str
    interface_type: str

    class Config:
        from_attributes = True


class UserResponse(UserBase):
    id: str
    is_admin: bool
    is_active: bool
    role_id: Optional[str] = None
    role: Optional[RoleInfo] = None
    permissions: List[str] = []
    created_at: str

    class Config:
        from_attributes = True


class UserInDB(UserResponse):
    password_hash: str
