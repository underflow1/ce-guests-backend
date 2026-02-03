"""migrate_user_interface_to_user_new

Revision ID: 6b9c6b0e2a1f
Revises: b2f8c1a0f6f1
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6b9c6b0e2a1f"
down_revision: Union[str, None] = "b2f8c1a0f6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET interface_type = 'user_new'
            WHERE interface_type = 'user'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET interface_type = 'user'
            WHERE interface_type = 'user_new'
            """
        )
    )
