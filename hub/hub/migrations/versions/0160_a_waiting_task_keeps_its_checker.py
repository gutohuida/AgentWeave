"""a waiting task keeps its checker -- tasks.checker

Revision ID: 0160
Revises: 0159
Create Date: 2026-11-02 12:00:00.000000

`every-task-comes-with-a-recommended-builder-and-checker` (FR-10). A task filed against a spec whose
build was stopped waits with no build, and the next Build takes it in; a checker it named has to wait
with it, as its builder already does in `tasks.builder`.

Additive and nullable, on live data: no existing row changes, and null reads as naming nobody.

Rollback: the downgrade drops the column (plain `DROP COLUMN`, SQLite 3.35+, as `0152` does). A task
in a build keeps its checker in the build's people; one still waiting loses it and takes the default.

Guarded for a database without the table (an upgrade from an early revision) and for a column already
present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0160"
down_revision = "0159"
branch_labels = None
depends_on = None


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("tasks"):
        return set()
    return {column["name"] for column in inspector.get_columns("tasks")}


def upgrade() -> None:
    columns = _columns()
    if columns and "checker" not in columns:
        op.add_column("tasks", sa.Column("checker", sa.String(64), nullable=True))


def downgrade() -> None:
    if "checker" in _columns():
        op.drop_column("tasks", "checker")
