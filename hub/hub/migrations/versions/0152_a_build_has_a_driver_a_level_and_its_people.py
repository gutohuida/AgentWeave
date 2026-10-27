"""a build has a driver, a level and its people -- builds; tasks.build_id/level/builder;
task_transitions.level

Revision ID: 0152
Revises: 0149
Create Date: 2026-10-27 00:00:00.000000

`a-build-has-a-driver-a-level-and-its-people` (slice D, Tier 2). A `builds` table records how an
approved document is built (driver, level, builders, reviewer pool, lead, budget cap, window,
landing), with one *running* build per document enforced by a partial unique index. Each task a
build covers records the build and its level (and the builder it was declared with), and each move
of such a task records the level that governed it.

No backfill and nothing existing is read or rewritten: a null `build_id`/`level` means built
outside any build and governed by the document's rigor exactly as before, which is every row on the
operator's database today (read-only, 2026-10-27: 0 open spec tasks, one live flow loop with no
build).

Numbered 0152 on a base whose head is 0149 (slices K and M take 0150 and 0151 beside it); the
orchestrator relinks `down_revision` at merge.

Downgrade drops the index, the four columns and the table (plain `DROP COLUMN`, SQLite 3.35+, as
`0147`'s downgrade does); it loses the build records and the levels written since, and nothing else.

Guarded for a database without the tables (an upgrade from an early revision) and for columns or a
table already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0152"
down_revision = "0149"
branch_labels = None
depends_on = None

_TASK_COLUMNS = (
    ("build_id", sa.String(64)),
    ("level", sa.String(16)),
    ("builder", sa.String(64)),
)


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _indexes(conn, table: str) -> set:
    return {i["name"] for i in sa.inspect(conn).get_indexes(table)}


def upgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "builds" not in tables and "projects" in tables:
        op.create_table(
            "builds",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("document_id", sa.String(64), nullable=False),
            sa.Column("state", sa.String(16), nullable=False, server_default="running"),
            sa.Column("driver", sa.String(16), nullable=False),
            sa.Column("level", sa.String(16), nullable=False),
            sa.Column("builders", sa.JSON(), nullable=False),
            sa.Column("reviewers", sa.JSON(), nullable=False),
            sa.Column("lead", sa.String(64), nullable=True),
            sa.Column("budget_cap_usd_micros", sa.BigInteger(), nullable=True),
            sa.Column("window_start", sa.DateTime(), nullable=True),
            sa.Column("window_end", sa.DateTime(), nullable=True),
            sa.Column("landing", sa.String(16), nullable=False, server_default="main"),
            sa.Column("loop_id", sa.String(64), nullable=True),
            sa.Column("lead_conversation_id", sa.String(64), nullable=True),
            sa.Column("stop_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("stopped_at", sa.DateTime(), nullable=True),
        )
    if "builds" in _tables(conn):
        present = _indexes(conn, "builds")
        if "ix_builds_project" not in present:
            op.create_index("ix_builds_project", "builds", ["project_id", "created_at"])
        if "ix_builds_document_id" not in present:
            op.create_index("ix_builds_document_id", "builds", ["document_id"])
        if "ix_builds_loop_id" not in present:
            op.create_index("ix_builds_loop_id", "builds", ["loop_id"])
        if "ux_builds_document_running" not in present:
            op.create_index(
                "ux_builds_document_running",
                "builds",
                ["document_id"],
                unique=True,
                sqlite_where=sa.text("state = 'running'"),
                postgresql_where=sa.text("state = 'running'"),
            )
    if "tasks" in tables:
        have = _columns(conn, "tasks")
        for name, kind in _TASK_COLUMNS:
            if name not in have:
                op.add_column("tasks", sa.Column(name, kind, nullable=True))
        if "ix_tasks_build_id" not in _indexes(conn, "tasks"):
            op.create_index("ix_tasks_build_id", "tasks", ["build_id"])
    if "task_transitions" in tables and "level" not in _columns(conn, "task_transitions"):
        op.add_column("task_transitions", sa.Column("level", sa.String(16), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "task_transitions" in tables and "level" in _columns(conn, "task_transitions"):
        op.execute(sa.text("ALTER TABLE task_transitions DROP COLUMN level"))
    if "tasks" in tables:
        if "ix_tasks_build_id" in _indexes(conn, "tasks"):
            op.drop_index("ix_tasks_build_id", table_name="tasks")
        have = _columns(conn, "tasks")
        for name, _ in _TASK_COLUMNS:
            if name in have:
                op.execute(sa.text(f"ALTER TABLE tasks DROP COLUMN {name}"))
    if "builds" in tables:
        for name in _indexes(conn, "builds"):
            op.drop_index(name, table_name="builds")
        op.drop_table("builds")
