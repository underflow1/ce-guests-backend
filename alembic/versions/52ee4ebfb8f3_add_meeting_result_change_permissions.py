"""add_meeting_result_change_permissions

Revision ID: 52ee4ebfb8f3
Revises: 1035ff165731
Create Date: 2026-02-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "52ee4ebfb8f3"
down_revision: Union[str, None] = "1035ff165731"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    # Новые права:
    # - can_change_meeting_result: переквалификация результата встречи (40<->60 и т.п.)
    # - can_rollback_meeting_result: откат результата встречи (40/50/60 -> 30)
    permissions = [
        (
            "e2aa01d9-0c0b-4f3b-a39e-0c12c39dfc3a",
            "can_change_meeting_result",
            "Смена результата встречи",
            "Переквалифицировать результат встречи (смена результата после установки)",
        ),
        (
            "c1f0d1a6-0d9b-4e67-9f2b-5b2d0f6d7f63",
            "can_change_meeting_result_ui",
            "Смена результата встречи (UI)",
            "Показывать возможность переквалифицировать результат встречи",
        ),
        (
            "4a5f6d1a-9b4e-4e52-86c0-9a4b5c6d7e81",
            "can_rollback_meeting_result",
            "Откат результата встречи",
            "Откатить установленный результат встречи (вернуть в состояние 'гость принят')",
        ),
        (
            "b0c1d2e3-f4a5-4b6c-8d9e-0f1a2b3c4d5e",
            "can_rollback_meeting_result_ui",
            "Откат результата встречи (UI)",
            "Показывать возможность отката результата встречи",
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


def downgrade() -> None:
    # Downgrade intentionally does nothing:
    # permissions may already be used in role configuration.
    pass

