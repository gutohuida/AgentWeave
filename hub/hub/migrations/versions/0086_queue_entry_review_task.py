"""carry "this turn is a review of task X" through the inbound queue

Revision ID: 0086
Revises: 0085
Create Date: 2026-08-24 10:00:00.000000

`2026-08-23-a-reviewer-can-see-the-work`, task 4.1. A review turn's workspace is a detached
checkout of the commit under review rather than the agent's own worktree, and the scheduler is
what starts the turn — so which task is being reviewed has to survive the queue, exactly as
`task_id` (`0060`) and `divergence_source_run_id` (`0079`) already do. Anything held only at the
request would be gone by the time the turn actually starts.

Deliberately a separate column from `task_id` rather than a flag beside it. They answer different
questions: `task_id` is the task this run is *working on* and binds the run to it, while this is
the task whose finished work the run is *inspecting*. Collapsing them would make a reviewer look
like the task's author to every consumer of the binding, which is the specific confusion the
change exists to prevent.

Guarded for a missing `inbound_queue_entries` table, like `0033`/`0034`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None

_TABLE = "inbound_queue_entries"
_COLUMN = "review_task_id"


def _columns(conn) -> set[str] | None:
    """Columns of `inbound_queue_entries`, or None when the table is not there."""
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN in existing:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(64), nullable=True))


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN not in existing:
        return
    op.drop_column(_TABLE, _COLUMN)
