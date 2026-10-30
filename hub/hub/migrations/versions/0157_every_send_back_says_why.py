"""every send-back says why -- task_transitions.reason_class, task_transitions.reason

Revision ID: 0157
Revises: 0156
Create Date: 2026-10-30 00:00:00.000000

`a-task-s-checks-and-merges-use-its-own-work-and-a-live-run-is-never-reset` FR-8/FR-9 (Tier 2). A
move to `revision_needed` records why: a reason class (`task_transitions.SEND_BACK_CLASSES`) and a
sentence. A reviewer must give the class; the Hub sets it on its own send-backs.

Additive only: two nullable columns. No backfill and no existing row is read or rewritten: a
send-back recorded before this reads no reason, and the app shows "no reason recorded".

Rollback: the downgrade drops both columns (plain `DROP COLUMN`, SQLite 3.35+, as `0152` does).

Guarded for a database without the table (an upgrade from an early revision) and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0157"
down_revision = "0156"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("reason_class", lambda: sa.String(length=16)),
    ("reason", lambda: sa.Text()),
)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "task_transitions" not in set(inspector.get_table_names()):
        return
    present = {c["name"] for c in inspector.get_columns("task_transitions")}
    for name, kind in _COLUMNS:
        if name not in present:
            op.add_column("task_transitions", sa.Column(name, kind(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "task_transitions" not in set(inspector.get_table_names()):
        return
    present = {c["name"] for c in inspector.get_columns("task_transitions")}
    for name, _ in reversed(_COLUMNS):
        if name in present:
            op.execute(sa.text(f"ALTER TABLE task_transitions DROP COLUMN {name}"))
