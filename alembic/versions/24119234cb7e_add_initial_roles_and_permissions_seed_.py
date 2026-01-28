"""Add initial roles and permissions seed data

Revision ID: 24119234cb7e
Revises: 2686999fda4e
Create Date: 2026-01-28 17:43:47.462256

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '24119234cb7e'
down_revision: Union[str, None] = '2686999fda4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Вставляем все права (permissions)
    permissions = [
        ("dd25e9cd-fb28-42ef-a203-a180416faac4", "can_view", "Просмотр записей", "Просматривать записи"),
        ("fe60d460-898c-4960-901a-56a89d1b40b2", "can_add", "Создание записей", "Создавать новые записи"),
        ("81141a2b-5e73-4ca9-8187-eec9b8ab1ec9", "can_edit_entry", "Редактирование записей", "Редактировать записи (все операции изменения)"),
        ("2cff259d-7264-41bf-8b16-263aa5db4dfb", "can_delete_entry", "Удаление записей", "Удалять записи"),
        ("97d9d111-b0cc-4eb8-98de-4289f73bec82", "can_move_ui", "Перемещение записей (UI)", "Показывать возможность перетаскивания записей"),
        ("1ad69070-08a4-46fb-acb4-135f6ae6f171", "can_delete_ui", "Удаление записей (UI)", "Показывать кнопку удаления"),
        ("638c07d1-ffbb-4d0a-a403-4b8060c72b88", "can_mark_completed", "Отметка выполненным", "Отмечать гостя как пришедшего"),
        ("1ef3ee8e-5a16-4fcb-9879-cdbe98551ef1", "can_unmark_completed", "Снятие отметки выполненным", "Снимать отметку прихода гостя"),
        ("9c271740-c13a-408e-bd92-123e7ffca13c", "can_mark_completed_ui", "Отметка выполненным (UI)", "Показывать возможность поставить отметку прихода"),
        ("8b0975bf-f5ef-4656-9a72-6901b0b98982", "can_unmark_completed_ui", "Снятие отметки выполненным (UI)", "Показывать возможность снять отметку прихода"),
        ("37531b33-8d2c-4894-9af9-8e91593a5d08", "can_edit_entry_ui", "Редактирование записей (UI)", "Показывать возможность редактирования ФИО и ответственного"),
    ]
    
    for perm_id, code, name, description in permissions:
        op.execute(
            sa.text("""
                INSERT OR IGNORE INTO permissions (id, code, name, description)
                VALUES (:id, :code, :name, :description)
            """),
            {"id": perm_id, "code": code, "name": name, "description": description}
        )
    
    # Вставляем роли (roles)
    roles = [
        ("04033f54-855f-4396-8e54-d46b4c9186e9", "Пользователь", "Обычный пользователь со всеми правами", "user", "2026-01-22T11:41:30.556239"),
        ("f7ae9b7a-4ffc-4333-9beb-3735169a7db9", "Оперативный дежурный", "Отображается только текущий день. Можно ставить и снимать отметку", "guard", "2026-01-22T14:46:55.133734+03:00"),
    ]
    
    for role_id, name, description, interface_type, created_at in roles:
        op.execute(
            sa.text("""
                INSERT OR IGNORE INTO roles (id, name, description, interface_type, created_at)
                VALUES (:id, :name, :description, :interface_type, :created_at)
            """),
            {"id": role_id, "name": name, "description": description, "interface_type": interface_type, "created_at": created_at}
        )
    
    # Вставляем связи ролей и прав (role_permissions)
    # Роль "Пользователь" - все 11 прав
    user_role_permissions = [
        ("1ad69070-08a4-46fb-acb4-135f6ae6f171", "04033f54-855f-4396-8e54-d46b4c9186e9"),  # can_delete_ui
        ("1ef3ee8e-5a16-4fcb-9879-cdbe98551ef1", "04033f54-855f-4396-8e54-d46b4c9186e9"),  # can_unmark_completed
        ("2cff259d-7264-41bf-8b16-263aa5db4dfb", "04033f54-855f-4396-8e54-d46b4c9186e9"),  # can_delete_entry
        ("37531b33-8d2c-4894-9af9-8e91593a5d08", "04033f54-855f-4396-8e54-d46b4c9186e9"),  # can_edit_entry_ui
        ("638c07d1-ffbb-4d0a-a403-4b8060c72b88", "04033f54-855f-4396-8e54-d46b4c9186e9"),  # can_mark_completed
        ("81141a2b-5e73-4ca9-8187-eec9b8ab1ec9", "04033f54-855f-4396-8e54-d46b4c9186e9"),  # can_edit_entry
        ("8b0975bf-f5ef-4656-9a72-6901b0b98982", "04033f54-855f-4396-8e54-d46b4c9186e9"),  # can_unmark_completed_ui
        ("97d9d111-b0cc-4eb8-98de-4289f73bec82", "04033f54-855f-4396-8e54-d46b4c9186e9"),  # can_move_ui
        ("9c271740-c13a-408e-bd92-123e7ffca13c", "04033f54-855f-4396-8e54-d46b4c9186e9"),  # can_mark_completed_ui
        ("dd25e9cd-fb28-42ef-a203-a180416faac4", "04033f54-855f-4396-8e54-d46b4c9186e9"),  # can_view
        ("fe60d460-898c-4960-901a-56a89d1b40b2", "04033f54-855f-4396-8e54-d46b4c9186e9"),  # can_add
    ]
    
    # Роль "Оперативный дежурный" - 5 прав
    guard_role_permissions = [
        ("1ef3ee8e-5a16-4fcb-9879-cdbe98551ef1", "f7ae9b7a-4ffc-4333-9beb-3735169a7db9"),  # can_unmark_completed
        ("638c07d1-ffbb-4d0a-a403-4b8060c72b88", "f7ae9b7a-4ffc-4333-9beb-3735169a7db9"),  # can_mark_completed
        ("8b0975bf-f5ef-4656-9a72-6901b0b98982", "f7ae9b7a-4ffc-4333-9beb-3735169a7db9"),  # can_unmark_completed_ui
        ("9c271740-c13a-408e-bd92-123e7ffca13c", "f7ae9b7a-4ffc-4333-9beb-3735169a7db9"),  # can_mark_completed_ui
        ("dd25e9cd-fb28-42ef-a203-a180416faac4", "f7ae9b7a-4ffc-4333-9beb-3735169a7db9"),  # can_view
    ]
    
    all_role_permissions = user_role_permissions + guard_role_permissions
    for perm_id, role_id in all_role_permissions:
        rp_id = str(uuid.uuid4())
        op.execute(
            sa.text("""
                INSERT OR IGNORE INTO role_permissions (id, role_id, permission_id)
                VALUES (:id, :role_id, :permission_id)
            """),
            {"id": rp_id, "role_id": role_id, "permission_id": perm_id}
        )


def downgrade() -> None:
    # Удаляем связи ролей и прав
    op.execute("DELETE FROM role_permissions WHERE role_id IN ('04033f54-855f-4396-8e54-d46b4c9186e9', 'f7ae9b7a-4ffc-4333-9beb-3735169a7db9')")
    
    # Удаляем роли
    op.execute("DELETE FROM roles WHERE id IN ('04033f54-855f-4396-8e54-d46b4c9186e9', 'f7ae9b7a-4ffc-4333-9beb-3735169a7db9')")
    
    # Удаляем права
    op.execute("""
        DELETE FROM permissions WHERE id IN (
            'dd25e9cd-fb28-42ef-a203-a180416faac4',
            'fe60d460-898c-4960-901a-56a89d1b40b2',
            '81141a2b-5e73-4ca9-8187-eec9b8ab1ec9',
            '2cff259d-7264-41bf-8b16-263aa5db4dfb',
            '97d9d111-b0cc-4eb8-98de-4289f73bec82',
            '1ad69070-08a4-46fb-acb4-135f6ae6f171',
            '638c07d1-ffbb-4d0a-a403-4b8060c72b88',
            '1ef3ee8e-5a16-4fcb-9879-cdbe98551ef1',
            '9c271740-c13a-408e-bd92-123e7ffca13c',
            '8b0975bf-f5ef-4656-9a72-6901b0b98982',
            '37531b33-8d2c-4894-9af9-8e91593a5d08'
        )
    """)
