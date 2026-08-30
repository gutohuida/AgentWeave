"""a question records the deadline of the wait it started, and when that wait ended

Revision ID: 0099
Revises: 0098
Create Date: 2026-08-30 05:20:00.000000

F14 and F60, `a-task-waits-while-its-run-waits`.

`wait_expires_at` is the deadline the Hub stamped while serving the ask, computed from
`Agent.question_timeout_seconds` where set and from the Hub's own resolution of
`AW_QUESTION_TIMEOUT` and its 240s default otherwise. Stored rather than derived at report time
because the setting is operator-editable while the run waits, so a deadline recomputed later would
describe a wait that never happened (design D3).

`wait_ended_at` is when the run stopped waiting without an answer — reported by `ask_user` as it
gives up, or swept at the run's end when that report never landed (design D4). It is what makes an
expired wait distinguishable from an open one, which four surfaces previously derived from
`answered = False` alone.

No backfill. Both columns record what happened during a wait, and for questions asked before this
migration no such record was kept — writing a plausible value would forge one, the reasoning
`0043`, `0096` and `0098` used. A pre-existing question reports NULL for both, which reads
correctly everywhere: NULL `wait_expires_at` makes the expiry report refuse it, and NULL
`wait_ended_at` leaves it counted as open exactly as it is today.

Guarded for a missing table the way `0033`/`0034`/`0098` are: an upgrade starting from an early
revision reaches here with only that revision's tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None

_TABLE = "questions"
_COLUMNS = ("wait_expires_at", "wait_ended_at")


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if _TABLE not in _tables(conn):
        return
    existing = _columns(conn, _TABLE)
    for name in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if _TABLE not in _tables(conn):
        return
    existing = _columns(conn, _TABLE)
    for name in _COLUMNS:
        if name in existing:
            op.drop_column(_TABLE, name)
