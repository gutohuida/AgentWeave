"""stamp which workspace scheme a task belongs to, once, and never again

Revision ID: 0095
Revises: 0094
Create Date: 2026-08-27 13:40:00.000000

`2026-08-27-work-is-isolated-per-task`, design D4.

Per-task worktrees change where a turn bound to a task executes. A task that already carries
committed work on a per-agent branch cannot be moved: its own prior commits are on that branch and
nowhere else, so starting its next turn in a fresh task checkout cut from the integration base would
present the agent with its own work missing, mid-task. Those tasks stay on the old scheme for the
rest of their lives, and this column is what says so.

**The discriminator is the existence of a `Run`, and nothing about that run's contents.** R1
proposed "a prior run with a non-null `snapshot_commit_sha`" and that is wrong in the direction that
loses work: `worktrees.snapshot_worktree` returns `None` for a clean tree
(`hub/hub/worktrees.py:457-458`), so an agent that commits its own work — the normal case, which
`snapshot_worktree`'s own docstring calls a "best-effort, internal safety net" against — ends its
turn clean and records `NULL`. Reading that column would have un-grandfathered exactly the tasks
with the most real work on the branch.

**Deliberately over-inclusive.** A task whose runs committed nothing is grandfathered too. It keeps
today's behaviour instead of gaining isolation it could have had; the cost is that F58 persists a
little longer for a fixed set of tasks, where `rode_along_commits` already reports what came along.
The opposite error costs an agent its own work. Those are not comparable.

**Written here and by nothing else.** The set of grandfathered tasks is fixed at the instant this
migration runs and can only shrink, and that is a property of the write happening in exactly one
place rather than of any argument about which states are reachable —
`hub/tests/test_task_workspace_scheme.py::test_nothing_outside_the_migration_writes_the_column`
is what holds it.

Guarded for a missing table the way `0033`/`0034`/`0075` are: an upgrade starting from an early
revision reaches here with only that revision's tables, and `create_all` builds the rest from the
model with the column already on it. `runs` is guarded separately from `tasks` — a chain that has
one and not the other has no runs to grandfather, which is the correct answer rather than an error.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None

_TABLE = "tasks"
_COLUMN = "workspace_scheme"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)
    if _TABLE not in present:
        return

    if _COLUMN not in _columns(conn, _TABLE):
        # Deliberately no CHECK constraint, matching `status`, `priority` and `divergence_policy`
        # on this table: a table-level CHECK naming a column makes that column undroppable in
        # SQLite, which is what makes this migration's own downgrade possible.
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.String(16), nullable=False, server_default="task"),
        )

    # Every task that has ever had a run stays on the per-agent scheme. Nothing about the run is
    # read — not its status, not its outcome, not what it committed. See the docstring.
    if "runs" in present and "task_id" in _columns(conn, "runs"):
        # Spelled out rather than interpolated from `_TABLE`/`_COLUMN` on purpose: the source scan
        # in `test_task_workspace_scheme.py` looks for literal write forms, and a write hidden
        # behind an f-string is a write it cannot see. This is the one file the scan exempts, so it
        # is also the one file that must actually match it — otherwise the exemption is vacuous and
        # the test is green over a source tree it never really examined.
        conn.execute(
            sa.text(
                "UPDATE tasks SET workspace_scheme = 'agent' "
                "WHERE id IN (SELECT task_id FROM runs WHERE task_id IS NOT NULL)"
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _TABLE in _tables(conn) and _COLUMN in _columns(conn, _TABLE):
        op.drop_column(_TABLE, _COLUMN)
