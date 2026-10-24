"""a check run may be superseded -- widen ck_task_check_runs_state

Revision ID: 0143
Revises: 0142
Create Date: 2026-10-24 00:00:00.000000

`checks-wait-less` (FR-3). A check run still running when its project's main tip moves is ended and
recorded `superseded`, not failed: main moved past it, and a run on the new tip replaces it. `0119`'s
CHECK admits only `running`, `passed`, `failed`, `error` and `interrupted`. No row changes value on
the way up.

Downgrade records every superseded run as `interrupted` -- ended before it decided anything, which is
what `interrupted` already says -- before restoring the narrow CHECK, because a batch recreate applies
the new CHECK to the copied rows. Table recreation, because SQLite cannot alter a CHECK in place;
guarded for a missing table, as `0121` is.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0143"
down_revision = "0142"
branch_labels = None
depends_on = None

_NARROW = ("running", "passed", "failed", "error", "interrupted")
_WIDE = (*_NARROW, "superseded")


def _present(conn) -> bool:
    return "task_check_runs" in set(sa.inspect(conn).get_table_names())


def _replace(states) -> None:
    with op.batch_alter_table("task_check_runs", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_task_check_runs_state", type_="check")
        batch_op.create_check_constraint(
            "ck_task_check_runs_state", "state IN ('" + "', '".join(states) + "')"
        )


def upgrade() -> None:
    if _present(op.get_bind()):
        _replace(_WIDE)


def downgrade() -> None:
    conn = op.get_bind()
    if _present(conn):
        conn.execute(
            sa.text("UPDATE task_check_runs SET state = 'interrupted' WHERE state = 'superseded'")
        )
        _replace(_NARROW)
