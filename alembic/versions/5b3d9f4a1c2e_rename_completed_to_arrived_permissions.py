"""rename completed to arrived permissions

Revision ID: 5b3d9f4a1c2e
Revises: 0e7d5a2ab34b
Create Date: 2026-02-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5b3d9f4a1c2e"
down_revision: Union[str, None] = "0e7d5a2ab34b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    # Backend permissions
    connection.execute(
        sa.text(
            """
            UPDATE permissions
            SET code = 'can_mark_arrived',
                name = 'Отметка прибытия',
                description = 'Отмечать факт прибытия гостя'
            WHERE code = 'can_mark_completed'
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE permissions
            SET code = 'can_unmark_arrived',
                name = 'Снятие отметки прибытия',
                description = 'Снимать отметку прибытия гостя'
            WHERE code = 'can_unmark_completed'
            """
        )
    )

    # UI permissions
    connection.execute(
        sa.text(
            """
            UPDATE permissions
            SET code = 'can_mark_arrived_ui',
                name = 'Отметка прибытия (UI)',
                description = 'Показывать возможность поставить отметку прибытия'
            WHERE code = 'can_mark_completed_ui'
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE permissions
            SET code = 'can_unmark_arrived_ui',
                name = 'Снятие отметки прибытия (UI)',
                description = 'Показывать возможность снять отметку прибытия'
            WHERE code = 'can_unmark_completed_ui'
            """
        )
    )

    # Notification type code in persisted settings JSON
    connection.execute(
        sa.text(
            """
            UPDATE settings
            SET value = REPLACE(value, '"entry_completed"', '"entry_arrived"')
            WHERE key = 'notifications' AND value LIKE '%entry_completed%'
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            UPDATE permissions
            SET code = 'can_mark_completed',
                name = 'Отметка выполненным',
                description = 'Отмечать гостя как пришедшего'
            WHERE code = 'can_mark_arrived'
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE permissions
            SET code = 'can_unmark_completed',
                name = 'Снятие отметки выполненным',
                description = 'Снимать отметку прихода гостя'
            WHERE code = 'can_unmark_arrived'
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE permissions
            SET code = 'can_mark_completed_ui',
                name = 'Отметка выполненным (UI)',
                description = 'Показывать возможность поставить отметку прихода'
            WHERE code = 'can_mark_arrived_ui'
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE permissions
            SET code = 'can_unmark_completed_ui',
                name = 'Снятие отметки выполненным (UI)',
                description = 'Показывать возможность снять отметку прихода'
            WHERE code = 'can_unmark_arrived_ui'
            """
        )
    )

    connection.execute(
        sa.text(
            """
            UPDATE settings
            SET value = REPLACE(value, '"entry_arrived"', '"entry_completed"')
            WHERE key = 'notifications' AND value LIKE '%entry_arrived%'
            """
        )
    )
