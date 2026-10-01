"""a run reaches the Hub without MCP -- runs.harness_mcp_status, runs.plane_surface

Revision ID: 0115
Revises: 0114
Create Date: 2026-10-01 18:00:00.000000

`a-run-reaches-the-hub-without-mcp`, design D1. Two nullable columns on `runs`:

- `harness_mcp_status`: `connected` | `failed` | `absent`, or NULL for a run never tested --
  whether this run's harness started the Hub's tool server it was given. The latest tested run of
  an agent decides what its next run is told, replacing the positive-only, permanent grounds
  `mcp_adapter_online_at` gave (F340).
- `plane_surface`: `mcp` | `shim` -- what this run was told it reaches the Hub with.

Backfill: `harness_mcp_status = 'connected'` wherever `mcp_adapter_online_at` is set, so an agent
with grounds today keeps them on its first turn after the upgrade; the first negative test after
it is what revokes them. `plane_surface` is not backfilled: what an earlier run was told was not
recorded, and a guess would be indistinguishable from a record.

Guarded for a missing `runs` (an upgrade starting from an early revision reaches this with only
that revision's tables), as `0033`/`0034` do.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0115"
down_revision = "0114"
branch_labels = None
depends_on = None

_TABLE = "runs"
_STATUS = "harness_mcp_status"
_SURFACE = "plane_surface"


def _columns(conn) -> set[str] | None:
    inspector = sa.inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return None
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    conn = op.get_bind()
    columns = _columns(conn)
    if columns is None:
        return
    with op.batch_alter_table(_TABLE, recreate="never") as batch_op:
        if _STATUS not in columns:
            batch_op.add_column(sa.Column(_STATUS, sa.String(16), nullable=True))
        if _SURFACE not in columns:
            batch_op.add_column(sa.Column(_SURFACE, sa.String(8), nullable=True))
    if "mcp_adapter_online_at" in columns:
        conn.execute(
            sa.text(
                f"UPDATE {_TABLE} SET {_STATUS} = 'connected' "
                f"WHERE mcp_adapter_online_at IS NOT NULL AND {_STATUS} IS NULL"
            )
        )


def downgrade() -> None:
    columns = _columns(op.get_bind())
    if columns is None:
        return
    with op.batch_alter_table(_TABLE, recreate="never") as batch_op:
        if _SURFACE in columns:
            batch_op.drop_column(_SURFACE)
        if _STATUS in columns:
            batch_op.drop_column(_STATUS)
