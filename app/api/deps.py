from typing import Optional, Set, List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.user import User
from app.models.role import Role
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.services.auth import decode_access_token

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Получить текущего пользователя из JWT токена с загруженной ролью"""
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен авторизации",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен авторизации",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Загружаем пользователя с ролью и правами роли
    user = db.query(User).options(
        joinedload(User.role).joinedload(Role.role_permissions).joinedload(RolePermission.permission)
    ).filter(User.id == user_id).first()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь деактивирован",
        )
    
    # Проверяем что у не-админа есть роль
    if not user.is_admin and user.role_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У пользователя не назначена роль",
        )
    
    return user


def get_current_active_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """Проверка что текущий пользователь - админ"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав доступа",
        )
    return current_user


def get_user_permissions(user: User) -> Set[str]:
    """Получить набор прав пользователя (коды прав) - все права (бэкенд + фронтенд)"""
    if user.is_admin:
        # Админ имеет все права (бэкенд + фронтенд)
        return {
            # Бэкенд-права
            "can_view", "can_add", "can_edit_entry", "can_delete_entry",
            "can_mark_completed", "can_unmark_completed",
            # Фронтенд-права
            "can_move_ui", "can_mark_completed_ui", "can_unmark_completed_ui",
            "can_edit_entry_ui", "can_delete_ui"
        }
    
    if not user.role or not user.role.role_permissions:
        return set()
    
    return {rp.permission.code for rp in user.role.role_permissions}


def get_user_ui_permissions(user: User) -> Set[str]:
    """Получить только UI-права пользователя (для отдачи на фронтенд)"""
    all_permissions = get_user_permissions(user)
    # Фильтруем только права с суффиксом _ui
    return {perm for perm in all_permissions if perm.endswith("_ui")}


def require_permission(permission_code: str):
    """Dependency для проверки наличия права у пользователя"""
    def check_permission(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> User:
        permissions = get_user_permissions(current_user)
        if permission_code not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Недостаточно прав: требуется право '{permission_code}'",
            )
        return current_user
    
    return check_permission
