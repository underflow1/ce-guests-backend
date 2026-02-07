"""add_entry_state_machine

Revision ID: 1035ff165731
Revises: b950b50f8695
Create Date: 2026-02-06

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1035ff165731"
down_revision: Union[str, None] = "b950b50f8695"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    timestamp = datetime.utcnow().isoformat()

    # 1) Добавляем state в entries
    with op.batch_alter_table("entries") as batch_op:
        batch_op.add_column(sa.Column("state", sa.Integer(), nullable=False, server_default="10"))

    # 2) Бэкофилл state по текущим полям
    # Приоритет:
    # - is_cancelled=1 -> 20
    # - is_completed=0 -> 10
    # - is_completed=1 & meeting_result_id IS NULL -> 30
    # - is_completed=1 & meeting_result.code -> 40/50/60

    # cancelled
    connection.execute(
        sa.text(
            """
            UPDATE entries
            SET state = 20, updated_at = COALESCE(updated_at, :updated_at)
            WHERE is_cancelled = 1
            """
        ),
        {"updated_at": timestamp},
    )

    # draft
    connection.execute(
        sa.text(
            """
            UPDATE entries
            SET state = 10, updated_at = COALESCE(updated_at, :updated_at)
            WHERE is_cancelled = 0 AND is_completed = 0
            """
        ),
        {"updated_at": timestamp},
    )

    # completed without result
    connection.execute(
        sa.text(
            """
            UPDATE entries
            SET state = 30, updated_at = COALESCE(updated_at, :updated_at)
            WHERE is_cancelled = 0 AND is_completed = 1 AND meeting_result_id IS NULL
            """
        ),
        {"updated_at": timestamp},
    )

    # completed with result -> map code to state
    # meeting_results.code: 1=Не оформлен -> 50, 2=Трудоустроен -> 60, 3=Отказ -> 40
    connection.execute(
        sa.text(
            """
            UPDATE entries
            SET state = (
                SELECT
                    CASE mr.code
                        WHEN 1 THEN 50
                        WHEN 2 THEN 60
                        WHEN 3 THEN 40
                        ELSE 30
                    END
                FROM meeting_results mr
                WHERE mr.id = entries.meeting_result_id
            ),
            updated_at = COALESCE(updated_at, :updated_at)
            WHERE is_cancelled = 0 AND is_completed = 1 AND meeting_result_id IS NOT NULL
            """
        ),
        {"updated_at": timestamp},
    )

    # 3) Синхронизируем is_completed/is_cancelled из state для консистентности
    connection.execute(
        sa.text(
            """
            UPDATE entries
            SET
                is_cancelled = CASE WHEN state = 20 THEN 1 ELSE 0 END,
                is_completed = CASE WHEN state IN (30,40,50,60) THEN 1 ELSE 0 END
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("entries") as batch_op:
        batch_op.drop_column("state")

