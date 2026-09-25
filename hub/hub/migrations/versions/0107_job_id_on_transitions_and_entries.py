"""a job's move records the job: task_transitions.job_id, inbound_queue_entries.job_id

Revision ID: 0107
Revises: 0106
Create Date: 2026-09-25 03:00:00.000000

`a-flows-own-moves-are-recorded-as-the-flows` (findings F47, F120). A scheduled loop or flow stages
its selection as the operator, and the history could not tell the two apart. `origin` gains the
value `job`, and the job travels: `task_transitions.job_id` on the row, `inbound_queue_entries.job_id`
so the cause survives from the firing that queued a review to the dispatch that stages it.

Both nullable `String(64)`, no ForeignKey (the SQLite column-drop trap), no backfill: existing rows
keep reading as the operator's, which is what the operator accepted (D8). `origin` has no CHECK
constraint, so admitting `job` needs no table rebuild.

Guarded per table, because an upgrade starting from an early revision reaches this with only that
revision's tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0107"
down_revision = "0106"
branch_labels = None
depends_on = None

_TABLES = ("task_transitions", "inbound_queue_entries")
_COLUMN = "job_id"


def _columns(conn, table: str) -> set[str] | None:
    inspector = sa.inspect(conn)
    if table not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    for table in _TABLES:
        existing = _columns(conn, table)
        if existing is not None and _COLUMN not in existing:
            op.add_column(table, sa.Column(_COLUMN, sa.String(64), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    for table in _TABLES:
        existing = _columns(conn, table)
        if existing is not None and _COLUMN in existing:
            with op.batch_alter_table(table) as batch:
                batch.drop_column(_COLUMN)
