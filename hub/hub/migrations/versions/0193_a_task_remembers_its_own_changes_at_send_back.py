"""a task remembers its own changes at a send-back -- tasks.send_back_changes, tasks.handover_blocker

Revision ID: 0193
Revises: 0192
Create Date: 2026-11-27 21:00:00.000000

`a-task-that-cannot-move-waits-instead-of-being-rebuilt-and-re-reviewed` (FR-4, FR-7, D4).
`send_back_changes` is a digest of the task's own changes against the main branch, written by every
send-back, so a completion that changes nothing can be refused; `handover_blocker` is the blocker a
builder named when it handed unchanged work to its checker, which lets that work reach review with
no check run.

Runs on the operator's :8000 data at its next restart. Additive, both nullable with no default:
every existing row reads as having no baseline (never refused) and no handover.

Rollback: the downgrade drops both columns (plain `DROP COLUMN`, SQLite 3.35+, as `0192` does).
Guarded for a database without the table and for columns already present (`create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0193"
down_revision = "0192"
branch_labels = None
depends_on = None

_COLUMNS = ("send_back_changes", "handover_blocker")


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("tasks"):
        return set()
    return {column["name"] for column in inspector.get_columns("tasks")}


def upgrade() -> None:
    columns = _columns()
    if not columns:
        return
    for name in _COLUMNS:
        if name not in columns:
            op.add_column("tasks", sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    columns = _columns()
    for name in _COLUMNS:
        if name in columns:
            op.drop_column("tasks", name)
