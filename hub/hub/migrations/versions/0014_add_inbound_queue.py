"""add inbound queue and turn limits

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-01 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "projects" in tables:
        project_columns = {c["name"] for c in inspector.get_columns("projects")}
        with op.batch_alter_table("projects", recreate="never") as batch_op:
            if "hop_budget" not in project_columns:
                batch_op.add_column(
                    sa.Column("hop_budget", sa.Integer(), nullable=False, server_default="6")
                )
            if "turn_delivery_cap" not in project_columns:
                batch_op.add_column(
                    sa.Column(
                        "turn_delivery_cap", sa.Integer(), nullable=False, server_default="10"
                    )
                )

    if "runs" in tables:
        run_columns = {c["name"] for c in inspector.get_columns("runs")}
        if "turn_depth" not in run_columns:
            with op.batch_alter_table("runs", recreate="never") as batch_op:
                batch_op.add_column(sa.Column("turn_depth", sa.Integer(), nullable=True))

    if "inbound_queue_entries" not in tables:
        op.create_table(
            "inbound_queue_entries",
            sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("id", sa.String(64), unique=True, nullable=False),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("agent", sa.String(64), nullable=False),
            sa.Column("origin_type", sa.String(16), nullable=False),
            sa.Column("origin_agent", sa.String(64), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("hop_depth", sa.Integer(), nullable=False),
            sa.Column("state", sa.String(16), nullable=False, server_default="queued"),
            sa.Column("delivered_in_run_id", sa.String(64), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("message_id", sa.String(64), nullable=True),
            sa.Column("session_mode", sa.String(16), nullable=True),
            sa.Column("session_id", sa.String(128), nullable=True),
            sa.Column("work_dir", sa.String(4096), nullable=True),
            sa.CheckConstraint(
                "origin_type IN ('operator', 'agent')", name="ck_inbound_queue_origin_type"
            ),
            sa.CheckConstraint(
                "state IN ('queued', 'delivered', 'withdrawn')",
                name="ck_inbound_queue_state",
            ),
            sa.CheckConstraint("hop_depth >= 0", name="ck_inbound_queue_hop_depth"),
            sa.CheckConstraint(
                "(origin_type = 'operator' AND origin_agent IS NULL) OR "
                "(origin_type = 'agent' AND origin_agent IS NOT NULL)",
                name="ck_inbound_queue_origin_agent",
            ),
        )
        op.create_index(
            "ix_inbound_queue_project_agent_state_arrival",
            "inbound_queue_entries",
            ["project_id", "agent", "state", "sequence"],
        )
        op.create_index(
            "ix_inbound_queue_delivered_run",
            "inbound_queue_entries",
            ["delivered_in_run_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "inbound_queue_entries" in inspector.get_table_names():
        op.drop_table("inbound_queue_entries")
    tables = set(inspector.get_table_names())
    if "runs" in tables:
        with op.batch_alter_table("runs", recreate="never") as batch_op:
            if "turn_depth" in {c["name"] for c in inspector.get_columns("runs")}:
                batch_op.drop_column("turn_depth")
    if "projects" in tables:
        project_columns = {c["name"] for c in inspector.get_columns("projects")}
        with op.batch_alter_table("projects", recreate="never") as batch_op:
            if "turn_delivery_cap" in project_columns:
                batch_op.drop_column("turn_delivery_cap")
            if "hop_budget" in project_columns:
                batch_op.drop_column("hop_budget")
