"""a loop's definition edits are staged, not applied immediately

Revision ID: 0080
Revises: 0079
Create Date: 2026-08-19 05:50:00.000000

`2026-08-18-a-loop-writes-its-own-queue` design D11 (addendum, task A2.1/A2.5). Five additive
nullable columns, same "no `batch_alter_table` recreate needed" shape as `0075`/`0077`/`0078`/
`0079`:

`loops.pending_purpose`, `loops.pending_stop_at`, `loops.pending_stop_when_queue_empties` — a
staged edit to the corresponding live column, applied at the loop's next firing, before its
briefing is composed (`scheduler._apply_pending_loop_edit`). NULL means "no change staged to this
field" for all three — the same "untouched vs explicitly cleared" convention `JobUpdate`'s own
`purpose`/`stop_at`/`stop_when_queue_empties` fields already use, so a caller that only edits
`purpose` leaves the other two live values alone.

`loops.pending_edit_actor`, `loops.pending_edit_at` — who staged the edit and when (task A2.5).
`pending_edit_at` doubles as the sentinel for "is there a pending edit at all": an edit always
touches at least one of the three fields above (mirrors `_loop_opts_in`'s own "at least one
field" rule), so a non-NULL `pending_edit_at` and an all-NULL trio of pending fields cannot occur
together in practice.

Guarded for a missing table, matching `0071`/`0073`/`0075`/`0077`/`0078`/`0079`'s own precedent
for an upgrade starting from an early revision.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0080"
down_revision = "0079"
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
        if "pending_purpose" not in columns:
            op.add_column("loops", sa.Column("pending_purpose", sa.Text(), nullable=True))
        if "pending_stop_at" not in columns:
            op.add_column(
                "loops", sa.Column("pending_stop_at", sa.DateTime(timezone=True), nullable=True)
            )
        if "pending_stop_when_queue_empties" not in columns:
            op.add_column(
                "loops",
                sa.Column("pending_stop_when_queue_empties", sa.Boolean(), nullable=True),
            )
        if "pending_edit_actor" not in columns:
            op.add_column("loops", sa.Column("pending_edit_actor", sa.String(64), nullable=True))
        if "pending_edit_at" not in columns:
            op.add_column(
                "loops", sa.Column("pending_edit_at", sa.DateTime(timezone=True), nullable=True)
            )


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "loops" in present:
        columns = _columns(conn, "loops")
        for column in (
            "pending_purpose",
            "pending_stop_at",
            "pending_stop_when_queue_empties",
            "pending_edit_actor",
            "pending_edit_at",
        ):
            if column in columns:
                op.drop_column("loops", column)
