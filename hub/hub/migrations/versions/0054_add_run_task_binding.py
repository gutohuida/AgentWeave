"""add run task binding

Revision ID: 0054
Revises: 0053
Create Date: 2026-08-10 20:10:00.000000

A run did not know what task it was working on. `runs` carried project, agent, session,
conversation, pid and heartbeat — and nothing about the work. So the board depended on agents
remembering to keep it current, not out of carelessness but because the runtime held no link that
would let it know instead (`openspec/changes/2026-08-10-run-task-binding/`).

`task_id` is the binding, set by the runtime at spawn from the cause of the run. `divergence_source_run_id`
is the retry bound: a run carrying it was started in response to another run's divergence, and never
triggers a retry of its own, so no sequence of divergences can start an unbounded number of runs.

Both nullable, and no backfill. Existing runs stay unbound, which reads correctly — they were.
Inventing a binding would put a guess into the record the run-boundary check reads.

Guarded, like 0038-0053.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

_TABLE = "runs"
_TASK_COLUMN = "task_id"
_SOURCE_COLUMN = "divergence_source_run_id"
_INDEX = "ix_runs_task_id"


def _columns(conn):
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None:
        return
    if _TASK_COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_TASK_COLUMN, sa.String(64), nullable=True))
        op.create_index(_INDEX, _TABLE, [_TASK_COLUMN])
    if _SOURCE_COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_SOURCE_COLUMN, sa.String(64), nullable=True))


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None:
        return
    if _SOURCE_COLUMN in existing:
        op.drop_column(_TABLE, _SOURCE_COLUMN)
    if _TASK_COLUMN in existing:
        op.drop_index(_INDEX, table_name=_TABLE)
        op.drop_column(_TABLE, _TASK_COLUMN)
