"""the operator's Overview visits and the manager's notes -- overview_visits, overview_notes

Revision ID: 0191
Revises: 0190
Create Date: 2026-11-23 10:00:00.000000

`overview-at-a-glance-with-dashboard-and-briefing-tabs` (FR-9, FR-11, D2, D5). `overview_visits`
holds, per project, when the operator last opened the Overview and the visit before that; the
Briefing's 'since you last looked' counts from the latter. `overview_notes` keeps every note the
overview-note manager job wrote; the latest is shown.

Runs on the operator's :8000 data at its next restart. Two new tables only: no existing row is read
or rewritten, and a project with no rows reads as never visited, with no note. The downgrade drops
both tables, losing only the visits and the notes.

Guarded for a database without `projects` (an upgrade from an early revision) and for a table
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0191"
down_revision = "0190"
branch_labels = None
depends_on = None


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    tables = _tables(op.get_bind())
    if "projects" not in tables:
        return
    if "overview_visits" not in tables:
        op.create_table(
            "overview_visits",
            sa.Column(
                "project_id",
                sa.String(64),
                sa.ForeignKey("projects.id"),
                primary_key=True,
                nullable=False,
            ),
            sa.Column("last_visit_at", sa.DateTime(), nullable=False),
            sa.Column("previous_visit_at", sa.DateTime(), nullable=True),
        )
    if "overview_notes" not in tables:
        op.create_table(
            "overview_notes",
            sa.Column("id", sa.String(64), primary_key=True, nullable=False),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("written_at", sa.DateTime(), nullable=False),
            sa.Column("trigger", sa.String(16), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("cites", sa.JSON(), nullable=False),
            sa.Column("firing_event_id", sa.String(64), nullable=True),
        )
        op.create_index("ix_overview_notes_project_id", "overview_notes", ["project_id"])


def downgrade() -> None:
    tables = _tables(op.get_bind())
    if "overview_notes" in tables:
        op.drop_index("ix_overview_notes_project_id", table_name="overview_notes")
        op.drop_table("overview_notes")
    if "overview_visits" in tables:
        op.drop_table("overview_visits")
