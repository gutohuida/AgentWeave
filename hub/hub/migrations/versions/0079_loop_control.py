"""a loop's queue-extension control is an explicit per-loop setting

Revision ID: 0079
Revises: 0078
Create Date: 2026-08-19 04:30:00.000000

`2026-08-18-a-loop-writes-its-own-queue` design D10 (addendum, task A1.1). One additive nullable
column, same "no `batch_alter_table` recreate needed" shape as `0075`/`0077`/`0078`:

`loops.control` — who decides whether this loop's queue may be extended: NULL (the default,
meaning "the operator", never a stored copy of that default — mirrors `Agent.default_permission_mode`,
`models.py:196`) or `"creator"` (delegated to the loop's creator agent). See `Loop.control`'s own
comment in `models.py` for the full reasoning.

Guarded for a missing table, matching `0071`/`0073`/`0075`/`0077`/`0078`'s own precedent for an
upgrade starting from an early revision.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def _tables(conn: sa.engine.Connection) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn: sa.engine.Connection, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "loops" in present:
        columns = _columns(conn, "loops")
        if "control" not in columns:
            op.add_column("loops", sa.Column("control", sa.String(32), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "loops" in present and "control" in _columns(conn, "loops"):
        op.drop_column("loops", "control")
