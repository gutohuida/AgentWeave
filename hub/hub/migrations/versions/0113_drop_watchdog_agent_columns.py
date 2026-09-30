"""agents no longer register themselves -- drop the watchdog-era agent columns

Revision ID: 0113
Revises: 0112
Create Date: 2026-09-30 15:00:00.000000

`agents-no-longer-register-themselves`, design D2. Self-registration is deleted (the operator's
decision of 2026-08-29), and with it the four columns that described how a self-registered agent
was contacted: `contact_mode`, `self_registered`, `mcp_endpoint`, `spawn_cmd`. Nothing reads them:
the Hub starts every agent itself, from its bound runner. Measured `mode=ro` on the operator's
database 2026-09-30: 8 agents, none self-registered, all `contact_mode='watchdog-spawn'`.

Shaped like `0013`: `batch_alter_table("agents", recreate="never")`, so SQLite emits a direct
`ALTER TABLE ... DROP COLUMN` (SQLite >= 3.35) and the table keeps `ck_agents_lifecycle` and its
indexes without being rebuilt. None of the four columns is indexed or constrained, which is what
makes the direct drop legal. One guard per column, and one for a missing `agents` (an upgrade
starting from an early revision reaches this with only that revision's tables).

This must not fail quietly on the operator's table, where `self_registered` is `BOOLEAN NOT NULL`
with no default: the model no longer sets it, so a column left behind would fail every agent
insert. `test_migration_0113_leaves_the_real_agents_table_insertable` builds that exact table.

Downgrade re-adds the columns nullable (`self_registered` with a `'0'` default) and restores no
values: there are none worth restoring.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0113"
down_revision = "0112"
branch_labels = None
depends_on = None

_COLUMNS = ("contact_mode", "self_registered", "mcp_endpoint", "spawn_cmd")


def _agent_columns(conn) -> set[str] | None:
    inspector = sa.inspect(conn)
    if "agents" not in inspector.get_table_names():
        return None
    return {c["name"] for c in inspector.get_columns("agents")}


def upgrade() -> None:
    columns = _agent_columns(op.get_bind())
    if columns is None:
        return
    with op.batch_alter_table("agents", recreate="never") as batch_op:
        for name in _COLUMNS:
            if name in columns:
                batch_op.drop_column(name)


def downgrade() -> None:
    columns = _agent_columns(op.get_bind())
    if columns is None:
        return
    with op.batch_alter_table("agents", recreate="never") as batch_op:
        if "contact_mode" not in columns:
            batch_op.add_column(sa.Column("contact_mode", sa.String(32), nullable=True))
        if "self_registered" not in columns:
            batch_op.add_column(
                sa.Column("self_registered", sa.Boolean, nullable=True, server_default="0")
            )
        if "mcp_endpoint" not in columns:
            batch_op.add_column(sa.Column("mcp_endpoint", sa.String(256), nullable=True))
        if "spawn_cmd" not in columns:
            batch_op.add_column(sa.Column("spawn_cmd", sa.JSON, nullable=True))
