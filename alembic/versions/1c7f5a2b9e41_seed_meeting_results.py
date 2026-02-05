"""seed_meeting_results

Revision ID: 1c7f5a2b9e41
Revises: 8f5a3c2d1b9e
Create Date: 2026-02-03

"""
from typing import Sequence, Union
from datetime import datetime
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1c7f5a2b9e41"
down_revision: Union[str, None] = "8f5a3c2d1b9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RESULTS = {
    "Не оформлен": [
        "Документы в процессе проверки СБ",
        "Дополнительный запрос документов от О.К",
    ],
    "Трудоустроен": [],
    "Отказ": [
        "не прошел СБ",
        "проблемы со здоровьем",
        "Не отвечает ожиданиям Заказчика",
    ],
}


def _upsert_result(conn, name: str, timestamp: str) -> str:
    row = conn.execute(
        sa.text(
            """
            SELECT id, is_active
            FROM meeting_results
            WHERE lower(name) = lower(:name)
            """
        ),
        {"name": name},
    ).fetchone()

    if row:
        if not row[1]:
            conn.execute(
                sa.text(
                    """
                    UPDATE meeting_results
                    SET is_active = 1, updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {"id": row[0], "updated_at": timestamp},
            )
        return row[0]

    new_id = str(uuid.uuid4())
    conn.execute(
        sa.text(
            """
            INSERT INTO meeting_results (id, name, is_active, created_at, updated_at, updated_by)
            VALUES (:id, :name, 1, :created_at, NULL, NULL)
            """
        ),
        {"id": new_id, "name": name, "created_at": timestamp},
    )
    return new_id


def _upsert_reason(conn, result_id: str, name: str, timestamp: str) -> None:
    row = conn.execute(
        sa.text(
            """
            SELECT id, is_active
            FROM meeting_result_reasons
            WHERE meeting_result_id = :result_id AND lower(name) = lower(:name)
            """
        ),
        {"result_id": result_id, "name": name},
    ).fetchone()

    if row:
        if not row[1]:
            conn.execute(
                sa.text(
                    """
                    UPDATE meeting_result_reasons
                    SET is_active = 1, updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {"id": row[0], "updated_at": timestamp},
            )
        return

    conn.execute(
        sa.text(
            """
            INSERT INTO meeting_result_reasons (
                id, meeting_result_id, name, is_active, created_at, updated_at, updated_by
            )
            VALUES (:id, :result_id, :name, 1, :created_at, NULL, NULL)
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "result_id": result_id,
            "name": name,
            "created_at": timestamp,
        },
    )


def upgrade() -> None:
    connection = op.get_bind()
    timestamp = datetime.utcnow().isoformat()

    for result_name, reasons in RESULTS.items():
        result_id = _upsert_result(connection, result_name, timestamp)
        for reason_name in reasons:
            _upsert_reason(connection, result_id, reason_name, timestamp)


def downgrade() -> None:
    connection = op.get_bind()

    for result_name, reasons in RESULTS.items():
        row = connection.execute(
            sa.text(
                """
                SELECT id FROM meeting_results
                WHERE lower(name) = lower(:name)
                """
            ),
            {"name": result_name},
        ).fetchone()
        if not row:
            continue
        result_id = row[0]
        if reasons:
            for reason_name in reasons:
                connection.execute(
                    sa.text(
                        """
                        UPDATE meeting_result_reasons
                        SET is_active = 0
                        WHERE meeting_result_id = :result_id AND lower(name) = lower(:name)
                        """
                    ),
                    {"result_id": result_id, "name": reason_name},
                )
        connection.execute(
            sa.text(
                """
                UPDATE meeting_results
                SET is_active = 0
                WHERE id = :id
                """
            ),
            {"id": result_id},
        )
