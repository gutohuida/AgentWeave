"""count a repeated stall in place instead of appending a row per tick

Revision ID: 0087
Revises: 0086
Create Date: 2026-08-24 16:00:00.000000

`loop-notices-and-reacts`, task 2.4, design D6. A loop that ticks while its queue is stalled writes
one `JobRun` per tick saying the same thing. `JobRun` feeds the last-ten-runs view and the
"is this loop running" check, so a stalled loop fills that window with identical rows and a healthy
loop reads as dead. At the five-minute cadence this change adopts, that window is twelve rows an
hour of nothing.

The precedent is `InboundQueueEntry.delivery_attempts`, which chose a counter over duplicate rows
for the identical problem — *"an entry returned five times is indistinguishable from one never
tried."*

**Default 1, not 0.** The column counts firings this row represents, and every row that already
exists represents exactly one. A pre-existing row reading 0 would say a firing that demonstrably
happened did not, and the history view would have to special-case NULL to avoid printing it.
Server-side default so rows written by a process still running old code are also correct.

Guarded for a missing `job_runs` table, like `0033`/`0034`, because an upgrade starting from an
early revision reaches this with only that revision's tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None

_TABLE = "job_runs"
_COLUMN = "tick_count"


def _columns(conn) -> set[str] | None:
    """Columns of `job_runs`, or None when the table is not there."""
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN in existing:
        return
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN not in existing:
        return
    op.drop_column(_TABLE, _COLUMN)
