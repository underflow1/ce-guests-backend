"""add_meeting_result_code

Revision ID: c81584830aca
Revises: 1c7f5a2b9e41
Create Date: 2026-02-05

"""
from typing import Sequence, Union
from datetime import datetime
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c81584830aca"
down_revision: Union[str, None] = "1c7f5a2b9e41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    timestamp = datetime.utcnow().isoformat()

    # 1) Добавляем колонку code в meeting_results
    with op.batch_alter_table("meeting_results") as batch_op:
        batch_op.add_column(sa.Column("code", sa.Integer(), nullable=True))

    # 2) Заполняем коды для существующих статусов
    status_codes = {
        "Не оформлен": 1,
        "Трудоустроен": 2,
        "Отказ": 3,
    }

    for name, code in status_codes.items():
        connection.execute(
            sa.text(
                """
                UPDATE meeting_results
                SET code = :code, updated_at = :updated_at
                WHERE lower(name) = lower(:name) AND code IS NULL
                """
            ),
            {"name": name, "code": code, "updated_at": timestamp},
        )
    
    # 3) Деактивируем все статусы с code <= 0 (служебные статусы, не для выбора как результат встречи)
    connection.execute(
        sa.text(
            """
            UPDATE meeting_results
            SET is_active = 0, updated_at = :updated_at
            WHERE code IS NOT NULL AND code <= 0 AND is_active = 1
            """
        ),
        {"updated_at": timestamp},
    )



def downgrade() -> None:
    # Удаляем колонку code
    with op.batch_alter_table("meeting_results") as batch_op:
        batch_op.drop_column("code")
