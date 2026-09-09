"""record whether a run's harness actually started the injected MCP server

Revision ID: 0102
Revises: 0101
Create Date: 2026-09-09 02:20:00.000000

`2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`, §4, designs D7/D9/D10.

The Hub puts its canonical MCP server on the runner's command line and has, since `d279d22`,
assumed that a configured server is an available one. A harness that forbids MCP by policy takes
the configuration and starts nothing, and the run is told in its first line to call tools that are
not there. Nothing recorded which of the two happened, so nothing could tell them apart.

This column is that record: the instant the adapter announced itself, or NULL. It is written by
`POST /api/v1/agent-actions/mcp-adapter-online`, which the adapter calls before it serves, and read
only by `launchability.described_access_path` — as a fact about the *next* run of that agent, since
a run's turn-start notice is composed before the run exists.

**Nullable, no server default, no backfill**, following `0096`'s `workspace_dir` and `0101`'s two
columns. NULL means "never reported in", which is exactly true of every run that predates the
announce, and a backfilled timestamp would assert that every historical harness honoured the
injection — the claim this change exists to stop the Hub from making for free.

It deliberately does **not** decide whether the server is injected. That stays the operator's
`hub_client`, because injection also decides the run's permission posture (`design.md` D9), and an
inference that moved containment as a side effect is what the requirement's "A truer description
does not silently widen permission" scenario forbids.

Guarded for a missing table the way `0033`/`0034`/`0075`/`0095`/`0096`/`0100`/`0101` are: an
upgrade starting from an early revision reaches here with only that revision's tables, and
`create_all` builds the rest from the model with the column already on it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None

_TABLE = "runs"
_COLUMN = "mcp_adapter_online_at"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if _TABLE not in _tables(conn):
        return
    if _COLUMN not in _columns(conn, _TABLE):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.DateTime(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if _TABLE in _tables(conn) and _COLUMN in _columns(conn, _TABLE):
        op.drop_column(_TABLE, _COLUMN)
