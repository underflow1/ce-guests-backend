from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_

from app.database import get_db
from app.models.user import User
from app.models.role import Role
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.schemas.role import RoleCreate, RoleUpdate, RoleResponse, RoleWithPermissions
from app.schemas.permission import PermissionResponse
from app.api.deps import get_current_active_admin, get_user_permissions
from app.services.auth import get_current_timestamp
import uuid

router = APIRouter()


@router.get("/roles", response_model=dict)
def get_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Получить список всех ролей (только для админов)"""
    roles = db.query(Role).options(
        joinedload(Role.role_permissions).joinedload(RolePermission.permission)
    ).all()
    
    return {
        "roles": [
            RoleResponse(
                id=role.id,
                name=role.name,
                description=role.description,
                interface_type=role.interface_type,
                created_at=role.created_at,
                permissions=[
                    PermissionResponse(
                        id=rp.permission.id,
                        code=rp.permission.code,
                        name=rp.permission.name,
                        description=rp.permission.description,
                    )
                    for rp in role.role_permissions
                ],
            )
            for role in roles
        ]
    }


@router.get("/roles/{role_id}", response_model=RoleWithPermissions)
def get_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Получить роль по ID (только для админов)"""
    role = db.query(Role).options(
        joinedload(Role.role_permissions).joinedload(RolePermission.permission)
    ).filter(Role.id == role_id).first()
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Роль не найдена",
        )
    
    return RoleWithPermissions(
        id=role.id,
        name=role.name,
        description=role.description,
        interface_type=role.interface_type,
        created_at=role.created_at,
        permissions=[
            PermissionResponse(
                id=rp.permission.id,
                code=rp.permission.code,
                name=rp.permission.name,
                description=rp.permission.description,
            )
            for rp in role.role_permissions
        ],
        permission_ids=[rp.permission_id for rp in role.role_permissions],
    )


@router.post("/roles", response_model=RoleWithPermissions, status_code=status.HTTP_201_CREATED)
def create_role(
    role_data: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Создать новую роль (только для админов)"""
    # Проверяем что роль с таким именем не существует
    existing_role = db.query(Role).filter(Role.name == role_data.name).first()
    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Роль с таким именем уже существует",
        )
    
    # Проверяем что все переданные права существуют
    if role_data.permission_ids:
        permissions = db.query(Permission).filter(Permission.id.in_(role_data.permission_ids)).all()
        if len(permissions) != len(role_data.permission_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Одно или несколько прав не найдены",
            )
    
    timestamp = get_current_timestamp()
    role = Role(
        id=str(uuid.uuid4()),
        name=role_data.name,
        description=role_data.description,
        interface_type=role_data.interface_type,
        created_at=timestamp,
    )
    
    db.add(role)
    db.flush()  # Получаем ID роли
    
    # Добавляем права к роли
    if role_data.permission_ids:
        for perm_id in role_data.permission_ids:
            role_permission = RolePermission(
                id=str(uuid.uuid4()),
                role_id=role.id,
                permission_id=perm_id,
            )
            db.add(role_permission)
    
    db.commit()
    db.refresh(role)
    
    # Загружаем роль с правами для ответа
    role = db.query(Role).options(
        joinedload(Role.role_permissions).joinedload(RolePermission.permission)
    ).filter(Role.id == role.id).first()
    
    return RoleWithPermissions(
        id=role.id,
        name=role.name,
        description=role.description,
        interface_type=role.interface_type,
        created_at=role.created_at,
        permissions=[
            PermissionResponse(
                id=rp.permission.id,
                code=rp.permission.code,
                name=rp.permission.name,
                description=rp.permission.description,
            )
            for rp in role.role_permissions
        ],
        permission_ids=[rp.permission_id for rp in role.role_permissions],
    )


@router.put("/roles/{role_id}", response_model=RoleWithPermissions)
def update_role(
    role_id: str,
    role_data: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Обновить роль (только для админов)"""
    role = db.query(Role).filter(Role.id == role_id).first()
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Роль не найдена",
        )
    
    # Проверяем что роль не используется пользователями (если меняем имя)
    if role_data.name is not None and role_data.name != role.name:
        existing_role = db.query(Role).filter(
            Role.name == role_data.name,
            Role.id != role_id
        ).first()
        if existing_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Роль с таким именем уже существует",
            )
    
    # Обновляем поля если они переданы
    if role_data.name is not None:
        role.name = role_data.name
    
    if role_data.description is not None:
        role.description = role_data.description
    
    if role_data.interface_type is not None:
        role.interface_type = role_data.interface_type
    
    # Обновляем права если они переданы
    if role_data.permission_ids is not None:
        # Проверяем что все переданные права существуют
        permissions = db.query(Permission).filter(Permission.id.in_(role_data.permission_ids)).all()
        if len(permissions) != len(role_data.permission_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Одно или несколько прав не найдены",
            )
        
        # Удаляем старые права
        db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
        
        # Добавляем новые права
        for perm_id in role_data.permission_ids:
            role_permission = RolePermission(
                id=str(uuid.uuid4()),
                role_id=role.id,
                permission_id=perm_id,
            )
            db.add(role_permission)
    
    db.commit()
    db.refresh(role)
    
    # Загружаем роль с правами для ответа
    role = db.query(Role).options(
        joinedload(Role.role_permissions).joinedload(RolePermission.permission)
    ).filter(Role.id == role.id).first()
    
    return RoleWithPermissions(
        id=role.id,
        name=role.name,
        description=role.description,
        interface_type=role.interface_type,
        created_at=role.created_at,
        permissions=[
            PermissionResponse(
                id=rp.permission.id,
                code=rp.permission.code,
                name=rp.permission.name,
                description=rp.permission.description,
            )
            for rp in role.role_permissions
        ],
        permission_ids=[rp.permission_id for rp in role.role_permissions],
    )


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Удалить роль (только для админов)"""
    role = db.query(Role).filter(Role.id == role_id).first()
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Роль не найдена",
        )
    
    # Проверяем что роль не используется пользователями
    users_with_role = db.query(User).filter(User.role_id == role_id).count()
    if users_with_role > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Невозможно удалить роль: она используется {users_with_role} пользователем(ями)",
        )
    
    db.delete(role)
    db.commit()
    
    return {"success": True}


@router.get("/permissions", response_model=dict)
def get_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    """Получить список всех доступных прав (только для админов)"""
    permissions = db.query(Permission).all()
    
    return {
        "permissions": [
            PermissionResponse(
                id=perm.id,
                code=perm.code,
                name=perm.name,
                description=perm.description,
            )
            for perm in permissions
        ]
    }
