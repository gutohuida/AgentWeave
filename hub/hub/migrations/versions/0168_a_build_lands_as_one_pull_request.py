"""a build lands as one pull request -- PR landing settings on projects, PR fields on builds

Revision ID: 0168
Revises: 0167
Create Date: 2026-11-06 22:00:00.000000

`a-build-lands-as-one-pull-request` (Tier 2), task `settings`, FR-1 and FR-7. Adds columns only:
`projects.pr_landing` and `projects.pr_single_commit` (both off, for new and existing projects:
pushing publishes the work, so it is never a default), and on `builds` the PR the build lands as
(`pr_number`, `pr_url`, `pr_state`, `pr_last_asked_at`, `pr_pushed_sha`, `pr_error`), all null.

Runs on the operator's :8000 data at its next restart. No existing row is read or rewritten; every
build already recorded lands on main or nowhere, which reads none of the new columns. The downgrade
drops them (plain `DROP COLUMN`, SQLite 3.35+, as 0167 does), losing only a PR landing setting and
the PR a build opened, which the build branch and GitHub still hold.

Guarded for a database without the table (an upgrade from an early revision) and for a column
already present (a database built by `create_all`) or already absent on downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0168"
down_revision = "0167"
branch_labels = None
depends_on = None

_PROJECT_COLUMNS = (
    ("pr_landing", lambda: sa.Boolean(), sa.text("0")),
    ("pr_single_commit", lambda: sa.Boolean(), sa.text("0")),
)
_BUILD_COLUMNS = (
    ("pr_number", lambda: sa.Integer()),
    ("pr_url", lambda: sa.String(512)),
    ("pr_state", lambda: sa.String(16)),
    ("pr_last_asked_at", lambda: sa.DateTime()),
    ("pr_pushed_sha", lambda: sa.String(64)),
    ("pr_error", lambda: sa.Text()),
)


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "projects" in tables:
        present = _columns(conn, "projects")
        for name, kind, default in _PROJECT_COLUMNS:
            if name not in present:
                op.add_column(
                    "projects",
                    sa.Column(name, kind(), nullable=False, server_default=default),
                )
    if "builds" in tables:
        present = _columns(conn, "builds")
        for name, kind in _BUILD_COLUMNS:
            if name not in present:
                op.add_column("builds", sa.Column(name, kind(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    for table, names in (
        ("builds", [name for name, _ in _BUILD_COLUMNS]),
        ("projects", [name for name, _, _ in _PROJECT_COLUMNS]),
    ):
        if table not in tables:
            continue
        present = _columns(conn, table)
        for name in names:
            if name in present:
                op.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {name}"))
