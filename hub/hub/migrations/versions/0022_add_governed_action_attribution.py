"""add attribution for governed agent and job actions

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-03 03:40:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_COLUMNS = {
    "agents": ("created_by_run_id",),
    "ai_jobs": ("created_by_run_id", "updated_by_run_id"),
    "job_runs": ("requested_by_run_id",),
}


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    for table, columns in _COLUMNS.items():
        if table not in tables:
            continue
        existing = {column["name"] for column in sa.inspect(conn).get_columns(table)}
        for column in columns:
            if column not in existing:
                op.add_column(table, sa.Column(column, sa.String(64), nullable=True))
            index_name = f"ix_{table}_{column}"
            indexes = {index["name"] for index in sa.inspect(conn).get_indexes(table)}
            if index_name not in indexes:
                op.create_index(index_name, table, [column])

    if "agent_job_deletions" not in tables:
        op.create_table(
            "agent_job_deletions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("job_id", sa.String(64), nullable=False),
            sa.Column("project_id", sa.String(64), nullable=False),
            sa.Column("agent", sa.String(64), nullable=False),
            sa.Column("run_id", sa.String(64), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_agent_job_deletions_job_id", "agent_job_deletions", ["job_id"])
        op.create_index("ix_agent_job_deletions_project_id", "agent_job_deletions", ["project_id"])
        op.create_index("ix_agent_job_deletions_run_id", "agent_job_deletions", ["run_id"])


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if "agent_job_deletions" in tables:
        op.drop_table("agent_job_deletions")
    for table, columns in reversed(tuple(_COLUMNS.items())):
        if table not in tables:
            continue
        for column in reversed(columns):
            index_name = f"ix_{table}_{column}"
            indexes = {index["name"] for index in sa.inspect(conn).get_indexes(table)}
            if index_name in indexes:
                op.drop_index(index_name, table_name=table)
            existing = {c["name"] for c in sa.inspect(conn).get_columns(table)}
            if column in existing:
                with op.batch_alter_table(table, recreate="never") as batch_op:
                    batch_op.drop_column(column)
