"""add agent table for pilot mode

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-10 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agents" not in inspector.get_table_names():
        op.create_table(
            "agents",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("name", sa.String(64), nullable=False, index=True),
            sa.Column("pilot", sa.Boolean, default=False, nullable=False),
            sa.Column("registered_session_id", sa.String(128), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_agents_project_name", "agents", ["project_id", "name"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agents" in inspector.get_table_names():
        op.drop_index("ix_agents_project_name", table_name="agents")
        op.drop_table("agents")
