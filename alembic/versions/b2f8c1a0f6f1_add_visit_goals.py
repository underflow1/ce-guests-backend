"""add_visit_goals

Revision ID: b2f8c1a0f6f1
Revises: 9b2f0e9a9a3a
Create Date: 2026-02-02

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2f8c1a0f6f1"
down_revision: Union[str, None] = "9b2f0e9a9a3a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "visit_goals",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("idx_visit_goals_is_active", "visit_goals", ["is_active"])

    op.create_table(
        "entry_visit_goals",
        sa.Column("entry_id", sa.Text(), nullable=False),
        sa.Column("visit_goal_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["visit_goal_id"], ["visit_goals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("entry_id", "visit_goal_id"),
    )
    op.create_index("idx_entry_visit_goals_entry_id", "entry_visit_goals", ["entry_id"])
    op.create_index("idx_entry_visit_goals_goal_id", "entry_visit_goals", ["visit_goal_id"])

    now = datetime.utcnow().isoformat()
    op.bulk_insert(
        sa.table(
            "visit_goals",
            sa.column("id", sa.Text()),
            sa.column("name", sa.Text()),
            sa.column("is_active", sa.Integer()),
            sa.column("created_at", sa.Text()),
        ),
        [
            {"id": "f2b5a6e6-1f1f-4a8f-9a2a-0d4f7b4b2d11", "name": "Собеседование", "is_active": 1, "created_at": now},
            {"id": "b9df7b40-7a2c-4f8b-8b2d-4d67c2cce2c9", "name": "Трудоустройство", "is_active": 1, "created_at": now},
        ],
    )


def downgrade() -> None:
    op.drop_index("idx_entry_visit_goals_goal_id", table_name="entry_visit_goals")
    op.drop_index("idx_entry_visit_goals_entry_id", table_name="entry_visit_goals")
    op.drop_table("entry_visit_goals")
    op.drop_index("idx_visit_goals_is_active", table_name="visit_goals")
    op.drop_table("visit_goals")
