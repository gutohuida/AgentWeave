"""a loop's default agent is a staged edit like the rest of its definition

Revision ID: 0110
Revises: 0109
Create Date: 2026-09-27 02:00:00.000000

`a-flow-is-configured-from-its-own-tab` design D2/D7. One additive nullable column, the same
"no `batch_alter_table` recreate needed" shape as `0080`:

`loops.pending_agent` -- the agent a staged edit will name on the loop's job, applied at the loop's
next firing with the other pending fields (`scheduler._stage_pending_loop_edit`). NULL means "no
agent change staged", the untouched-vs-explicit convention the other pending columns use.

Guarded for a missing table, matching `0080`'s own precedent.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0110"
down_revision = "0109"
branch_labels = None
depends_on = None


def _columns(conn: sa.engine.Connection, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    present = "loops" in sa.inspect(conn).get_table_names()
    if present and "pending_agent" not in _columns(conn, "loops"):
        op.add_column("loops", sa.Column("pending_agent", sa.String(64), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    present = "loops" in sa.inspect(conn).get_table_names()
    if present and "pending_agent" in _columns(conn, "loops"):
        op.drop_column("loops", "pending_agent")
