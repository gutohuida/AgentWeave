"""add the project's main branch and the record of what approval merged

Revision ID: 0070
Revises: 0069
Create Date: 2026-08-14 00:30:00.000000

`projects.main_branch` starts null for every existing project, and null means nothing merges. That
is the whole upgrade story: a change that started merging into a branch it inferred, on the day it
was installed, would write to histories nobody offered it. The existing `MAIN_BRANCH_NAMES` guess
keeps working for *reporting* — where a wrong answer costs an `unknown` — and stops short of
writing.

`task_integrations` records every approval that reached the integration step, including the ones
that merged nothing. Skipping is a first-class outcome with a stated reason, because "my approved
work is not on main" needs an answer and silence is not one.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None

_OUTCOMES = ("merged", "skipped", "failed")


def _tables(conn) -> set[str]:
    """An upgrade starting from an early revision reaches this migration with only the tables
    those revisions created; `create_all` builds the rest from the model."""
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    # Nullable with no server default: "not chosen" has to be representable, and is the state every
    # existing project starts in.
    if "projects" in present and "main_branch" not in _columns(conn, "projects"):
        op.add_column("projects", sa.Column("main_branch", sa.String(255), nullable=True))

    if "task_integrations" not in present:
        op.create_table(
            "task_integrations",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=False),
            sa.Column("commit_sha", sa.String(64), nullable=True),
            sa.Column("source_branch", sa.String(255), nullable=True),
            sa.Column("target_branch", sa.String(255), nullable=True),
            sa.Column("outcome", sa.String(16), nullable=False),
            sa.Column("reason", sa.Text, nullable=False, server_default=""),
            sa.Column("mechanism", sa.String(16), nullable=False, server_default="local"),
            sa.Column("actor_kind", sa.String(16), nullable=False),
            sa.Column("actor", sa.String(128), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            # Safe on a table this migration creates: the constraint goes when the table goes.
            # Naming a column in a table-level CHECK is what makes a column undroppable in SQLite,
            # and that trap only bites when the column outlives the migration that added it.
            sa.CheckConstraint(
                "outcome IN ('" + "', '".join(_OUTCOMES) + "')",
                name="ck_task_integrations_outcome",
            ),
        )
        op.create_index("ix_task_integrations_task", "task_integrations", ["task_id", "created_at"])
        op.create_index(
            "ix_task_integrations_project", "task_integrations", ["project_id", "created_at"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)
    if "task_integrations" in present:
        op.drop_index("ix_task_integrations_project", table_name="task_integrations")
        op.drop_index("ix_task_integrations_task", table_name="task_integrations")
        op.drop_table("task_integrations")
    if "projects" in present and "main_branch" in _columns(conn, "projects"):
        op.drop_column("projects", "main_branch")
