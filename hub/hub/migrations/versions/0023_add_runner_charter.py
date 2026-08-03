"""add runners and charters tables, bind agents to each

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-03 17:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if "runners" not in tables:
        op.create_table(
            "runners",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("name", sa.String(256), nullable=False),
            sa.Column("cli", sa.String(16), nullable=False),
            sa.Column("model", sa.String(256), nullable=True),
            sa.Column("flags", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("cli IN ('claude', 'codex')", name="ck_runners_cli"),
        )
        op.create_index("ix_runners_project_name", "runners", ["project_id", "name"])

    if "charters" not in tables:
        op.create_table(
            "charters",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("name", sa.String(256), nullable=False),
            sa.Column("content", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_charters_project_name", "charters", ["project_id", "name"])

    if "agents" in tables:
        existing = {column["name"] for column in sa.inspect(conn).get_columns("agents")}
        for column, target in (("runner_id", "runners"), ("charter_id", "charters")):
            if column not in existing:
                op.add_column("agents", sa.Column(column, sa.String(64), nullable=True))
                # SQLite cannot add a foreign-key constraint after table creation
                # without rebuilding the table (see 0017's conversation_id precedent).
                if conn.dialect.name != "sqlite":
                    op.create_foreign_key(
                        f"fk_agents_{column}", "agents", target, [column], ["id"]
                    )


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if "agents" in tables:
        existing = {column["name"] for column in sa.inspect(conn).get_columns("agents")}
        for column in ("charter_id", "runner_id"):
            if column in existing:
                with op.batch_alter_table("agents", recreate="never") as batch_op:
                    batch_op.drop_column(column)

    if "charters" in tables:
        op.drop_table("charters")
    if "runners" in tables:
        op.drop_table("runners")
