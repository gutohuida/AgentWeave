"""a task transition may carry a note -- task_transitions.note

Revision ID: 0147
Revises: 0146
Create Date: 2026-10-27 00:00:00.000000

`every-task-can-always-be-moved-on` (FR-6, task `already-built`). Closing a document's open tasks as
already built walks each task to `under_review`, and later approves it, in moves the operator did
not make one by one; the history has to say which action made them and against which commits. One
nullable Text column; no existing row is read or rewritten, and NULL is what every move other than
such an action records.

A downgrade drops the column (a plain `DROP COLUMN`, SQLite 3.35+, as `0145`'s downgrade does) and
loses the notes written since; the moves themselves stay recorded.

Guarded for a database without the table (an upgrade from an early revision) and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0147"
down_revision = "0146"
branch_labels = None
depends_on = None


def _columns(conn) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns("task_transitions")}


def _present(conn) -> bool:
    return "task_transitions" in set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    conn = op.get_bind()
    if _present(conn) and "note" not in _columns(conn):
        op.add_column("task_transitions", sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if _present(conn) and "note" in _columns(conn):
        op.execute(sa.text("ALTER TABLE task_transitions DROP COLUMN note"))
