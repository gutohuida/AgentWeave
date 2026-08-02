"""add stable agent colour index

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-02 02:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agents" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("agents")}
    if "color_index" not in columns:
        with op.batch_alter_table("agents", recreate="never") as batch_op:
            batch_op.add_column(sa.Column("color_index", sa.Integer(), nullable=True))

    # Backfill existing rows deterministically: registration order (created_at) per
    # project, so a rename or Hub restart never reshuffles an already-assigned colour.
    rows = conn.execute(
        sa.text(
            "SELECT id, project_id FROM agents WHERE color_index IS NULL "
            "ORDER BY project_id, created_at, id"
        )
    ).fetchall()
    next_index: dict = {}
    for row in rows:
        idx = next_index.get(row.project_id, 0)
        conn.execute(
            sa.text("UPDATE agents SET color_index = :idx WHERE id = :id"),
            {"idx": idx, "id": row.id},
        )
        next_index[row.project_id] = idx + 1


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agents" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("agents")}
    if "color_index" in columns:
        with op.batch_alter_table("agents", recreate="never") as batch_op:
            batch_op.drop_column("color_index")
