"""drop_entry_status_fields_use_state

Revision ID: 393b36373cc6
Revises: 52ee4ebfb8f3
Create Date: 2026-02-06

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "393b36373cc6"
down_revision: Union[str, None] = "52ee4ebfb8f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    dialect = connection.dialect.name

    # 1) Создаем таблицу для причины результата встречи (вместо meeting_result_reason_id в entries)
    op.create_table(
        "entry_meeting_reasons",
        sa.Column("entry_id", sa.Text(), nullable=False),
        sa.Column("meeting_result_reason_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_result_reason_id"], ["meeting_result_reasons.id"]),
        sa.PrimaryKeyConstraint("entry_id"),
    )

    # 2) Переносим meeting_result_reason_id в новую таблицу (только для state=40/50/60)
    # Примечание: если данных нет — просто ничего не вставится.
    if dialect == "sqlite":
        connection.execute(
            sa.text(
                """
                INSERT OR IGNORE INTO entry_meeting_reasons (entry_id, meeting_result_reason_id)
                SELECT id, meeting_result_reason_id
                FROM entries
                WHERE meeting_result_reason_id IS NOT NULL
                """
            )
        )
    elif dialect == "postgresql":
        connection.execute(
            sa.text(
                """
                INSERT INTO entry_meeting_reasons (entry_id, meeting_result_reason_id)
                SELECT id, meeting_result_reason_id
                FROM entries
                WHERE meeting_result_reason_id IS NOT NULL
                ON CONFLICT (entry_id) DO NOTHING
                """
            )
        )
    else:
        # На прочих СУБД делаем перенос без дублей через NOT EXISTS
        connection.execute(
            sa.text(
                """
                INSERT INTO entry_meeting_reasons (entry_id, meeting_result_reason_id)
                SELECT e.id, e.meeting_result_reason_id
                FROM entries e
                WHERE e.meeting_result_reason_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM entry_meeting_reasons r WHERE r.entry_id = e.id
                  )
                """
            )
        )

    # 3) Удаляем ненужные колонки из entries (state становится первоисточником)
    with op.batch_alter_table("entries") as batch_op:
        batch_op.drop_column("meeting_result_reason_id")
        batch_op.drop_column("meeting_result_id")
        batch_op.drop_column("is_cancelled")
        batch_op.drop_column("is_completed")


def downgrade() -> None:
    # Обратную миграцию не поддерживаем (упрощение)
    # При необходимости можно восстановить колонки и заполнить их из state.
    pass

