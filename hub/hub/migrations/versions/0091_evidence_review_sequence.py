"""give evidence reviews a real ordering key, so "which review is latest" cannot tie

Revision ID: 0091
Revises: 0090
Create Date: 2026-08-26 05:20:00.000000

F59. `_latest_reviews_for` (`hub/hub/api/v1/spec.py`) and `reviews_for`
(`hub/hub/requirement_evidence.py`) both answered "which review is latest" by
`order_by(EvidenceReview.created_at, EvidenceReview.id)`. Two reviews created in the same clock
tick tie on `created_at` — the identical measured cause as F55's `Checkpoint.sequence`: Windows'
clock resolution is coarser than the microsecond precision the value implies, and a real
occurrence whenever an operator (or an agent) records two decisions back to back, not a
one-in-a-million race. `EvidenceReview.id` cannot break the tie either: it is `evr-` + a random
short id, with no relationship to insertion order, so roughly half the time the tie-break picked
the *older* review as "latest" and the operator was shown a stale decision and reason, silently.
Reproduced live: `test_a_later_acceptance_replaces_the_reason_shown` failed 3 of 6 bare re-runs on
the unmodified branch tip.

`sequence` is the same fix already applied to `Checkpoint` (migration `0088`), `TaskTransition`,
`InboundQueueEntry` and `Conversation` (migration `0073`), same reasoning: an autoincrement integer
the database itself hands out in insertion order, so two rows committed in the same transaction
still come back in the order they were actually created. Making `sequence` the primary key, not
`id`, is the same shape those tables use — SQLite can only give a column real autoincrement when it
is the table's sole `INTEGER PRIMARY KEY`. No `session.get(EvidenceReview, ...)` call site exists
anywhere in the codebase (checked before writing this migration), so unlike `Checkpoint` this change
needs no `get_by_id`-style helper — nothing looks an `EvidenceReview` up by its string id via the
ORM identity map.

The table is recreated (`batch_alter_table(..., recreate="always")`) because SQLite cannot change
which column is the primary key in place — the same reason `0088` and `0073` recreate their tables
for the identical change. Existing rows get `sequence` values in whatever order SQLite's
`INSERT INTO ... SELECT` visits them during the copy, which for a table whose declared primary key
was never `INTEGER` is insertion order — the same order they were actually created in.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None

_TABLE = "evidence_reviews"


def _columns(conn) -> set[str] | None:
    """Columns of `evidence_reviews`, or None when it or a table its FK graph reaches is not there.

    Upgrades starting from an early revision reach this migration with only that revision's
    tables; `create_all` builds the rest from the model, `sequence` as the primary key included.
    `tasks` has to be in this set even though this migration never touches it directly:
    `evidence_reviews.evidence_id` FKs to `requirement_evidence`, and batch mode's
    `recreate="always"` reflects that target table to preserve the relationship — which in turn
    reflects `requirement_evidence.task_id`'s own FK to `tasks`. A synthetic upgrade chain that
    never creates `tasks` (the same shape `test_migration_00NN_is_guarded_when_tasks_does_not_exist`
    exercises for other migrations) makes that second-order reflection raise `NoSuchTableError`
    before this migration's own guard ever gets a chance to matter.
    """
    inspector = sa.inspect(conn)
    if not {_TABLE, "projects", "requirement_evidence", "tasks"} <= set(
        inspector.get_table_names()
    ):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or "sequence" in existing:
        return
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.add_column(sa.Column("sequence", sa.Integer(), nullable=True))
        batch_op.alter_column("id", existing_type=sa.String(64), nullable=False)
        batch_op.create_primary_key("pk_evidence_reviews", ["sequence"])
        batch_op.create_unique_constraint("uq_evidence_reviews_id", ["id"])


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or "sequence" not in existing:
        return
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.drop_constraint("pk_evidence_reviews", type_="primary")
        batch_op.drop_constraint("uq_evidence_reviews_id", type_="unique")
        batch_op.drop_column("sequence")
        batch_op.create_primary_key("pk_evidence_reviews_id", ["id"])
