"""a check run records when it got its slot -- task_check_runs.slot_at

Revision ID: 0164
Revises: 0163
Create Date: 2026-11-05 22:40:00.000000

`the-build-card-shows-where-check-time-went` (FR-1). A run's `started_at` is when it was queued;
how long it then waited for one of the check slots was held only in memory, so it was lost at a
Hub restart. `slot_at`, nullable, is when the run got its slot. Additive, on live data: no backfill,
and every existing row reads null, which the tally takes as an unknown wait. No CHECK, so the large
table is not recreated.

Rollback: the downgrade drops the column (plain `DROP COLUMN`, SQLite 3.35+, as `0162` does); the
slot wait is then unknown again, as before this change.

Guarded for a database without the table (an upgrade from an early revision) and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0164"
down_revision = "0163"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    columns = _columns("task_check_runs")
    if columns and "slot_at" not in columns:
        op.add_column("task_check_runs", sa.Column("slot_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    if "slot_at" in _columns("task_check_runs"):
        op.execute(sa.text("ALTER TABLE task_check_runs DROP COLUMN slot_at"))
