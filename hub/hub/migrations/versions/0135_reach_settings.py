"""what an agent may reach -- projects.default_permission_mode, projects.reach_grants, agents.reach_grants

Revision ID: 0135
Revises: 0134
Create Date: 2026-10-19 00:00:00.000000

`an-operator-sets-how-far-an-agent-reaches` (reach-1019, Tier 2). Three nullable columns: a
project's default posture for every agent, and the extra roots and hosts granted to a project and,
overriding it whole, to one agent. Existing rows read null -- no project default, no grants, an
agent inheriting -- so every project and agent behaves exactly as before. Nothing is backfilled or
rewritten. Plain `ADD COLUMN`s; no table is rebuilt.

The downgrade drops them (plain `DROP COLUMN`s, SQLite 3.35+); a project or agent then runs as it
did before this change, under its agent's own default or the built-in one.

Guarded for a database without the tables (an upgrade from an early revision), and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0135"
down_revision = "0134"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("projects", "default_permission_mode", lambda: sa.String(length=32)),
    ("projects", "reach_grants", sa.JSON),
    ("agents", "reach_grants", sa.JSON),
)


def _existing(table: str) -> set:
    bind = op.get_bind()
    if table not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    for table, column, kind in _COLUMNS:
        existing = _existing(table)
        if existing and column not in existing:
            op.add_column(table, sa.Column(column, kind(), nullable=True))


def downgrade() -> None:
    # Plain DROP COLUMNs, not batch rebuilds: rebuilding reflects the tables' foreign keys, and a
    # database upgraded from an early revision may lack the tables they name.
    for table, column, _kind in reversed(_COLUMNS):
        if column in _existing(table):
            op.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {column}"))
