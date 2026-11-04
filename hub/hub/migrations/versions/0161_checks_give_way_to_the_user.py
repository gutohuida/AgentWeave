"""checks give way to the user -- projects.checks_give_way

Revision ID: 0161
Revises: 0160
Create Date: 2026-11-04 12:00:00.000000

`checks-know-their-phase-and-give-way-to-the-user` (FR-5, FR-6). While a project's setting is on,
every process a check run starts runs below normal scheduling priority. Off for every project,
existing ones included (operator, 2026-11-04: no project's checks change speed without its say).

Additive, on live data: every existing row reads false, which is the behaviour before this change.

Rollback: the downgrade drops the column (plain `DROP COLUMN`, SQLite 3.35+, as `0151` does); checks
then run at normal priority again. The operational rollback needs no migration: turn the setting off.

Guarded for a database without the table (an upgrade from an early revision) and for a column already
present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0161"
down_revision = "0160"
branch_labels = None
depends_on = None


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("projects"):
        return set()
    return {column["name"] for column in inspector.get_columns("projects")}


def upgrade() -> None:
    columns = _columns()
    if columns and "checks_give_way" not in columns:
        op.add_column(
            "projects",
            sa.Column("checks_give_way", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )


def downgrade() -> None:
    if "checks_give_way" in _columns():
        op.execute(sa.text("ALTER TABLE projects DROP COLUMN checks_give_way"))
