"""classify an evidence-decision note as its own queue origin

Revision ID: 0108
Revises: 0107
Create Date: 2026-09-26 02:00:00.000000

An agent refused a decision because the run that recorded the evidence was still running is told,
when that run ends, that the row is open. No operator asked for the note and no agent sent it, so
both `operator` and `agent` would misstate where it came from in the queue the operator reads: its
own value, as `checkpoint` (0035) and `divergence` (0058) are. Like them it carries no
`origin_agent`; it is the Hub's own act.

Both constraints move, because `ck_inbound_queue_origin_agent` enumerates the origins too. Table
recreation with `batch_alter_table`, because SQLite cannot alter a CHECK constraint in place, with
the guard on the two tables `0058` guards on.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None


def _replace_constraints(*, include_evidence: bool) -> None:
    origins = "'operator', 'agent', 'job', 'checkpoint', 'divergence'"
    origin_agent = (
        "(origin_type = 'operator' AND origin_agent IS NULL) OR "
        "(origin_type = 'agent' AND origin_agent IS NOT NULL) OR "
        "(origin_type = 'job' AND origin_agent IS NULL) OR "
        "(origin_type = 'checkpoint' AND origin_agent IS NULL) OR "
        "(origin_type = 'divergence' AND origin_agent IS NULL)"
    )
    if include_evidence:
        origins += ", 'evidence'"
        origin_agent += " OR (origin_type = 'evidence' AND origin_agent IS NULL)"
    with op.batch_alter_table("inbound_queue_entries", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_inbound_queue_origin_type", type_="check")
        batch_op.drop_constraint("ck_inbound_queue_origin_agent", type_="check")
        batch_op.create_check_constraint(
            "ck_inbound_queue_origin_type", f"origin_type IN ({origins})"
        )
        batch_op.create_check_constraint("ck_inbound_queue_origin_agent", origin_agent)


def _has_tables() -> bool:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    return {"inbound_queue_entries", "projects"} <= tables


def upgrade() -> None:
    if not _has_tables():
        return
    _replace_constraints(include_evidence=True)


def downgrade() -> None:
    if not _has_tables():
        return
    # Input the Hub placed in the agent's queue with no sending agent: closest to `operator` once
    # the value is gone, as 0058's downgrade reads `divergence`.
    op.get_bind().execute(
        sa.text(
            "UPDATE inbound_queue_entries SET origin_type = 'operator' WHERE origin_type = 'evidence'"
        )
    )
    _replace_constraints(include_evidence=False)
