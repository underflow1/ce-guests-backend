"""drop_entries_current_pass_id

Revision ID: f4c2a91e7b31
Revises: 5b3d9f4a1c2e
Create Date: 2026-02-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4c2a91e7b31"
down_revision: Union[str, None] = "5b3d9f4a1c2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("entries") as batch_op:
        batch_op.drop_constraint("fk_entries_current_pass_id", type_="foreignkey")
        batch_op.drop_column("current_pass_id")


def downgrade() -> None:
    with op.batch_alter_table("entries") as batch_op:
        batch_op.add_column(sa.Column("current_pass_id", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_entries_current_pass_id",
            "passes",
            ["current_pass_id"],
            ["id"],
        )
