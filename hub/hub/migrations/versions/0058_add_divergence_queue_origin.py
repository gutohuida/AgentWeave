"""classify a divergence response as its own queue origin

Revision ID: 0058
Revises: 0057
Create Date: 2026-08-10 21:05:00.000000

A run started because a bound run ended without moving its task is not any of the four existing
origins. No operator asked for it, no agent sent it, no job scheduled it, and it is not a
checkpoint being handed to a successor.

Its own value rather than a borrowed one, for the reason `checkpoint` gives in `models.py`: a
signal that reports something other than what it names is the exact defect this whole capability
exists to remove. Reusing `operator` would put the operator's name on work they did not ask for,
in the queue the operator reads.

Both constraints move, because `ck_inbound_queue_origin_agent` enumerates the origins too. Like
`origin_type = 'job'`, a divergence response carries no `origin_agent`: it is the Hub's own act.

`divergence_source_run_id` rides along on the same table recreation. The retry bound (design D8)
lives on the *run*, and a queued response becomes a run later, in a different call — so like
`task_id`, it has to survive the queue or it is gone by the time it matters, and a chain that
cannot see its own source cannot be bounded.

Table recreation with `batch_alter_table`, because SQLite cannot alter a CHECK constraint in place
— the same approach `0019` and `0035` take, including the guard on `projects`, whose foreign key
reflection would otherwise raise on a database that alembic reaches without `create_all`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


_SOURCE_COLUMN = "divergence_source_run_id"


def _replace_constraints(*, include_divergence: bool, add_source_column: bool = False) -> None:
    origins = "'operator', 'agent', 'job', 'checkpoint'"
    origin_agent = (
        "(origin_type = 'operator' AND origin_agent IS NULL) OR "
        "(origin_type = 'agent' AND origin_agent IS NOT NULL) OR "
        "(origin_type = 'job' AND origin_agent IS NULL) OR "
        "(origin_type = 'checkpoint' AND origin_agent IS NULL)"
    )
    if include_divergence:
        origins += ", 'divergence'"
        origin_agent += " OR (origin_type = 'divergence' AND origin_agent IS NULL)"
    with op.batch_alter_table("inbound_queue_entries", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_inbound_queue_origin_type", type_="check")
        batch_op.drop_constraint("ck_inbound_queue_origin_agent", type_="check")
        batch_op.create_check_constraint(
            "ck_inbound_queue_origin_type", f"origin_type IN ({origins})"
        )
        batch_op.create_check_constraint("ck_inbound_queue_origin_agent", origin_agent)
        if add_source_column:
            batch_op.add_column(sa.Column(_SOURCE_COLUMN, sa.String(64), nullable=True))
        elif not include_divergence:
            batch_op.drop_column(_SOURCE_COLUMN)


def _columns(conn) -> set[str]:
    return {col["name"] for col in sa.inspect(conn).get_columns("inbound_queue_entries")}


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if not {"inbound_queue_entries", "projects"} <= tables:
        return
    _replace_constraints(
        include_divergence=True,
        add_source_column=_SOURCE_COLUMN not in _columns(conn),
    )


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if not {"inbound_queue_entries", "projects"} <= tables:
        return
    # A divergence response is closest to an operator-originated item once the value is gone: it is
    # input the Hub placed in the agent's queue with no sending agent, and `0019` rewrote `job` the
    # same way for the same reason.
    conn.execute(
        sa.text(
            "UPDATE inbound_queue_entries SET origin_type = 'operator' "
            "WHERE origin_type = 'divergence'"
        )
    )
    _replace_constraints(include_divergence=False)
