"""rename_interface_types

Revision ID: 7d2c9f1b6a7c
Revises: 6b9c6b0e2a1f
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7d2c9f1b6a7c"
down_revision: Union[str, None] = "6b9c6b0e2a1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET interface_type = 'user'
            WHERE interface_type IN ('user_new', 'user')
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET interface_type = 'duty_officer'
            WHERE interface_type = 'guard'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET interface_type = 'user_new'
            WHERE interface_type = 'user'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET interface_type = 'guard'
            WHERE interface_type = 'duty_officer'
            """
        )
    )
