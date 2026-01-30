"""add_passes_and_cancelled_and_permissions

Revision ID: 9b2f0e9a9a3a
Revises: 3f1c9c2d0c7a
Create Date: 2026-01-30

"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b2f0e9a9a3a"
down_revision: Union[str, None] = "3f1c9c2d0c7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    # 1) passes table
    op.create_table(
        "passes",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("entry_id", sa.Text(), nullable=False),
        sa.Column("date", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="ordered"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["entry_id"], ["entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_passes_entry_id", "passes", ["entry_id"])
    op.create_index("idx_passes_entry_date", "passes", ["entry_id", "date"])
    op.create_index("idx_passes_status", "passes", ["status"])

    # 2) entries: is_cancelled + current_pass_id
    with op.batch_alter_table("entries") as batch_op:
        batch_op.add_column(sa.Column("is_cancelled", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("current_pass_id", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_entries_current_pass_id",
            "passes",
            ["current_pass_id"],
            ["id"],
        )

    # 3) permissions
    permissions = [
        # visit cancelled
        ("b8aa7b2a-3b48-4bb9-8caa-49e0f2ed0e1a", "can_mark_cancelled", "Отмена визита", "Отменять визит"),
        ("4dc1a6e0-ff2b-4b1b-8c14-2db46a4c1aa3", "can_unmark_cancelled", "Снятие отмены визита", "Снимать отмену визита"),
        ("c35b9c0e-86f2-4aa5-94f4-8d14802c19f1", "can_mark_cancelled_ui", "Отмена визита (UI)", "Показывать возможность отменить визит"),
        ("0c65e4a6-8aa6-4f56-8f6a-8f6f9e6c2b7c", "can_unmark_cancelled_ui", "Снятие отмены визита (UI)", "Показывать возможность снять отмену визита"),
        # passes
        ("0a1f8d1d-73ee-4f2b-93d3-60a06c468f40", "can_mark_pass", "Заказ пропуска", "Заказывать пропуск"),
        ("57e5e0ce-80e4-41bb-9a93-2c7f1b7d83c7", "can_revoke_pass", "Отзыв пропуска", "Отзывать текущий пропуск"),
        ("2c5d5cdd-35d8-45f1-9e6f-1dc1bcb31f9f", "can_mark_pass_ui", "Заказ пропуска (UI)", "Показывать возможность заказать пропуск"),
        ("1f0f7d8e-0d1a-4b62-98a8-6d18f8f0f1f3", "can_revoke_pass_ui", "Отзыв пропуска (UI)", "Показывать возможность отозвать пропуск"),
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

    # Добавляем новые права роли "Пользователь" по умолчанию (как и остальные права).
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
    # Удаляем привязки прав роли "Пользователь"
    user_role_id = "04033f54-855f-4396-8e54-d46b4c9186e9"
    permission_ids = [
        "b8aa7b2a-3b48-4bb9-8caa-49e0f2ed0e1a",
        "4dc1a6e0-ff2b-4b1b-8c14-2db46a4c1aa3",
        "c35b9c0e-86f2-4aa5-94f4-8d14802c19f1",
        "0c65e4a6-8aa6-4f56-8f6a-8f6f9e6c2b7c",
        "0a1f8d1d-73ee-4f2b-93d3-60a06c468f40",
        "57e5e0ce-80e4-41bb-9a93-2c7f1b7d83c7",
        "2c5d5cdd-35d8-45f1-9e6f-1dc1bcb31f9f",
        "1f0f7d8e-0d1a-4b62-98a8-6d18f8f0f1f3",
    ]
    for pid in permission_ids:
        op.execute(
            sa.text(
                "DELETE FROM role_permissions WHERE role_id = :role_id AND permission_id = :pid"
            ),
            {"role_id": user_role_id, "pid": pid},
        )

    # Удаляем сами права
    op.execute(
        sa.text(
            """
            DELETE FROM permissions WHERE id IN (
                :p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8
            )
            """
        ),
        {
            "p1": permission_ids[0],
            "p2": permission_ids[1],
            "p3": permission_ids[2],
            "p4": permission_ids[3],
            "p5": permission_ids[4],
            "p6": permission_ids[5],
            "p7": permission_ids[6],
            "p8": permission_ids[7],
        },
    )

    # Удаляем колонки и FK из entries (сначала снимаем зависимость от passes)
    with op.batch_alter_table("entries") as batch_op:
        batch_op.drop_constraint("fk_entries_current_pass_id", type_="foreignkey")
        batch_op.drop_column("current_pass_id")
        batch_op.drop_column("is_cancelled")

    # Дропаем passes
    op.drop_index("idx_passes_status", table_name="passes")
    op.drop_index("idx_passes_entry_date", table_name="passes")
    op.drop_index("idx_passes_entry_id", table_name="passes")
    op.drop_table("passes")

