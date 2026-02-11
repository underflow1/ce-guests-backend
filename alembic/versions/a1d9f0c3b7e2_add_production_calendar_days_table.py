"""add_production_calendar_days_table

Revision ID: a1d9f0c3b7e2
Revises: f4c2a91e7b31
Create Date: 2026-02-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1d9f0c3b7e2"
down_revision: Union[str, None] = "f4c2a91e7b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "production_calendar_days",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("date", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("is_workday", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date"),
    )
    op.create_index(
        "idx_production_calendar_days_year",
        "production_calendar_days",
        ["year"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_production_calendar_days_year", table_name="production_calendar_days")
    op.drop_table("production_calendar_days")
