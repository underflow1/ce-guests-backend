"""reuse_reasons_with_state_options

Revision ID: 0e7d5a2ab34b
Revises: 66a74d60d552
Create Date: 2026-02-06

"""
from typing import Sequence, Union, Dict

from alembic import op
import sqlalchemy as sa


revision: str = "0e7d5a2ab34b"
down_revision: Union[str, None] = "66a74d60d552"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _norm(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def upgrade() -> None:
    connection = op.get_bind()
    dialect = connection.dialect.name

    # 1) Единый справочник причин
    op.create_table(
        "reasons",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_reasons_name"),
    )

    # 2) Разрешенные причины для state (many-to-many)
    op.create_table(
        "state_reason_options",
        sa.Column("state", sa.Integer(), nullable=False),
        sa.Column("reason_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["reason_id"], ["reasons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("state", "reason_id"),
        sa.UniqueConstraint("state", "reason_id", name="uq_state_reason_options_state_reason"),
    )

    # 3) Переносим данные из result_reasons в reasons + state_reason_options с дедупликацией по имени
    rows = connection.execute(
        sa.text(
            "SELECT id, state, name, is_active, created_at, updated_at, updated_by FROM result_reasons"
        )
    ).fetchall()

    # group by normalized name
    groups: Dict[str, list] = {}
    for r in rows:
        n = _norm(r.name)
        groups.setdefault(n, []).append(r)

    old_to_new: Dict[str, str] = {}
    for _, items in groups.items():
        # canonical = smallest id (stable)
        items_sorted = sorted(items, key=lambda x: str(x.id))
        canonical = items_sorted[0]
        new_id = str(canonical.id)

        # merge flags conservatively
        is_active = 1 if any(int(i.is_active) == 1 for i in items_sorted) else 0
        created_at = min(str(i.created_at) for i in items_sorted if i.created_at is not None)
        updated_at = None
        updated_by = None
        # keep latest updated_at if present
        updated_candidates = [(i.updated_at, i.updated_by) for i in items_sorted if i.updated_at is not None]
        if updated_candidates:
            updated_candidates.sort(key=lambda t: str(t[0]))
            updated_at, updated_by = updated_candidates[-1]

        connection.execute(
            sa.text(
                """
                INSERT INTO reasons (id, name, is_active, created_at, updated_at, updated_by)
                VALUES (:id, :name, :is_active, :created_at, :updated_at, :updated_by)
                """
            ),
            {
                "id": new_id,
                "name": str(canonical.name).strip(),
                "is_active": is_active,
                "created_at": created_at,
                "updated_at": str(updated_at) if updated_at is not None else None,
                "updated_by": str(updated_by) if updated_by is not None else None,
            },
        )

        for i in items_sorted:
            old_to_new[str(i.id)] = new_id

    # fill options (dedupe by PK)
    for r in rows:
        new_id = old_to_new.get(str(r.id))
        if not new_id:
            continue
        if dialect == "sqlite":
            connection.execute(
                sa.text(
                    "INSERT OR IGNORE INTO state_reason_options (state, reason_id) VALUES (:state, :reason_id)"
                ),
                {"state": int(r.state), "reason_id": new_id},
            )
        elif dialect == "postgresql":
            connection.execute(
                sa.text(
                    """
                    INSERT INTO state_reason_options (state, reason_id)
                    VALUES (:state, :reason_id)
                    ON CONFLICT (state, reason_id) DO NOTHING
                    """
                ),
                {"state": int(r.state), "reason_id": new_id},
            )
        else:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO state_reason_options (state, reason_id)
                    SELECT :state, :reason_id
                    WHERE NOT EXISTS (
                      SELECT 1 FROM state_reason_options WHERE state=:state AND reason_id=:reason_id
                    )
                    """
                ),
                {"state": int(r.state), "reason_id": new_id},
            )

    # 4) entry_meeting_reasons: result_reason_id -> reason_id с учетом дедупа
    with op.batch_alter_table("entry_meeting_reasons") as batch_op:
        batch_op.add_column(sa.Column("reason_id", sa.Text(), nullable=True))

    erows = connection.execute(
        sa.text("SELECT entry_id, result_reason_id FROM entry_meeting_reasons")
    ).fetchall()
    for er in erows:
        old_id = str(er.result_reason_id)
        new_id = old_to_new.get(old_id)
        if not new_id:
            # если по какой-то причине маппинга нет, просто пропускаем (в конце constraint упадет и это хорошо)
            continue
        connection.execute(
            sa.text(
                "UPDATE entry_meeting_reasons SET reason_id=:reason_id WHERE entry_id=:entry_id"
            ),
            {"reason_id": new_id, "entry_id": str(er.entry_id)},
        )

    with op.batch_alter_table("entry_meeting_reasons") as batch_op:
        batch_op.drop_column("result_reason_id")
        batch_op.alter_column("reason_id", existing_type=sa.Text(), nullable=False)
        batch_op.create_foreign_key(
            "fk_entry_meeting_reasons_reason_id",
            "reasons",
            ["reason_id"],
            ["id"],
        )

    # 5) Удаляем старый справочник
    op.drop_table("result_reasons")


def downgrade() -> None:
    # Обратную миграцию не поддерживаем
    pass

