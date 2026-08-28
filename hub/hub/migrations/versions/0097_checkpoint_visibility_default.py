"""checkpoints stored under the absent default become project-visible

Revision ID: 0097
Revises: 0096
Create Date: 2026-08-28 02:55:00.000000

F88, found by driving row 15 of the e2e sweep on 2026-08-28.

`checkpoints.visibility` shipped defaulting to `private`, and no caller anywhere ever passed
anything else — not the operator's "take a checkpoint now" route, not the threshold trigger, not
the handover path. So the visibility half of the `capability ∩ visibility` intersection
`checkpoint_access.may_read_checkpoint` computes was closed for every checkpoint that has ever
existed, and `can_read_checkpoints` and `can_recall` were conferrable and inert. Measured live: an
agent holding both was refused a peer's cited observation with the same not-found an ungranted one
gets.

The code default is now `project`, which is what `conversation-checkpoint` describes — "a
checkpoint MAY additionally restrict itself" makes restriction the exception a checkpoint opts
into, not the state every checkpoint starts in. The system is still closed by default, because
both reader grants still are.

**This backfills, and that is deliberate**, which is the opposite of `0043`'s and `0096`'s
no-backfill reasoning — and for a reason those two did not have. Their columns record a *fact*
about a past run that cannot be recovered, so writing a plausible value would forge one. This
column records a *decision*, and no such decision was ever made: nothing could set it, so every
stored `private` is the absent default rather than somebody's choice. Leaving them would split a
project's history at this migration, with the older half permanently unreadable and no surface
able to change it.

Nothing is widened by this on its own. A peer still reads nothing without the operator's grant,
which defaults to False and which this migration does not touch.

Guarded for a missing table the way `0033`/`0034`/`0075`/`0095`/`0096` are: an upgrade starting
from an early revision reaches here with only that revision's tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None

_TABLE = "checkpoints"
_COLUMN = "visibility"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if _TABLE not in _tables(conn) or _COLUMN not in _columns(conn, _TABLE):
        return
    conn.execute(sa.text(f"UPDATE {_TABLE} SET {_COLUMN} = 'project' WHERE {_COLUMN} = 'private'"))


def downgrade() -> None:
    """Deliberately does nothing.

    A downgrade cannot tell a row this migration moved from one an operator later restricted, and
    guessing would silently undo a real decision. The column keeps its values; only the code
    default goes back.
    """
