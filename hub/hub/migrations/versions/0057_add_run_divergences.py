"""add run divergences

Revision ID: 0057
Revises: 0056
Create Date: 2026-08-10 20:16:00.000000

The record of a bound run ending without its task moving.

A table rather than only an SSE event, because an event vanishes: the operator needs to see what
happened while they were not watching, and "how often does this agent drop its work?" is a question
worth being able to ask. B3's evidence model reads the same rows.

`resolved_at` is the one mutable field — a divergence is an open condition, not a verdict, and long
work spanning several turns opens one that closes as soon as the work reaches the ledger. The row
survives its own resolution; nothing here is deleted.

Ordered by an autoincrement `sequence`, like `task_transitions` and `inbound_queue_entries`. 0052
learned this the expensive way: rows staged in one flush shared `created_at` to the microsecond and
a random id decided what order the history read in.

No backfill — the table starts empty, and a divergence that was never observed cannot be invented.

Guarded on `tasks` and `projects` as well as on its own absence, like 0052: an upgrade starting from
an early revision reaches here with only that revision's tables, and when the foreign keys have
nothing to hang off, `create_all` builds the table from the model instead.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

_TABLE = "run_divergences"
_INDEX_RUN = "ix_run_divergences_run_id"
_INDEX_AGENT = "ix_run_divergences_agent"
_INDEX_TASK = "ix_run_divergences_task_id"
_INDEX_PROJECT_TASK = "ix_run_divergences_project_task"
_INDEX_PROJECT_RESOLVED = "ix_run_divergences_project_resolved"


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
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("agent", sa.String(64), nullable=False),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("task_status_at_end", sa.String(32), nullable=False),
        sa.Column("run_exit_status", sa.String(32), nullable=False),
        sa.Column("policy_applied", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("response_run_id", sa.String(64), nullable=True),
        sa.Column("previous_assignee", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "policy_applied IN ('surface', 'retry', 'escalate')",
            name="ck_run_divergences_policy",
        ),
        sa.CheckConstraint(
            "outcome IN ('surfaced', 'retried', 'escalated')",
            name="ck_run_divergences_outcome",
        ),
    )
    op.create_index(_INDEX_RUN, _TABLE, ["run_id"])
    op.create_index(_INDEX_AGENT, _TABLE, ["agent"])
    op.create_index(_INDEX_TASK, _TABLE, ["task_id"])
    op.create_index(_INDEX_PROJECT_TASK, _TABLE, ["project_id", "task_id"])
    op.create_index(_INDEX_PROJECT_RESOLVED, _TABLE, ["project_id", "resolved_at"])


def downgrade() -> None:
    if _TABLE not in _tables(op.get_bind()):
        return
    op.drop_index(_INDEX_PROJECT_RESOLVED, table_name=_TABLE)
    op.drop_index(_INDEX_PROJECT_TASK, table_name=_TABLE)
    op.drop_index(_INDEX_TASK, table_name=_TABLE)
    op.drop_index(_INDEX_AGENT, table_name=_TABLE)
    op.drop_index(_INDEX_RUN, table_name=_TABLE)
    op.drop_table(_TABLE)
