from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.role import Role
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.api.deps import get_current_active_admin, get_user_permissions
from app.services.auth import get_password_hash, get_current_timestamp
from sqlalchemy.orm import joinedload
from app.models.role_permission import RolePermission

router = APIRouter()


@router.get("/users", response_model=dict)
def get_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Получить список пользователей (только для админов)"""
    users = db.query(User).options(
        joinedload(User.role)
    ).all()
    
    result_users = []
    for user in users:
        permissions = get_user_permissions(user)
        role_info = None
        if user.role:
            role_info = {
                "id": user.role.id,
                "name": user.role.name,
                "interface_type": user.role.interface_type,
            }
        
        result_users.append(
            UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                full_name=user.full_name,
                is_admin=bool(user.is_admin),
                is_active=bool(user.is_active),
                role_id=user.role_id,
                role=role_info,
                permissions=list(permissions),
                created_at=user.created_at,
            )
        )
    
    return {"users": result_users}


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Создать нового пользователя (только для админов)"""
    # Проверяем что пользователь с таким username не существует
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким именем уже существует",
        )
    
    # Проверяем что email не занят (если передан)
    if user_data.email:
        existing_email = db.query(User).filter(User.email == user_data.email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь с таким email уже существует",
            )
    
    # Если пользователь не админ, то роль обязательна
    if not user_data.is_admin and not user_data.role_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для не-админа необходимо указать роль",
        )
    
    # Если указана роль, проверяем что она существует
    if user_data.role_id:
        role = db.query(Role).filter(Role.id == user_data.role_id).first()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Указанная роль не найдена",
            )
    
    password_hash = get_password_hash(user_data.password)
    timestamp = get_current_timestamp()
    
    user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        password_hash=password_hash,
        is_admin=1 if user_data.is_admin else 0,
        is_active=1,
        role_id=user_data.role_id if not user_data.is_admin else None,
        created_at=timestamp,
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Загружаем пользователя с ролью для ответа
    user = db.query(User).options(
        joinedload(User.role)
    ).filter(User.id == user.id).first()
    
    permissions = get_user_permissions(user)
    role_info = None
    if user.role:
        role_info = {
            "id": user.role.id,
            "name": user.role.name,
            "interface_type": user.role.interface_type,
        }
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
        role_id=user.role_id,
        role=role_info,
        permissions=list(permissions),
        created_at=user.created_at,
    )


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Обновить пользователя (только для админов)"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    # Обновляем поля если они переданы
    if user_data.username is not None:
        # Проверяем что новый username не занят другим пользователем
        existing_user = db.query(User).filter(
            User.username == user_data.username,
            User.id != user_id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь с таким именем уже существует",
            )
        user.username = user_data.username
    
    if user_data.email is not None:
        # Проверяем что новый email не занят другим пользователем
        if user_data.email:  # Если email не пустой
            existing_email = db.query(User).filter(
                User.email == user_data.email,
                User.id != user_id
            ).first()
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Пользователь с таким email уже существует",
                )
        user.email = user_data.email
    
    if user_data.full_name is not None:
        user.full_name = user_data.full_name
    
    if user_data.password is not None:
        user.password_hash = get_password_hash(user_data.password)
    
    if user_data.is_admin is not None:
        user.is_admin = 1 if user_data.is_admin else 0
    
    if user_data.is_active is not None:
        user.is_active = 1 if user_data.is_active else 0
    
    if user_data.role_id is not None:
        # Если пользователь становится админом, убираем роль
        if user_data.is_admin is True:
            user.role_id = None
        else:
            # Проверяем что роль существует
            role = db.query(Role).filter(Role.id == user_data.role_id).first()
            if not role:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Указанная роль не найдена",
                )
            user.role_id = user_data.role_id
    
    # Если пользователь не админ и у него нет роли, выдаем ошибку
    if not user.is_admin and user.role_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для не-админа необходимо указать роль",
        )
    
    db.commit()
    db.refresh(user)
    
    # Загружаем пользователя с ролью для ответа
    user = db.query(User).options(
        joinedload(User.role)
    ).filter(User.id == user.id).first()
    
    permissions = get_user_permissions(user)
    role_info = None
    if user.role:
        role_info = {
            "id": user.role.id,
            "name": user.role.name,
            "interface_type": user.role.interface_type,
        }
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
        role_id=user.role_id,
        role=role_info,
        permissions=list(permissions),
        created_at=user.created_at,
    )


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Деактивировать пользователя (только для админов)"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    # Нельзя деактивировать самого себя
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя деактивировать самого себя",
        )
    
    user.is_active = 0
    db.commit()
    
    return {"success": True}


@router.patch("/users/{user_id}/activate", response_model=UserResponse)
def activate_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Активировать пользователя (только для админов)"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    user.is_active = 1
    db.commit()
    
    # Загружаем пользователя с ролью для ответа
    user = db.query(User).options(
        joinedload(User.role)
    ).filter(User.id == user.id).first()
    
    permissions = get_user_permissions(user)
    role_info = None
    if user.role:
        role_info = {
            "id": user.role.id,
            "name": user.role.name,
            "interface_type": user.role.interface_type,
        }
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
        role_id=user.role_id,
        role=role_info,
        permissions=list(permissions),
        created_at=user.created_at,
    )


@router.patch("/users/{user_id}/deactivate", response_model=UserResponse)
def deactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Деактивировать пользователя (только для админов)"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    
    # Нельзя деактивировать самого себя
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя деактивировать самого себя",
        )
    
    user.is_active = 0
    db.commit()
    
    # Загружаем пользователя с ролью для ответа
    user = db.query(User).options(
        joinedload(User.role)
    ).filter(User.id == user.id).first()
    
    permissions = get_user_permissions(user)
    role_info = None
    if user.role:
        role_info = {
            "id": user.role.id,
            "name": user.role.name,
            "interface_type": user.role.interface_type,
        }
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
        role_id=user.role_id,
        role=role_info,
        permissions=list(permissions),
        created_at=user.created_at,
    )
