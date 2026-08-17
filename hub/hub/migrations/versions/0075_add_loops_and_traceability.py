"""add loops, a task->loop join column, and a job run's conversation traceability column

Revision ID: 0075
Revises: 0074
Create Date: 2026-08-17 01:05:00.000000

`2026-08-16-many-named-loops` gives an `AIJob` an optional purpose and stop condition — a "loop" —
and closes the gap that today's `JobRun` never records which conversation a firing actually used,
so "what did firing #12 of job X do" could only be guessed from timestamps.

Three additive changes, none touching an existing constraint, so none needs the
`batch_alter_table` recreate `0074` needed for its CHECK-constraint change:

(a) `loops` is a brand-new table — no existing-column-drop hazard, so a plain `ForeignKey` on
    `job_id` is fine (SQLite never enforces it; see design D1). One row per loop-job, `job_id`
    unique.
(b) `tasks.loop_id` — deliberately no `ForeignKey`, mirroring `tasks.spec_document_id`'s own
    established shape and its comment: a table-level CHECK naming a column makes that column
    undroppable in SQLite, and while nothing here adds such a CHECK, the column sits on an
    already-live table with data in it, so an `ADD COLUMN` migration is the only thing this
    revision ever gets to do to it.
(c) `job_runs.conversation_id` — deliberately no `ForeignKey` either, matching `AgentOutput.
    run_id`'s precedent: every `JobRun` written before this migration has `NULL` here, honestly,
    because nothing recorded it until now.

Guarded for a missing table on every step, the way `0071`/`0073` do — an upgrade starting from an
early revision reaches `0075` with only the tables those revisions created.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None

_LOOPS_TABLE = "loops"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def _indexes(conn, table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(conn).get_indexes(table)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if _LOOPS_TABLE not in present and {"projects", "ai_jobs"} <= present:
        op.create_table(
            _LOOPS_TABLE,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column(
                "job_id",
                sa.String(64),
                sa.ForeignKey("ai_jobs.id", ondelete="CASCADE"),
                unique=True,
                nullable=False,
            ),
            sa.Column("purpose", sa.Text(), nullable=False, server_default=""),
            sa.Column("stop_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "stop_when_queue_empties",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("stop_reason", sa.Text(), nullable=True),
            sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by_run_id", sa.String(64), nullable=True),
            sa.Column("updated_by_run_id", sa.String(64), nullable=True),
        )
        op.create_index("ix_loops_project", _LOOPS_TABLE, ["project_id"])

    if "tasks" in present:
        columns = _columns(conn, "tasks")
        if "loop_id" not in columns:
            # Deliberately no ForeignKey: same SQLite undroppable-column reasoning
            # `tasks.spec_document_id`'s own comment already states, unmodified for this column.
            op.add_column("tasks", sa.Column("loop_id", sa.String(64), nullable=True))
        if "ix_tasks_loop_id" not in _indexes(conn, "tasks"):
            op.create_index("ix_tasks_loop_id", "tasks", ["loop_id"])

    if "job_runs" in present:
        columns = _columns(conn, "job_runs")
        if "conversation_id" not in columns:
            # No ForeignKey, matching `AgentOutput.run_id`'s own precedent: rows written before
            # this migration honestly have NULL here, because nothing recorded it.
            op.add_column("job_runs", sa.Column("conversation_id", sa.String(64), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "job_runs" in present and "conversation_id" in _columns(conn, "job_runs"):
        op.drop_column("job_runs", "conversation_id")

    if "tasks" in present:
        if "ix_tasks_loop_id" in _indexes(conn, "tasks"):
            op.drop_index("ix_tasks_loop_id", table_name="tasks")
        if "loop_id" in _columns(conn, "tasks"):
            op.drop_column("tasks", "loop_id")

    if _LOOPS_TABLE in present:
        if "ix_loops_project" in _indexes(conn, _LOOPS_TABLE):
            op.drop_index("ix_loops_project", table_name=_LOOPS_TABLE)
        op.drop_table(_LOOPS_TABLE)
