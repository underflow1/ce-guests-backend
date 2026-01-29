"""add_can_move_entry_permission

Revision ID: 2482248eff76
Revises: de970440344d
Create Date: 2026-01-29 12:00:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2482248eff76'
down_revision: Union[str, None] = 'de970440344d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Получаем connection для работы с БД
    connection = op.get_bind()
    
    # Добавляем новое право can_move_entry
    permission_id = "7eb59bf7-a6bb-4be7-9138-6f077afcf4ae"
    connection.execute(
        sa.text("""
            INSERT OR IGNORE INTO permissions (id, code, name, description)
            VALUES (:id, :code, :name, :description)
        """),
        {
            "id": permission_id,
            "code": "can_move_entry",
            "name": "Перемещение записей",
            "description": "Перемещать записи (изменять дату/время через drag&drop)"
        }
    )
    
    # Добавляем право can_move_entry роли "Пользователь" (у которой уже есть can_move_ui)
    user_role_id = "04033f54-855f-4396-8e54-d46b4c9186e9"
    rp_id = str(uuid.uuid4())
    connection.execute(
        sa.text("""
            INSERT OR IGNORE INTO role_permissions (id, role_id, permission_id)
            VALUES (:id, :role_id, :permission_id)
        """),
        {"id": rp_id, "role_id": user_role_id, "permission_id": permission_id}
    )


def downgrade() -> None:
    # Удаляем связь роли и права
    user_role_id = "04033f54-855f-4396-8e54-d46b4c9186e9"
    permission_id = "7eb59bf7-a6bb-4be7-9138-6f077afcf4ae"
    op.execute(
        sa.text("""
            DELETE FROM role_permissions 
            WHERE role_id = :role_id AND permission_id = :permission_id
        """),
        {"role_id": user_role_id, "permission_id": permission_id}
    )
    
    # Удаляем право
    op.execute(
        sa.text("DELETE FROM permissions WHERE id = :id"),
        {"id": "7eb59bf7-a6bb-4be7-9138-6f077afcf4ae"}
    )
