"""add per-agent waiting settings

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-07 20:10:00.000000

Nullable with no default: an agent that has never been configured reads as NULL and uses the
built-in default, so no backfill is wanted and none is done.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

_TABLE = "agents"
_COLUMNS = ("permission_timeout_seconds", "question_timeout_seconds")


def _columns(conn) -> set[str] | None:
    """Columns of `agents`, or None when the table is not there.

    Upgrades starting from an early revision reach this migration with only the tables those
    revisions created; `create_all` builds the rest from the model, these columns included.
    """
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None:
        return
    for name in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, sa.Integer(), nullable=True))


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None:
        return
    for name in _COLUMNS:
        if name in existing:
            op.drop_column(_TABLE, name)
