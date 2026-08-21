"""add task_dependency_references

Revision ID: 0084
Revises: 0083
Create Date: 2026-08-21 08:10:00.000000

`task-dependencies` design D7: an unresolvable requirement name is "preserved rather than
dropped… the unrecognised name is the evidence of what went wrong" (`task_requirement_references`,
`0067`-era precedent). Section 4 extends the same shape to a `depends_on` entry `materialise()`
cannot turn into an edge — in practice, almost always an import whose target document was reopened
between the importing document's `propose()` and its `approve()`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def _tables(conn) -> set[str]:
    """An upgrade starting from an early revision reaches this migration with only the tables
    those revisions created; `create_all` builds the rest from the model."""
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "task_dependency_references" not in present and "tasks" in present and "projects" in present:
        op.create_table(
            "task_dependency_references",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=False),
            sa.Column("reference", sa.Text(), nullable=False),
            sa.Column("reason", sa.String(32), nullable=False, server_default="unknown"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_task_dependency_references_task", "task_dependency_references", ["task_id"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "task_dependency_references" in present:
        op.drop_index("ix_task_dependency_references_task", table_name="task_dependency_references")
        op.drop_table("task_dependency_references")
