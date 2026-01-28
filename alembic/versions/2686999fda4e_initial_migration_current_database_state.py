"""Initial migration - current database state

Revision ID: 2686999fda4e
Revises: 73c760abdb96
Create Date: 2026-01-28 14:46:28.433369

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2686999fda4e'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создаем таблицы в правильном порядке (учитывая foreign keys)
    
    # 1. Permissions (нет зависимостей)
    op.create_table(
        'permissions',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_permissions_code'), 'permissions', ['code'], unique=True)
    
    # 2. Roles (нет зависимостей)
    op.create_table(
        'roles',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('interface_type', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_roles_name'), 'roles', ['name'], unique=True)
    
    # 3. RolePermissions (зависит от roles и permissions)
    op.create_table(
        'role_permissions',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('role_id', sa.Text(), nullable=False),
        sa.Column('permission_id', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('role_id', 'permission_id', name='uq_role_permission')
    )
    
    # 4. Users (зависит от roles)
    op.create_table(
        'users',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('username', sa.Text(), nullable=False),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('full_name', sa.Text(), nullable=True),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('is_admin', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    
    # 5. Entries (зависит от users)
    op.create_table(
        'entries',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('responsible', sa.Text(), nullable=True),
        sa.Column('datetime', sa.Text(), nullable=False),
        sa.Column('created_by', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=True),
        sa.Column('updated_by', sa.Text(), nullable=True),
        sa.Column('deleted_at', sa.Text(), nullable=True),
        sa.Column('deleted_by', sa.Text(), nullable=True),
        sa.Column('is_completed', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['deleted_by'], ['users.id']),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_entries_datetime', 'entries', ['datetime'])


def downgrade() -> None:
    # Удаляем таблицы в обратном порядке
    op.drop_index('idx_entries_datetime', table_name='entries')
    op.drop_table('entries')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('role_permissions')
    op.drop_index(op.f('ix_roles_name'), table_name='roles')
    op.drop_table('roles')
    op.drop_index(op.f('ix_permissions_code'), table_name='permissions')
    op.drop_table('permissions')
