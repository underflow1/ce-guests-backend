"""add_token_lookup_hash_to_refresh_tokens

Revision ID: e13b8c4a9d2f
Revises: a1d9f0c3b7e2
Create Date: 2026-02-11 18:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e13b8c4a9d2f"
down_revision: Union[str, None] = "a1d9f0c3b7e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("token_lookup_hash", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_refresh_tokens_token_lookup_hash"),
        "refresh_tokens",
        ["token_lookup_hash"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_refresh_tokens_token_lookup_hash"), table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "token_lookup_hash")
