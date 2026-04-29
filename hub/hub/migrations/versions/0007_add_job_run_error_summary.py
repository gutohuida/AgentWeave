"""add job run error summary

Revision ID: 0007_add_job_run_error_summary
Revises: 0006_add_agent_config_column
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_add_job_run_error_summary"
down_revision = "0006_add_agent_config_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_runs", sa.Column("error_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("job_runs", "error_summary")
