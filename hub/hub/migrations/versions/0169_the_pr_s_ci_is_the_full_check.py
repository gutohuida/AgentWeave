"""the PR's CI is the full check -- the CI setting, its check names, interval and cutoff

Revision ID: 0169
Revises: 0168
Create Date: 2026-11-07 11:00:00.000000

`the-pr-s-ci-is-the-full-check` (Tier 2), task `settings`, FR-1, FR-3 and FR-10. Adds columns to
`projects` only: `pr_ci_full_check` (off, for new and existing projects alike: the operator turns it
on), `pr_ci_check_names` (an empty list), `pr_ci_interval_minutes` (2) and `pr_ci_cutoff_minutes`
(60).

Runs on the operator's :8000 data at its next restart. No existing row is read or rewritten. The
downgrade drops the columns (plain `DROP COLUMN`, SQLite 3.35+, as 0168 does), losing only the CI
setting: those projects fall back to slice 1's local landing checks, which read none of them.

Guarded for a database without the table (an upgrade from an early revision) and for a column
already present (a database built by `create_all`) or already absent on downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0169"
down_revision = "0168"
branch_labels = None
depends_on = None

_PROJECT_COLUMNS = (
    ("pr_ci_full_check", lambda: sa.Boolean(), sa.text("0")),
    ("pr_ci_check_names", lambda: sa.JSON(), sa.text("'[]'")),
    ("pr_ci_interval_minutes", lambda: sa.Integer(), sa.text("2")),
    ("pr_ci_cutoff_minutes", lambda: sa.Integer(), sa.text("60")),
)


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if "projects" not in set(sa.inspect(conn).get_table_names()):
        return
    present = _columns(conn, "projects")
    for name, kind, default in _PROJECT_COLUMNS:
        if name not in present:
            op.add_column(
                "projects", sa.Column(name, kind(), nullable=False, server_default=default)
            )


def downgrade() -> None:
    conn = op.get_bind()
    if "projects" not in set(sa.inspect(conn).get_table_names()):
        return
    present = _columns(conn, "projects")
    for name, _, _ in _PROJECT_COLUMNS:
        if name in present:
            op.execute(sa.text(f"ALTER TABLE projects DROP COLUMN {name}"))
