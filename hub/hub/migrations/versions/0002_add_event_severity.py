"""add severity column to event_logs

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-15 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # On fresh installs, event_logs is created by create_all (which includes
    # the severity column from the model). Only run ALTER TABLE on existing
    # databases where the table already exists without the column.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "event_logs" not in inspector.get_table_names():
        return  # fresh install — create_all will add the column
    existing_cols = {c["name"] for c in inspector.get_columns("event_logs")}
    if "severity" not in existing_cols:
        op.add_column(
            "event_logs",
            sa.Column("severity", sa.String(10), nullable=False, server_default="info"),
        )
        op.create_index("ix_event_logs_severity", "event_logs", ["severity"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "event_logs" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("event_logs")}
    if "severity" in existing_cols:
        op.drop_index("ix_event_logs_severity", table_name="event_logs")
        op.drop_column("event_logs", "severity")
