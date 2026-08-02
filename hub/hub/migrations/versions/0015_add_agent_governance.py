"""add agent and scheduled-work governance

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-02 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "projects" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("projects")}
    with op.batch_alter_table("projects", recreate="never") as batch_op:
        if "agent_budget" not in columns:
            batch_op.add_column(
                sa.Column("agent_budget", sa.Integer(), nullable=False, server_default="8")
            )
        if "allow_agent_jobs" not in columns:
            batch_op.add_column(
                sa.Column("allow_agent_jobs", sa.Boolean(), nullable=False, server_default="0")
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "projects" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("projects")}
    with op.batch_alter_table("projects", recreate="never") as batch_op:
        if "allow_agent_jobs" in columns:
            batch_op.drop_column("allow_agent_jobs")
        if "agent_budget" in columns:
            batch_op.drop_column("agent_budget")
