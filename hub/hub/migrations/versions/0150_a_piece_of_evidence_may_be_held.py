"""a piece of evidence may be held -- widen two evidence CHECKs

Revision ID: 0150
Revises: 0149
Create Date: 2026-10-27 00:00:00.000000

`each-piece-of-evidence-is-judged-on-its-own` (slice K, Tier 2). A send-back rejects only the pieces
the reviewer names as failing and keeps every other awaiting piece of the task `held` at its commit:
neither accepted nor rejected. `0068`'s CHECKs admit `awaiting`, `accepted` and `rejected` for
`requirement_evidence.review_state`, and `accepted` and `rejected` for `evidence_reviews.decision`;
both gain `held`. No row changes value on the way up: a piece rejected in bulk before this stays a
rejection (non-goal: past verdicts are not rewritten).

Downgrade maps every held piece back to `awaiting` -- it was never accepted or rejected, which is
what `awaiting` says -- and removes the `held` review rows, the one value the narrow CHECK cannot
hold; the reason a send-back gave for holding a piece is lost with them. Both happen before the
narrow CHECKs are restored, because a batch recreate applies the new CHECK to the copied rows.
Table recreation, because SQLite cannot alter a CHECK in place; guarded for a missing table and for
a missing table its foreign keys name, as `0121` is.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0150"
# Slice C's 0149 (`retire_the_proposed_phase`), which follows J's 0148. This branch's base ends at
# 0147; the chain closes when the slices merge.
down_revision = "0149"
branch_labels = None
depends_on = None

_NARROW_STATES = ("awaiting", "accepted", "rejected")
_WIDE_STATES = (*_NARROW_STATES, "held")
_NARROW_DECISIONS = ("accepted", "rejected")
_WIDE_DECISIONS = (*_NARROW_DECISIONS, "held")


#: What each table's foreign keys reach: a batch recreate reflects them, transitively
#: (`evidence_reviews` -> `requirement_evidence` -> `tasks`), and a database upgraded from an early
#: revision may hold the evidence tables without `tasks` (which only `create_all` builds), so each is
#: recreated only where everything it reaches is there, as `0121` guards.
_REACHED = {"projects", "spec_requirements", "tasks", "requirement_evidence"}
_NEEDS = {
    "requirement_evidence": _REACHED,
    "evidence_reviews": _REACHED | {"evidence_reviews"},
}


def _tables(conn) -> set:
    present = set(sa.inspect(conn).get_table_names())
    return {table for table, needs in _NEEDS.items() if needs <= present}


def _replace(table: str, name: str, column: str, values) -> None:
    with op.batch_alter_table(table, recreate="always") as batch_op:
        batch_op.drop_constraint(name, type_="check")
        batch_op.create_check_constraint(name, f"{column} IN ('" + "', '".join(values) + "')")


def upgrade() -> None:
    present = _tables(op.get_bind())
    if "requirement_evidence" in present:
        _replace(
            "requirement_evidence",
            "ck_requirement_evidence_review_state",
            "review_state",
            _WIDE_STATES,
        )
    if "evidence_reviews" in present:
        _replace("evidence_reviews", "ck_evidence_reviews_decision", "decision", _WIDE_DECISIONS)


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)
    if "requirement_evidence" in present:
        conn.execute(
            sa.text(
                "UPDATE requirement_evidence SET review_state = 'awaiting' "
                "WHERE review_state = 'held'"
            )
        )
        _replace(
            "requirement_evidence",
            "ck_requirement_evidence_review_state",
            "review_state",
            _NARROW_STATES,
        )
    if "evidence_reviews" in present:
        conn.execute(sa.text("DELETE FROM evidence_reviews WHERE decision = 'held'"))
        _replace("evidence_reviews", "ck_evidence_reviews_decision", "decision", _NARROW_DECISIONS)
