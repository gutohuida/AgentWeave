"""profiles run in parallel -- projects.profiles_run_in_parallel

Revision ID: 0183
Revises: 0182
Create Date: 2026-11-18 20:30:00.000000

`one-profile-runs-many-turns-at-once-on-different-tasks` (FR-15, D1). While a project's switch is
on, one profile may run several turns at once on different work. Off for every project, existing
ones included: with the switch off every flow runs one turn per profile at a time, as today.

Runs on the operator's :8000 data at its next restart. Additive: every existing row reads false,
which is the behaviour before this change; no existing row is read or rewritten.

Rollback: the downgrade drops the column (plain `DROP COLUMN`, SQLite 3.35+, as `0161` does); every
project then runs one turn per profile again. The operational rollback needs no migration: turn the
switch off.

Guarded for a database without the table (an upgrade from an early revision) and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0183"
down_revision = "0182"
branch_labels = None
depends_on = None

_COLUMN = "profiles_run_in_parallel"


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("projects"):
        return set()
    return {column["name"] for column in inspector.get_columns("projects")}


def upgrade() -> None:
    columns = _columns()
    if columns and _COLUMN not in columns:
        op.add_column(
            "projects",
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )


def downgrade() -> None:
    if _COLUMN in _columns():
        op.execute(sa.text(f"ALTER TABLE projects DROP COLUMN {_COLUMN}"))
