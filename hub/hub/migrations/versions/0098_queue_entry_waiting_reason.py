"""a queued entry records why its last delivery attempt did not start a turn

Revision ID: 0098
Revises: 0097
Create Date: 2026-08-28 05:10:00.000000

F97, found by driving the second e2e sweep on 2026-08-28.

`GET /queue/{agent}/status` re-derives the reason an agent is waiting from a handful of read-only
questions it can answer itself. Its own comment says why it does: a turn refused inside the
trigger left "the operator with '1 waiting' and no explanation to reason from". That comment was
written about the launchability and workspace cases, and it holds for exactly those — every other
refusal raised deeper inside `trigger_agent_directly` is still invisible to it.

Measured live, two agents and one task: the trigger response carried
`"writer is already running a turn on task task-...; a task's checkout takes one writing turn at
a time."` and the status route, polled one second later, answered `waiting_count: 1,
waiting_reason: null`.

The column is the alternative to restating each refusal's condition in the status route, which
would put two copies of every one of them in the codebase and leave the *next* refusal invisible
in the same way. `schedule_agent` already holds the refusal's own words at the moment it parks the
entry; it now writes them down.

No backfill. This records what happened on a delivery attempt, and for entries queued before this
migration no such record was kept — writing a plausible value would forge one, the reasoning
`0043` and `0096` used. A pre-existing queued entry reports `null` here and falls through to the
same delivery-attempt counter it does today, until its next attempt.

Guarded for a missing table the way `0033`/`0034`/`0075`/`0095`/`0096`/`0097` are: an upgrade
starting from an early revision reaches here with only that revision's tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None

_TABLE = "inbound_queue_entries"
_COLUMN = "waiting_reason"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if _TABLE not in _tables(conn):
        return
    if _COLUMN not in _columns(conn, _TABLE):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if _TABLE in _tables(conn) and _COLUMN in _columns(conn, _TABLE):
        op.drop_column(_TABLE, _COLUMN)
