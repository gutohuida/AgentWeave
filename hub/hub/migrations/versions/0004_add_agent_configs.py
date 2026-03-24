"""add agent_configs table

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-22 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create agent_configs table
    op.create_table(
        "agent_configs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False, index=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="delegate"),
        sa.Column("yolo_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("context_file", sa.String(128), nullable=False, server_default="AGENTS.md"),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Create unique index on project_id + agent_name
    op.create_index(
        "ix_agent_configs_project_agent",
        "agent_configs",
        ["project_id", "agent_name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_configs_project_agent", table_name="agent_configs")
    op.drop_table("agent_configs")
