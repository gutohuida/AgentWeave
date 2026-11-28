"""a task waits on its prerequisites -- tasks.waits_on_prerequisites

Revision ID: 0192
Revises: 0191
Create Date: 2026-11-27 19:30:00.000000

`a-task-that-cannot-move-waits-instead-of-being-rebuilt-and-re-reviewed` (FR-2, FR-3, D1). A task
stopped because a prerequisite was added after it started is `blocked`, as a task parked on an
operator question is; this column is the second, typed reason, so a task can hold both and is
released only when each has cleared, and so its release goes back to its builder (`assigned`)
rather than resuming where a question's release resumes it.

Runs on the operator's :8000 data at its next restart. Additive, not null with a false default:
every existing row reads as not waiting on prerequisites, which is what each of them is today.

Rollback: the downgrade drops the column (plain `DROP COLUMN`, SQLite 3.35+, as `0159` does); a
task waiting on prerequisites then reads as blocked on nothing, released by the operator's hand.
Guarded for a database without the table (an upgrade from an early revision) and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0192"
down_revision = "0191"
branch_labels = None
depends_on = None


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("tasks"):
        return set()
    return {column["name"] for column in inspector.get_columns("tasks")}


def upgrade() -> None:
    columns = _columns()
    if columns and "waits_on_prerequisites" not in columns:
        op.add_column(
            "tasks",
            sa.Column(
                "waits_on_prerequisites",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    if "waits_on_prerequisites" in _columns():
        op.drop_column("tasks", "waits_on_prerequisites")
