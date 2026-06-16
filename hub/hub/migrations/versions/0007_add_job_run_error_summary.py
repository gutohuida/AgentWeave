"""add job run error summary

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-29

Updated 2026-06-15 (PR 7 / DB-4): cap `error_summary` at 500 characters to
prevent unbounded growth from agent output logs being persisted here.
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
        op.add_column(
            "job_runs",
            sa.Column("error_summary", sa.String(500), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "job_runs" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("job_runs")}
    if "error_summary" in existing_cols:
        op.drop_column("job_runs", "error_summary")
