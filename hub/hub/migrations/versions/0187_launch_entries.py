"""What a run launched with, and the entry a task keeps -- runs.runner_id/model/effort,
tasks.builder_entry/checker_entry

Revision ID: 0187
Revises: 0186
Create Date: 2026-11-19 16:00:00.000000

`a-profile-runs-each-task-on-a-runner-and-model-chosen-from-its-pool`, FR-7 and FR-12. Five
nullable columns:

- `runs.runner_id`, `runs.model`, `runs.effort`: the runner record, model and reasoning effort a
  run launched with, written at spawn.
- `tasks.builder_entry`, `tasks.checker_entry`: the pool entry (`{agent, runner_id, effort}`) the
  task's builder and checker runs launch with, fixed when the first of each starts.

Runs on the operator's :8000 data at its next restart. Adds columns only; no row is changed and
nothing is backfilled: what an earlier run launched with was not recorded, and a guess would be
indistinguishable from a record. A task with no entry resolves one when its next run starts, as a
task built after the change does.

Rollback: the downgrade drops the five columns, losing only what runs since recorded and the
entries tasks kept; code before this change reads none of them. Guarded for a missing table, as
0033/0034 are.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0187"
down_revision = "0186"
branch_labels = None
depends_on = None

_COLUMNS = {
    "runs": (
        ("runner_id", lambda: sa.String(64)),
        ("model", lambda: sa.String(256)),
        ("effort", lambda: sa.String(32)),
    ),
    "tasks": (
        ("builder_entry", lambda: sa.JSON()),
        ("checker_entry", lambda: sa.JSON()),
    ),
}


def _columns(conn, table: str) -> set[str] | None:
    inspector = sa.inspect(conn)
    if table not in inspector.get_table_names():
        return None
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    for table, columns in _COLUMNS.items():
        present = _columns(conn, table)
        if present is None:
            continue
        missing = [(name, kind) for name, kind in columns if name not in present]
        if not missing:
            continue
        with op.batch_alter_table(table, recreate="never") as batch_op:
            for name, kind in missing:
                batch_op.add_column(sa.Column(name, kind(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    for table, columns in _COLUMNS.items():
        present = _columns(conn, table)
        if present is None:
            continue
        with op.batch_alter_table(table) as batch_op:
            for name, _ in columns:
                if name in present:
                    batch_op.drop_column(name)
