"""let a divergence record that a review governed it, and that a reviewer was resolved again

Revision ID: 0092
Revises: 0091
Create Date: 2026-08-26 19:05:00.000000

`one-answer-to-what-is-happening`, design D3 and D4.

Until now every review run was unbound — `binding_from_entries` read only `task_id`, and no
dispatch path has ever set that on a review entry — so `run_advanced_its_task` waved all nine of
them through on *"no task to have neglected"*. Once binding learns `review_task_id`, a review that
ends without a verdict reaches the divergence machinery for the first time, and that machinery
enumerates two columns it does not fit.

**`policy_applied`** records which rule governed. A review is governed by the reviewer resolution
and **not** by the task's `divergence_policy` (D3: re-running the same reviewer on the same
evidence is the least likely intervention to change the outcome, and the observed causes are
deterministic rather than flaky). Writing the task's own policy there would be a false record — a
`retry` task whose review failed would read `policy_applied: retry` beside an outcome nothing
retried, which is the one-word-two-meanings defect this whole change exists to end. So `review` is
its own value, and it is deliberately absent from `run_task_binding.POLICIES`: a task can never
carry it, and only a divergence row can.

**`outcome`** gains `restaffed`: a failed review answered by resolving the reviewer again (D4).
Distinct from `retried`, which is the same agent given another turn, and from `escalated`, which
routes through `task.escalation_agent` — a second reviewer resolution that `agent-flows` forbids in
terms. `_may_escalate` reads the previous outcome to bound a chain, and `restaffed` matching
neither is what makes it terminal there.

The change's own design said "no database migration; no schema change". That was wrong, found by
running the code rather than by reading it: both columns carry CHECK constraints
(`ck_run_divergences_policy`, `ck_run_divergences_outcome`) that the design did not account for.
Recorded in `design.md` under D3 rather than quietly absorbed.

Table recreation with `batch_alter_table`, because SQLite cannot alter a CHECK constraint in place
— the same approach `0058` takes for the identical kind of widening, including the guard on
`projects` and `tasks`, whose foreign key reflection would otherwise raise on a database alembic
reaches without `create_all`.

The downgrade rewrites the new values rather than dropping the rows. `review` becomes `surface`,
which is what the régime does when nothing can be restaffed, and `restaffed` becomes `escalated`,
the pre-existing outcome that also means "a different agent was given the work". Both are
approximations, and both keep a record that something happened — the row surviving its own history
is this table's stated property.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None

_TABLE = "run_divergences"


def _replace_constraints(*, include_review: bool) -> None:
    policies = "'surface', 'retry', 'escalate'"
    outcomes = "'surfaced', 'retried', 'escalated'"
    if include_review:
        policies += ", 'review'"
        outcomes += ", 'restaffed'"
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.drop_constraint("ck_run_divergences_policy", type_="check")
        batch_op.drop_constraint("ck_run_divergences_outcome", type_="check")
        batch_op.create_check_constraint(
            "ck_run_divergences_policy", f"policy_applied IN ({policies})"
        )
        batch_op.create_check_constraint("ck_run_divergences_outcome", f"outcome IN ({outcomes})")


def _present(conn) -> bool:
    """Whether this migration has a table to act on.

    Upgrades starting from an early revision reach here with only that revision's tables, and
    `create_all` builds the rest from the model with the widened constraints already in place.
    `projects` and `tasks` are named because `run_divergences` carries foreign keys into both, and
    batch mode's `recreate="always"` reflects those targets to preserve the relationships — a
    synthetic chain that never creates them raises `NoSuchTableError` before this migration's own
    guard could matter.
    """
    tables = set(sa.inspect(conn).get_table_names())
    return {_TABLE, "projects", "tasks"} <= tables


def upgrade() -> None:
    if not _present(op.get_bind()):
        return
    _replace_constraints(include_review=True)


def downgrade() -> None:
    conn = op.get_bind()
    if not _present(conn):
        return
    conn.execute(
        sa.text(f"UPDATE {_TABLE} SET policy_applied = 'surface' WHERE policy_applied = 'review'")
    )
    conn.execute(sa.text(f"UPDATE {_TABLE} SET outcome = 'escalated' WHERE outcome = 'restaffed'"))
    _replace_constraints(include_review=False)
