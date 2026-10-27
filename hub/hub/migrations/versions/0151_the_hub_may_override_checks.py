"""the Hub may override checks -- task_transitions.override_by, projects.checks_auto_override,
tasks.merges_branch_tip

Revision ID: 0151
Revises: 0149
Create Date: 2026-10-27 00:00:00.000000

`a-red-main-does-not-hold-the-night` (slice M, Tier 2). An approval over check failures that are
provably not the task's (the same test ids fail on main too, or passed when rerun on their own)
lands with an override the Hub records itself, so who overrode becomes a column of its own beside
`override_reason`: `operator` or `hub`. Every existing override was the operator's (only the
operator could make one), so rows with a reason are backfilled `operator`; every other row stays
NULL. And one project setting, on by default for new and existing projects, turns the automatic
override and fix-task filing off. And `tasks.merges_branch_tip` (default false, every existing task
false): a fix task the Hub files is governed by its review alone and merges its branch tip, since it
serves no requirement and in a flow could otherwise never be reviewed or landed.

Numbered 0151 with `down_revision` 0149 (slice C, the highest revision on this branch): slice K
takes 0150 in parallel, and the chain is relinked to 0150 when it merges.

Runs on the operator's :8000 data at its next restart. A downgrade drops the three columns (a
Hub-filed fix task then reads as an ordinary task of its loop) (plain `DROP
COLUMN`, SQLite 3.35+, as 0145/0147 do); automatic overrides then read as operator overrides whose
reason says the Hub made them, and nothing else is lost. The operational rollback needs no
migration: turn the setting off.

Guarded for a database without the tables (an upgrade from an early revision) and for columns
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0151"
down_revision = "0149"
branch_labels = None
depends_on = None


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "task_transitions" in tables and "override_by" not in _columns(conn, "task_transitions"):
        op.add_column(
            "task_transitions", sa.Column("override_by", sa.String(length=16), nullable=True)
        )
        op.execute(
            sa.text(
                "UPDATE task_transitions SET override_by = 'operator' "
                "WHERE override_reason IS NOT NULL"
            )
        )
    if "projects" in tables and "checks_auto_override" not in _columns(conn, "projects"):
        op.add_column(
            "projects",
            sa.Column(
                "checks_auto_override", sa.Boolean(), nullable=False, server_default=sa.text("1")
            ),
        )
    if "tasks" in tables and "merges_branch_tip" not in _columns(conn, "tasks"):
        op.add_column(
            "tasks",
            sa.Column(
                "merges_branch_tip", sa.Boolean(), nullable=False, server_default=sa.text("0")
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "tasks" in tables and "merges_branch_tip" in _columns(conn, "tasks"):
        op.execute(sa.text("ALTER TABLE tasks DROP COLUMN merges_branch_tip"))
    if "task_transitions" in tables and "override_by" in _columns(conn, "task_transitions"):
        op.execute(sa.text("ALTER TABLE task_transitions DROP COLUMN override_by"))
    if "projects" in tables and "checks_auto_override" in _columns(conn, "projects"):
        op.execute(sa.text("ALTER TABLE projects DROP COLUMN checks_auto_override"))
