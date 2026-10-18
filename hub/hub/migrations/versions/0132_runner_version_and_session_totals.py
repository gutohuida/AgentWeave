"""what a turn's runner reported -- runs.runner_version, turn_usage.session_totals

Revision ID: 0132
Revises: 0131
Create Date: 2026-10-18 00:00:00.000000

F678 (`spdoc-7f874f103d5b`, Tier 2). Two nullable columns. `runs.runner_version` is the CLI version
a run's harness reported (Claude's `system/init` `claude_code_version`). `turn_usage.session_totals`
is the cost and token totals the runner reported for its session at the end of the turn, which a
resumed Claude turn on 2.1.277 or later is differenced against. Existing rows read null: a version
that was not recorded, and a turn with no baseline. Nothing is backfilled or rewritten. Plain `ADD
COLUMN`s; no table is rebuilt.

The downgrade drops both (a plain `DROP COLUMN`, SQLite 3.35+); nothing else reads them.

Guarded for a database without either table (an upgrade from an early revision), and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0132"
down_revision = "0131"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("runs", "runner_version", sa.String(64)),
    ("turn_usage", "session_totals", sa.JSON()),
)


def _existing(table: str) -> set:
    bind = op.get_bind()
    if table not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    for table, column, kind in _COLUMNS:
        existing = _existing(table)
        if existing and column not in existing:
            op.add_column(table, sa.Column(column, kind, nullable=True))


def downgrade() -> None:
    # A plain DROP COLUMN, not a batch rebuild: rebuilding reflects the table's foreign keys, and a
    # database upgraded from an early revision may lack the tables they name.
    for table, column, _ in _COLUMNS:
        if column in _existing(table):
            op.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {column}"))
