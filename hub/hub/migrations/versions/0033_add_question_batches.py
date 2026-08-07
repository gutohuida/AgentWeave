"""add question batch columns

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-07 19:15:00.000000

Existing rows need no backfill: the server defaults make every question already in the table a
batch of one, which is exactly what it is.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

_TABLE = "questions"
_INDEX_BATCH = "ix_questions_batch_id"


def _columns(conn) -> set[str] | None:
    """Columns of `questions`, or None when the table is not there at all.

    Upgrades that start from an early revision reach this migration with only the tables those
    revisions had created; `questions` is not guaranteed to be one of them. A missing table means
    there is nothing to widen — `create_all` builds it from the model, batch columns included.
    """
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    conn = op.get_bind()
    existing = _columns(conn)
    if existing is None:
        return

    if "batch_id" not in existing:
        op.add_column(_TABLE, sa.Column("batch_id", sa.String(64), nullable=True))
        op.create_index(_INDEX_BATCH, _TABLE, ["batch_id"])
    if "batch_index" not in existing:
        op.add_column(
            _TABLE,
            sa.Column("batch_index", sa.Integer(), nullable=False, server_default="0"),
        )
    if "batch_size" not in existing:
        op.add_column(
            _TABLE,
            sa.Column("batch_size", sa.Integer(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    existing = _columns(conn)
    if existing is None:
        return
    if "batch_size" in existing:
        op.drop_column(_TABLE, "batch_size")
    if "batch_index" in existing:
        op.drop_column(_TABLE, "batch_index")
    if "batch_id" in existing:
        op.drop_index(_INDEX_BATCH, table_name=_TABLE)
        op.drop_column(_TABLE, "batch_id")
