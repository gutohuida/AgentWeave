"""let a divergence record that a live flow governed its own work turn's divergence

Revision ID: 0094
Revises: 0093
Create Date: 2026-08-27 05:00:00.000000

`every-run-knows-its-task`, design D7.

Once a flow's ordinary work firing binds the run it starts (groups 1-2 of this change), that run's
divergence reaches the same policy machinery a delegated or operator-started run's does — and a
task whose policy is `retry` would have that policy start a second run racing the flow's own next
firing of the same task. `retry` does not answer a divergence of a live flow's own work turn; the
flow already re-fires it.

The record says so: `policy_applied` gains `flow`, deliberately absent from
`run_task_binding.POLICIES` so no task can ever carry it — the same shape `0092` used for `review`.
`outcome` needs no new value: the flow régime always resolves to `surfaced`, an outcome that
already exists.

Table recreation with `batch_alter_table`, the same approach `0092` and `0058` take for the
identical kind of CHECK-constraint widening, including the guard on `projects` and `tasks`, whose
foreign key reflection would otherwise raise on a database alembic reaches without `create_all`
(the `0033`/`0034` missing-table guard shape).

The downgrade rewrites `flow` back to `retry` — the policy that was actually on the task when the
divergence happened, and the value this migration's own upgrade path never touches for `outcome`,
which already reads `surfaced` and needs no rewrite.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None

_TABLE = "run_divergences"


def _replace_constraint(*, include_flow: bool) -> None:
    policies = "'surface', 'retry', 'escalate', 'review'"
    if include_flow:
        policies += ", 'flow'"
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.drop_constraint("ck_run_divergences_policy", type_="check")
        batch_op.create_check_constraint(
            "ck_run_divergences_policy", f"policy_applied IN ({policies})"
        )


def _present(conn) -> bool:
    """Whether this migration has a table to act on.

    Upgrades starting from an early revision reach here with only that revision's tables, and
    `create_all` builds the rest from the model with the widened constraint already in place.
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
    _replace_constraint(include_flow=True)


def downgrade() -> None:
    conn = op.get_bind()
    if not _present(conn):
        return
    conn.execute(
        sa.text(f"UPDATE {_TABLE} SET policy_applied = 'retry' WHERE policy_applied = 'flow'")
    )
    _replace_constraint(include_flow=False)
