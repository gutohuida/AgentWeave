"""the PR's CI is the full check -- CI's result on the build and on each pushed task

Revision ID: 0170
Revises: 0169
Create Date: 2026-11-07 12:00:00.000000

`the-pr-s-ci-is-the-full-check` (Tier 2), task `read-ci`, FR-4, FR-5 and FR-11. Adds nullable
columns only: `builds.pr_ci` (CI's last read on the PR's head commit), `builds.pr_ci_pushed_at`
(when that head was pushed, which the cutoff on asking counts from) and `task_landings.ci` (CI's
result on the commit that landing pushed).

Runs on the operator's :8000 data at its next restart. No existing row is read or rewritten: every
existing row reads null, which is what a build or landing with the CI setting off reads. The
downgrade drops the columns (plain `DROP COLUMN`, SQLite 3.35+, as 0168 does), losing only the
last CI reads, which the next ask after an upgrade produces again.

Guarded for a database without the tables (an upgrade from an early revision) and for a column
already present (a database built by `create_all`) or already absent on downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0170"
down_revision = "0169"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("builds", "pr_ci", lambda: sa.JSON()),
    ("builds", "pr_ci_pushed_at", lambda: sa.DateTime()),
    ("task_landings", "ci", lambda: sa.JSON()),
)


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    for table, name, kind in _COLUMNS:
        if table in tables and name not in _columns(conn, table):
            op.add_column(table, sa.Column(name, kind(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    for table, name, _ in _COLUMNS:
        if table in tables and name in _columns(conn, table):
            op.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {name}"))
