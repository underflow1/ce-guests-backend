"""remove_meeting_results_use_state_reasons

Revision ID: 66a74d60d552
Revises: 393b36373cc6
Create Date: 2026-02-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "66a74d60d552"
down_revision: Union[str, None] = "393b36373cc6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATE_REFUSED = 40
STATE_PENDING = 50


def upgrade() -> None:
    connection = op.get_bind()
    dialect = connection.dialect.name

    # 1) Новый справочник причин по state (40/50)
    op.create_table(
        "result_reasons",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("state", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state", "name", name="uq_result_reasons_state_name"),
    )

    # 2) Перенос причин из meeting_result_reasons -> result_reasons
    # Сохраняем id, чтобы можно было безболезненно перепривязать entry_meeting_reasons.
    if dialect == "sqlite":
        connection.execute(
            sa.text(
                """
                INSERT OR IGNORE INTO result_reasons (id, state, name, is_active, created_at, updated_at, updated_by)
                SELECT
                  r.id,
                  CASE mr.code
                    WHEN 3 THEN :state_refused
                    WHEN 1 THEN :state_pending
                    ELSE NULL
                  END AS state,
                  r.name,
                  r.is_active,
                  r.created_at,
                  r.updated_at,
                  r.updated_by
                FROM meeting_result_reasons r
                JOIN meeting_results mr ON mr.id = r.meeting_result_id
                WHERE mr.code IN (1, 3)
                """
            ),
            {"state_refused": STATE_REFUSED, "state_pending": STATE_PENDING},
        )
    else:
        # PostgreSQL/прочие: используем ON CONFLICT при возможности или NOT EXISTS
        connection.execute(
            sa.text(
                """
                INSERT INTO result_reasons (id, state, name, is_active, created_at, updated_at, updated_by)
                SELECT
                  r.id,
                  CASE mr.code
                    WHEN 3 THEN :state_refused
                    WHEN 1 THEN :state_pending
                    ELSE NULL
                  END AS state,
                  r.name,
                  r.is_active,
                  r.created_at,
                  r.updated_at,
                  r.updated_by
                FROM meeting_result_reasons r
                JOIN meeting_results mr ON mr.id = r.meeting_result_id
                WHERE mr.code IN (1, 3)
                  AND NOT EXISTS (SELECT 1 FROM result_reasons rr WHERE rr.id = r.id)
                """
            ),
            {"state_refused": STATE_REFUSED, "state_pending": STATE_PENDING},
        )

    # 3) Перепривязываем entry_meeting_reasons на новый FK и переименовываем колонку
    # В sqlite делаем через batch.
    with op.batch_alter_table("entry_meeting_reasons") as batch_op:
        batch_op.add_column(sa.Column("result_reason_id", sa.Text(), nullable=True))
    connection.execute(
        sa.text(
            """
            UPDATE entry_meeting_reasons
            SET result_reason_id = meeting_result_reason_id
            """
        )
    )
    with op.batch_alter_table("entry_meeting_reasons") as batch_op:
        batch_op.drop_column("meeting_result_reason_id")
        batch_op.alter_column("result_reason_id", existing_type=sa.Text(), nullable=False)
        batch_op.create_foreign_key(
            "fk_entry_meeting_reasons_result_reason_id",
            "result_reasons",
            ["result_reason_id"],
            ["id"],
        )

    # 4) Удаляем старые таблицы meeting_results/meeting_result_reasons
    op.drop_table("meeting_result_reasons")
    op.drop_table("meeting_results")


def downgrade() -> None:
    # Обратную миграцию не поддерживаем
    pass

