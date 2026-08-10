"""add task transitions

Revision ID: 0052
Revises: 0051
Create Date: 2026-08-10 16:20:00.000000

The append-only history of task status changes.

`tasks.updated_by_run_id` is a single mutable column, so the run that approved a task overwrites
the run that completed it — which makes "did the author approve their own work?" unanswerable in
the schema, not merely unchecked. Rows here are what the author/reviewer rule reads.

No backfill. The table starts empty and a pre-existing task begins its history at its next move.
A synthetic "created as pending" row would state something no one observed, in the one record
whose value is that everything in it happened.

Guarded, like 0038-0051 — and additionally on `tasks`, not only `projects`, because the foreign
key needs it. An upgrade starting from an early revision reaches here with only that revision's
tables; when either is missing there is nothing to hang this table off, and `create_all` builds it
from the model instead.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

_TABLE = "task_transitions"
_INDEX_TASK_SEQUENCE = "ix_task_transitions_task_sequence"
_INDEX_TASK = "ix_task_transitions_task_id"
_INDEX_RUN = "ix_task_transitions_run_id"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    tables = _tables(op.get_bind())
    if _TABLE in tables or "tasks" not in tables or "projects" not in tables:
        return
    op.create_table(
        _TABLE,
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(64), nullable=False, unique=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=False),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(_INDEX_TASK, _TABLE, ["task_id"])
    op.create_index(_INDEX_RUN, _TABLE, ["run_id"])
    op.create_index(_INDEX_TASK_SEQUENCE, _TABLE, ["task_id", "sequence"])


def downgrade() -> None:
    if _TABLE not in _tables(op.get_bind()):
        return
    op.drop_index(_INDEX_TASK_SEQUENCE, table_name=_TABLE)
    op.drop_index(_INDEX_RUN, table_name=_TABLE)
    op.drop_index(_INDEX_TASK, table_name=_TABLE)
    op.drop_table(_TABLE)
