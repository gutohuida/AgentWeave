"""count failed deliveries, so an input that kills the runtime cannot wedge its agent forever

Revision ID: 0072
Revises: 0071
Create Date: 2026-08-14 17:00:00.000000

When a run fails before it completes, the input it was carrying returns to the queue so nothing is
lost. It keeps its place in arrival order and its binding to the conversation it arrived on, and the
queue is served in arrival order — so an input whose delivery kills the runtime is served again
immediately, and every later input for that agent waits behind the one doing the killing. Observed
live: four entries stacked up and four consecutive runs failed, and a request for a *fresh*
conversation could not get through either.

Nothing distinguished an entry returned five times from one never tried. `delivery_attempts` is
that fact. `abandoned_reason` is what the Hub says when it stops trying.

Every existing entry gets 0 and NULL, which is the truth about them: no delivery of theirs has
failed, and nothing has been given up on.

Deliberately no fourth `state`. The value is CHECK-constrained, and rewriting a CHECK on SQLite
means rebuilding a table whose autoincrement `sequence` the whole scheduler ordering depends on —
a bad trade to record a nuance a column carries. `withdrawn` already means "this will never be
delivered", which is true of an abandoned entry.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def _tables(conn) -> set[str]:
    """An upgrade starting from an early revision reaches this migration with only the tables
    those revisions created; `create_all` builds the rest from the model."""
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if "inbound_queue_entries" not in _tables(conn):
        return

    columns = _columns(conn, "inbound_queue_entries")
    if "delivery_attempts" not in columns:
        op.add_column(
            "inbound_queue_entries",
            sa.Column(
                "delivery_attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    if "abandoned_reason" not in columns:
        op.add_column(
            "inbound_queue_entries",
            sa.Column("abandoned_reason", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if "inbound_queue_entries" not in _tables(conn):
        return

    columns = _columns(conn, "inbound_queue_entries")
    if "abandoned_reason" in columns:
        op.drop_column("inbound_queue_entries", "abandoned_reason")
    if "delivery_attempts" in columns:
        op.drop_column("inbound_queue_entries", "delivery_attempts")
