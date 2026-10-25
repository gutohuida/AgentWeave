"""traces are kept for a bounded window -- trace_settings.retention_days

Revision ID: 0144
Revises: 0143
Create Date: 2026-10-25 00:00:00.000000

`the-database-stays-fast-as-history-grows` (Tier 2, task `retention`, D4). One nullable column; no
existing row is read or rewritten. NULL means the Hub's default window
(`hub/hub/trace_retention.py`, `DEFAULT_RETENTION_DAYS`), so every existing project takes the
default and a later change of the default reaches every project that never chose its own.

The column deletes nothing by itself: the Hub's maintenance pass (`hub/hub/db_maintenance.py`)
does, in batches, after startup. Deleted spans are not recoverable, and a downgrade does not bring
them back; it drops the column (a plain `DROP COLUMN`, SQLite 3.35+, as `0138`'s downgrade does),
and a Hub on the older code then keeps every span again.

Guarded for a database without the table (an upgrade from an early revision) and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0144"
down_revision = "0143"
branch_labels = None
depends_on = None


def _columns(conn) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns("trace_settings")}


def _present(conn) -> bool:
    return "trace_settings" in set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    conn = op.get_bind()
    if _present(conn) and "retention_days" not in _columns(conn):
        op.add_column("trace_settings", sa.Column("retention_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if _present(conn) and "retention_days" in _columns(conn):
        op.execute(sa.text("ALTER TABLE trace_settings DROP COLUMN retention_days"))
