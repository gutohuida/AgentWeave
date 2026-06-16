"""cap job run error summary to 500 chars

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-15

PR 7 / DB-4: Existing deployments that ran 0007 with the old unbounded
`Text()` type need their `job_runs.error_summary` column altered to
`String(500)`. Uses `batch_alter_table` so SQLite (which has no native
`ALTER COLUMN`) works as well as PostgreSQL.
"""

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "job_runs" not in inspector.get_table_names():
        return  # fresh install — 0007 already created the column as String(500)
    existing_cols = {c["name"] for c in inspector.get_columns("job_runs")}
    if "error_summary" in existing_cols:
        with op.batch_alter_table("job_runs") as batch_op:
            batch_op.alter_column(
                "error_summary",
                type_=sa.String(500),
                existing_type=sa.Text(),
                existing_nullable=True,
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "job_runs" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("job_runs")}
    if "error_summary" in existing_cols:
        with op.batch_alter_table("job_runs") as batch_op:
            batch_op.alter_column(
                "error_summary",
                type_=sa.Text(),
                existing_type=sa.String(500),
                existing_nullable=True,
            )
