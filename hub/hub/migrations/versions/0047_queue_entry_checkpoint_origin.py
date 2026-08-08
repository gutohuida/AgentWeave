"""allow a checkpoint to be a queue entry origin

Revision ID: 0047
Revises: 0046
Create Date: 2026-08-09 01:05:00.000000

A checkpoint is delivered to its successor conversation as an inbound queue entry — conversation
scoped, which `_render_hub_agent_context` cannot be, because that writes one file per *agent* and
so cannot carry a per-conversation payload.

`checkpoint` is its own origin rather than a borrowed one. Under `automatic` no operator asked
for the delivery and no agent sent it, so `operator` and `agent` would both misstate where it came
from — and a signal reporting something other than what it names is the defect this whole
capability exists to remove.

The table is recreated because SQLite cannot alter a CHECK constraint in place. This follows 0019,
which built these two constraints the same way, including its guard on `projects`: recreating
reflects the table, and reflecting resolves its foreign key, so an upgrade running without
`projects` would raise `NoSuchTableError`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

_TABLES = {"inbound_queue_entries", "projects"}


def _replace_constraints(*, include_checkpoint: bool) -> None:
    origins = "'operator', 'agent', 'job'"
    origin_agent = (
        "(origin_type = 'operator' AND origin_agent IS NULL) OR "
        "(origin_type = 'agent' AND origin_agent IS NOT NULL) OR "
        "(origin_type = 'job' AND origin_agent IS NULL)"
    )
    if include_checkpoint:
        origins += ", 'checkpoint'"
        origin_agent += " OR (origin_type = 'checkpoint' AND origin_agent IS NULL)"

    with op.batch_alter_table("inbound_queue_entries", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_inbound_queue_origin_type", type_="check")
        batch_op.drop_constraint("ck_inbound_queue_origin_agent", type_="check")
        batch_op.create_check_constraint(
            "ck_inbound_queue_origin_type", f"origin_type IN ({origins})"
        )
        batch_op.create_check_constraint("ck_inbound_queue_origin_agent", origin_agent)


def upgrade() -> None:
    if set(sa.inspect(op.get_bind()).get_table_names()) >= _TABLES:
        _replace_constraints(include_checkpoint=True)


def downgrade() -> None:
    conn = op.get_bind()
    if not set(sa.inspect(conn).get_table_names()) >= _TABLES:
        return
    # Rewritten rather than deleted: the entry carried a real checkpoint to a real successor, and
    # dropping it would strand that conversation with nothing to resume from.
    conn.execute(
        sa.text(
            "UPDATE inbound_queue_entries SET origin_type = 'operator' "
            "WHERE origin_type = 'checkpoint'"
        )
    )
    _replace_constraints(include_checkpoint=False)
