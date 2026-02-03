"""add_meeting_results_and_permissions

Revision ID: c4e1a8b2d6f0
Revises: b2f8c1a0f6f1
Create Date: 2026-02-03

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4e1a8b2d6f0"
down_revision: Union[str, None] = "b2f8c1a0f6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    op.create_table(
        "meeting_results",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_meeting_results_name"),
    )
    op.create_index("idx_meeting_results_is_active", "meeting_results", ["is_active"])

    op.create_table(
        "meeting_result_reasons",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("meeting_result_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["meeting_result_id"], ["meeting_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_result_id", "name", name="uq_meeting_result_reason_name"),
    )
    op.create_index("idx_meeting_result_reasons_is_active", "meeting_result_reasons", ["is_active"])

    with op.batch_alter_table("entries") as batch_op:
        batch_op.add_column(sa.Column("meeting_result_id", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("meeting_result_reason_id", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_entries_meeting_result_id",
            "meeting_results",
            ["meeting_result_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_entries_meeting_result_reason_id",
            "meeting_result_reasons",
            ["meeting_result_reason_id"],
            ["id"],
        )

    permissions = [
        (
            "5b7d6f7c-2b1c-4b6f-9a37-8f9a6d1a7a21",
            "can_set_meeting_result",
            "Установка результата встречи",
            "Устанавливать результат встречи",
        ),
        (
            "a4b2e1f9-0c5d-4f21-9f4b-1e0d3f9d7c54",
            "can_set_meeting_result_ui",
            "Установка результата встречи (UI)",
            "Показывать возможность установить результат встречи",
        ),
    ]

    for perm_id, code, name, description in permissions:
        connection.execute(
            sa.text(
                """
                INSERT OR IGNORE INTO permissions (id, code, name, description)
                VALUES (:id, :code, :name, :description)
                """
            ),
            {"id": perm_id, "code": code, "name": name, "description": description},
        )

    user_role_id = "04033f54-855f-4396-8e54-d46b4c9186e9"
    for perm_id, _, _, _ in permissions:
        rp_id = str(uuid.uuid4())
        connection.execute(
            sa.text(
                """
                INSERT OR IGNORE INTO role_permissions (id, role_id, permission_id)
                VALUES (:id, :role_id, :permission_id)
                """
            ),
            {"id": rp_id, "role_id": user_role_id, "permission_id": perm_id},
        )


def downgrade() -> None:
    user_role_id = "04033f54-855f-4396-8e54-d46b4c9186e9"
    permission_ids = [
        "5b7d6f7c-2b1c-4b6f-9a37-8f9a6d1a7a21",
        "a4b2e1f9-0c5d-4f21-9f4b-1e0d3f9d7c54",
    ]

    for pid in permission_ids:
        op.execute(
            sa.text(
                "DELETE FROM role_permissions WHERE role_id = :role_id AND permission_id = :pid"
            ),
            {"role_id": user_role_id, "pid": pid},
        )

    op.execute(
        sa.text(
            """
            DELETE FROM permissions WHERE id IN (:p1,:p2)
            """
        ),
        {
            "p1": permission_ids[0],
            "p2": permission_ids[1],
        },
    )

    with op.batch_alter_table("entries") as batch_op:
        batch_op.drop_constraint("fk_entries_meeting_result_reason_id", type_="foreignkey")
        batch_op.drop_constraint("fk_entries_meeting_result_id", type_="foreignkey")
        batch_op.drop_column("meeting_result_reason_id")
        batch_op.drop_column("meeting_result_id")

    op.drop_index("idx_meeting_result_reasons_is_active", table_name="meeting_result_reasons")
    op.drop_table("meeting_result_reasons")

    op.drop_index("idx_meeting_results_is_active", table_name="meeting_results")
    op.drop_table("meeting_results")
