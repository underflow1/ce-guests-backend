"""merge_heads

Revision ID: 8f5a3c2d1b9e
Revises: 7d2c9f1b6a7c, c4e1a8b2d6f0
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8f5a3c2d1b9e"
down_revision: Union[str, Sequence[str], None] = ("7d2c9f1b6a7c", "c4e1a8b2d6f0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
