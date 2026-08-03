"""add durable per-turn accounting

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-03 02:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "projects" in tables:
        project_columns = {column["name"] for column in inspector.get_columns("projects")}
        if "token_budget" not in project_columns:
            op.add_column("projects", sa.Column("token_budget", sa.Integer(), nullable=True))

    if "runs" in tables:
        run_columns = {column["name"] for column in inspector.get_columns("runs")}
        if "initiator" not in run_columns:
            op.add_column(
                "runs",
                sa.Column(
                    "initiator", sa.String(16), nullable=False, server_default="operator"
                ),
            )

    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if "turn_usage" not in tables and {"projects", "runs"} <= tables:
        op.create_table(
            "turn_usage",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("run_id", sa.String(64), sa.ForeignKey("runs.id"), nullable=False),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("agent", sa.String(64), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("runner", sa.String(32), nullable=True),
            sa.Column("model", sa.String(128), nullable=True),
            sa.Column("input_tokens", sa.Integer(), nullable=True),
            sa.Column("output_tokens", sa.Integer(), nullable=True),
            sa.Column("total_tokens", sa.Integer(), nullable=True),
            sa.Column("cache_read_tokens", sa.Integer(), nullable=True),
            sa.Column("cache_write_tokens", sa.Integer(), nullable=True),
            sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
            sa.Column("api_equivalent_usd_micros", sa.Integer(), nullable=True),
            sa.Column("allowance", sa.JSON(), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "status IN ('measured', 'unavailable')", name="ck_turn_usage_status"
            ),
            sa.CheckConstraint(
                "(status = 'measured' AND total_tokens IS NOT NULL) OR "
                "(status = 'unavailable' AND input_tokens IS NULL AND output_tokens IS NULL "
                "AND total_tokens IS NULL AND cache_read_tokens IS NULL "
                "AND cache_write_tokens IS NULL AND reasoning_tokens IS NULL)",
                name="ck_turn_usage_availability",
            ),
            sa.CheckConstraint(
                "total_tokens IS NULL OR total_tokens >= 0",
                name="ck_turn_usage_total_nonnegative",
            ),
            sa.UniqueConstraint("run_id", name="uq_turn_usage_run_id"),
        )
        op.create_index("ix_turn_usage_project_agent", "turn_usage", ["project_id", "agent"])
        op.create_index(
            "ix_turn_usage_project_observed", "turn_usage", ["project_id", "observed_at"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if "turn_usage" in tables:
        op.drop_table("turn_usage")
    if "runs" in tables:
        columns = {column["name"] for column in inspector.get_columns("runs")}
        if "initiator" in columns:
            with op.batch_alter_table("runs", recreate="never") as batch_op:
                batch_op.drop_column("initiator")
    if "projects" in tables:
        columns = {column["name"] for column in inspector.get_columns("projects")}
        if "token_budget" in columns:
            with op.batch_alter_table("projects", recreate="never") as batch_op:
                batch_op.drop_column("token_budget")
