"""deactivate_no_show_meeting_result

Revision ID: b950b50f8695
Revises: c81584830aca
Create Date: 2026-02-05

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b950b50f8695"
down_revision: Union[str, None] = "c81584830aca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    timestamp = datetime.utcnow().isoformat()

    # Удаляем статус "Встреча не состоялась" если он существует
    # Этот статус не нужен - отмена встречи определяется через is_cancelled
    
    # Сначала находим ID статуса
    result_row = connection.execute(
        sa.text(
            """
            SELECT id FROM meeting_results
            WHERE lower(name) = lower(:name)
            """
        ),
        {"name": "Встреча не состоялась"},
    ).fetchone()
    
    if result_row:
        result_id = result_row[0]
        
        # Убираем ссылки на этот статус из entries (устанавливаем meeting_result_id = NULL)
        connection.execute(
            sa.text(
                """
                UPDATE entries
                SET meeting_result_id = NULL, meeting_result_reason_id = NULL, updated_at = :updated_at
                WHERE meeting_result_id = :result_id
                """
            ),
            {"result_id": result_id, "updated_at": timestamp},
        )
        
        # Удаляем связанные причины (reasons) - они удалятся каскадно если есть CASCADE
        connection.execute(
            sa.text(
                """
                DELETE FROM meeting_result_reasons
                WHERE meeting_result_id = :result_id
                """
            ),
            {"result_id": result_id},
        )
        
        # Удаляем сам статус
        connection.execute(
            sa.text(
                """
                DELETE FROM meeting_results
                WHERE id = :result_id
                """
            ),
            {"result_id": result_id},
        )


def downgrade() -> None:
    # При откате не восстанавливаем - статус не нужен
    pass
