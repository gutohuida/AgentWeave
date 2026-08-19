"""a loop and a plain job are archivable, and a loop records how it ended

Revision ID: 0078
Revises: 0077
Create Date: 2026-08-19 03:20:00.000000

`2026-08-18-a-loop-writes-its-own-queue` design D16/D17 (addendum 2, task B1). Three more
additive, nullable columns, same "no `batch_alter_table` recreate needed" shape as
`0075`/`0076`/`0077`:

(a) `loops.archived_at` — housekeeping visibility, D17's second axis. NULL while a loop is not
    archived. Mirrors `Agent.archived_at`/`Conversation.archived_at`: nothing is ever deleted,
    only hidden from default listings.
(b) `ai_jobs.archived_at` — same shape, for a plain job with no loop (D16: "the job with no loop
    is not deletable, it's archivable" — a uniform rule, not a conditional one).
(c) `loops.ending_state` — D17's first axis, what happened rather than housekeeping. A short
    nullable string, NULL while the loop is still running. See `Loop.ending_state`'s own comment
    in `models.py` for the permitted values and why `stop_reason`'s prose does not replace it.

Guarded for a missing table on every step, matching `0071`/`0073`/`0075`/`0077`'s own precedent
for an upgrade starting from an early revision.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def _tables(conn: sa.engine.Connection) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn: sa.engine.Connection, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "loops" in present:
        columns = _columns(conn, "loops")
        if "archived_at" not in columns:
            op.add_column(
                "loops", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
            )
        if "ending_state" not in columns:
            op.add_column("loops", sa.Column("ending_state", sa.String(16), nullable=True))

    if "ai_jobs" in present:
        columns = _columns(conn, "ai_jobs")
        if "archived_at" not in columns:
            op.add_column(
                "ai_jobs", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
            )


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "ai_jobs" in present and "archived_at" in _columns(conn, "ai_jobs"):
        op.drop_column("ai_jobs", "archived_at")

    if "loops" in present:
        columns = _columns(conn, "loops")
        if "ending_state" in columns:
            op.drop_column("loops", "ending_state")
        if "archived_at" in columns:
            op.drop_column("loops", "archived_at")
