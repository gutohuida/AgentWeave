"""add agent lifecycle

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-08 17:10:00.000000

An agent is archived, never deleted. Every existing agent is `open`, which is also the default
for anything created afterwards, so the backfill is unconditional and the column is NOT NULL from
the start — there is no such thing as an agent with no lifecycle.

The CHECK constraint is deliberately not added to the existing table. SQLite cannot add one
without rebuilding the table, and a batch rebuild of `agents` here would have to reproduce every
column and foreign key this revision happens to know about — which silently drops anything a
later revision adds. `create_all` builds the constraint for fresh databases from the model, and
the write paths reject any other value, so an upgraded database is protected by the same rule
without the rebuild.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

_TABLE = "agents"


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
    conn = op.get_bind()
    existing = _columns(conn)
    if existing is None:
        return
    if "lifecycle" not in existing:
        op.add_column(
            _TABLE,
            sa.Column("lifecycle", sa.String(16), nullable=False, server_default="open"),
        )
    if "archived_at" not in existing:
        op.add_column(_TABLE, sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    # Rows that predate the column read as NULL on some backends despite the server default.
    conn.execute(sa.text("UPDATE agents SET lifecycle = 'open' WHERE lifecycle IS NULL"))


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None:
        return
    for name in ("archived_at", "lifecycle"):
        if name in existing:
            op.drop_column(_TABLE, name)
