"""add agent_outputs table

Revision ID: 0001
Revises:
Create Date: 2026-03-14 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_outputs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False
        ),
        sa.Column("agent", sa.String(64), nullable=False, index=True),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_agent_outputs_project_agent", "agent_outputs", ["project_id", "agent"]
    )
    op.create_index(
        "ix_agent_outputs_project_ts", "agent_outputs", ["project_id", "timestamp"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_outputs_project_ts", table_name="agent_outputs")
    op.drop_index("ix_agent_outputs_project_agent", table_name="agent_outputs")
    op.drop_table("agent_outputs")
