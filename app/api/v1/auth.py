import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.user import UserResponse
from app.services.auth import (
    verify_password,
    create_access_token,
    get_current_timestamp,
)
from app.api.deps import get_current_user, get_user_permissions, get_user_ui_permissions

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/login", response_model=LoginResponse)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    """Авторизация пользователя (по username или email)"""
    # Пытаемся найти пользователя по username или email
    user = db.query(User).filter(
        (User.username == login_data.username) | (User.email == login_data.username)
    ).first()
    
    if not user or not verify_password(login_data.password, user.password_hash):
        logger.warning(f"Неудачная попытка входа: '{login_data.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя/email или пароль",
        )
    
    if not user.is_active:
        logger.warning(f"Попытка входа деактивированного пользователя: '{login_data.username}'")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь деактивирован",
        )
    
    # Создаем токен
    access_token = create_access_token(data={"sub": user.id})
    
    logger.info(f"Успешный вход пользователя: '{user.username}' (ID: {user.id})")
    
    # Загружаем пользователя с ролью для ответа
    from sqlalchemy.orm import joinedload
    from app.models.role import Role
    from app.models.role_permission import RolePermission
    
    user_with_role = db.query(User).options(
        joinedload(User.role).joinedload(Role.role_permissions).joinedload(RolePermission.permission)
    ).filter(User.id == user.id).first()
    
    # Отдаем только UI-права на фронтенд
    ui_permissions = get_user_ui_permissions(user_with_role)
    
    role_info = None
    if user_with_role.role:
        role_info = {
            "id": user_with_role.role.id,
            "name": user_with_role.role.name,
            "interface_type": user_with_role.role.interface_type,
        }
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user_with_role.id,
            username=user_with_role.username,
            email=user_with_role.email,
            full_name=user_with_role.full_name,
            is_admin=bool(user_with_role.is_admin),
            is_active=bool(user_with_role.is_active),
            role_id=user_with_role.role_id,
            role=role_info,
            permissions=list(ui_permissions),
            created_at=user_with_role.created_at,
        ),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Получить информацию о текущем пользователе с ролью и правами (только UI-права)"""
    # Отдаем только UI-права на фронтенд
    ui_permissions = get_user_ui_permissions(current_user)
    
    role_info = None
    if current_user.role:
        role_info = {
            "id": current_user.role.id,
            "name": current_user.role.name,
            "interface_type": current_user.role.interface_type,
        }
    
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        is_admin=bool(current_user.is_admin),
        is_active=bool(current_user.is_active),
        role_id=current_user.role_id,
        role=role_info,
        permissions=list(ui_permissions),
        created_at=current_user.created_at,
    )
