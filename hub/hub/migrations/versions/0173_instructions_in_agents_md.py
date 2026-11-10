"""AGENTS.md as a project's instructions, where chosen -- projects.instructions_in_agents_md

Revision ID: 0173
Revises: 0172
Create Date: 2026-11-10 12:00:00.000000

`a-new-project-starts-as-a-git-repository-with-an-agents-md`, task `instructions-in-agents-md`,
FR-11. Adds the boolean column `projects.instructions_in_agents_md`, default false.

Runs on the operator's :8000 data at its next restart. No existing row is read or rewritten: every
existing project reads false, which is today's behaviour -- instructions from the
`project_instructions` row. The downgrade drops the column (plain `DROP COLUMN`, SQLite 3.35+, as
0171 does); the instructions row was never changed, so a project returns to it as it was.

Guarded for a database without the table and for a column already present (a database built by
`create_all`) or already absent on downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0173"
down_revision = "0172"
branch_labels = None
depends_on = None


def _columns(conn) -> set:
    if "projects" not in set(sa.inspect(conn).get_table_names()):
        return set()
    return {c["name"] for c in sa.inspect(conn).get_columns("projects")}


def upgrade() -> None:
    columns = _columns(op.get_bind())
    if columns and "instructions_in_agents_md" not in columns:
        op.add_column(
            "projects",
            sa.Column(
                "instructions_in_agents_md",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade() -> None:
    if "instructions_in_agents_md" in _columns(op.get_bind()):
        op.execute(sa.text("ALTER TABLE projects DROP COLUMN instructions_in_agents_md"))
