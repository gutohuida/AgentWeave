"""add job run error summary

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "job_runs" not in inspector.get_table_names():
        return  # fresh install — create_all will add the column
    existing_cols = {c["name"] for c in inspector.get_columns("job_runs")}
    if "error_summary" not in existing_cols:
        op.add_column("job_runs", sa.Column("error_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "job_runs" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("job_runs")}
    if "error_summary" in existing_cols:
        op.drop_column("job_runs", "error_summary")
