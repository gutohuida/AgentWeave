"""add inbound queue entry task

Revision ID: 0055
Revises: 0054
Create Date: 2026-08-10 20:12:00.000000

A delegation could already name a task — `send_message(..., task_id=…)` — but the id landed on a
`Message` row and stopped there, so the run that eventually did the work never saw it.

Carried on the queue entry rather than passed through the scheduler call, for the same reason
`spec_document` is (0051): a busy agent's turn starts from a later call than the one that queued the
input, so anything held only in the call is gone by the time the run exists.

Nullable and unbackfilled. An entry queued before this migration names no task, which is what was
true of it.

Guarded, like 0038-0054.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

_TABLE = "inbound_queue_entries"
_COLUMN = "task_id"


def _columns(conn):
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN in existing:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(64), nullable=True))


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN not in existing:
        return
    op.drop_column(_TABLE, _COLUMN)
