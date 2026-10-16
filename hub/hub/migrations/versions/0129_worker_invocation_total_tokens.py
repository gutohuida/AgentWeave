"""worker spend counts against the budget -- worker_invocations.total_tokens, budget_exhausted

Revision ID: 0129
Revises: 0128
Create Date: 2026-10-16 00:00:00.000000

`worker-spend-counts-against-the-budget` (Tier 2, F240, decision fix-D2). Adds the normalised
token total that joins a worker call to the project total and the token budget, and the outcome
`budget_exhausted` for an autonomous call not spawned at exhaustion.

Existing rows are backfilled by the rule a new row is written by (`WorkerUsage.normalised_total`):
Claude counts cache reads and writes as input, as a Claude turn does; Codex already has its cached
input inside `input_tokens`; any other CLI (a Copilot one-shot call reports no tokens) stays null.
A row with neither an input nor an output count stays null: unknown, never zero. Measured on the
operator's database (mode=ro, 2026-10-16): 32 Claude rows, 962,599 tokens, and no project with a
budget, so the upgrade raises totals and pauses nothing.

The downgrade turns `budget_exhausted` rows into `spawn_failed` (their error is already set, so
the failure-explained CHECK holds), restores the old outcome CHECK and drops the column.

Guarded for a database with no `worker_invocations` table (an upgrade from a revision before
`0042`), and for a column already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0129"
down_revision = "0128"
branch_labels = None
depends_on = None

_OLD_OUTCOMES = (
    "ok",
    "unsupported_cli",
    "unknown_model",
    "spawn_failed",
    "nonzero_exit",
    "timeout",
    "unparseable",
    "schema_invalid",
)
_NEW_OUTCOMES = _OLD_OUTCOMES + ("budget_exhausted",)


def _outcome_check(outcomes) -> str:
    return "outcome IN ('" + "', '".join(outcomes) + "')"


def _columns() -> set:
    bind = op.get_bind()
    if "worker_invocations" not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {c["name"] for c in sa.inspect(bind).get_columns("worker_invocations")}


def upgrade() -> None:
    columns = _columns()
    if not columns:
        return
    with op.batch_alter_table("worker_invocations", recreate="always") as batch_op:
        if "total_tokens" not in columns:
            batch_op.add_column(sa.Column("total_tokens", sa.Integer(), nullable=True))
        batch_op.drop_constraint("ck_worker_invocations_outcome", type_="check")
        batch_op.create_check_constraint(
            "ck_worker_invocations_outcome", _outcome_check(_NEW_OUTCOMES)
        )
    op.execute(
        sa.text(
            "UPDATE worker_invocations SET total_tokens = CASE "
            "WHEN cli = 'claude' THEN COALESCE(input_tokens, 0) + COALESCE(cache_read_tokens, 0)"
            " + COALESCE(cache_write_tokens, 0) + COALESCE(output_tokens, 0) "
            "WHEN cli = 'codex' THEN COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0) "
            "END "
            "WHERE total_tokens IS NULL "
            "AND (input_tokens IS NOT NULL OR output_tokens IS NOT NULL)"
        )
    )


def downgrade() -> None:
    columns = _columns()
    if not columns:
        return
    op.execute(
        sa.text(
            "UPDATE worker_invocations SET outcome = 'spawn_failed' "
            "WHERE outcome = 'budget_exhausted'"
        )
    )
    with op.batch_alter_table("worker_invocations", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_worker_invocations_outcome", type_="check")
        batch_op.create_check_constraint(
            "ck_worker_invocations_outcome", _outcome_check(_OLD_OUTCOMES)
        )
        if "total_tokens" in columns:
            batch_op.drop_column("total_tokens")
