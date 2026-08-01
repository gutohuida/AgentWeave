"""add runs table

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "runs" in inspector.get_table_names():
        return  # fresh install — create_all already made the table

    op.create_table(
        "runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("agent", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_runs_project_agent", "runs", ["project_id", "agent"])
    op.create_index("ix_runs_project_status", "runs", ["project_id", "status"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "runs" in inspector.get_table_names():
        op.drop_table("runs")
