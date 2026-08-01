"""drop agent pilot columns

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-01 00:00:00.000000

Pilot mode is removed. Uses `batch_alter_table(..., recreate="never")` so SQLite
emits a direct `ALTER TABLE ... DROP/ADD COLUMN` (supported since SQLite 3.35)
instead of the full copy-and-recreate batch strategy — recreation would need to
reflect the `agents` table's FK target (`projects`), which doesn't exist yet in
an alembic-only migration context (that table is created separately by
`Base.metadata.create_all`, not by any migration).
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {c["name"] for c in inspector.get_columns("agents")}

    with op.batch_alter_table("agents", recreate="never") as batch_op:
        if "pilot" in columns:
            batch_op.drop_column("pilot")
        if "registered_session_id" in columns:
            batch_op.drop_column("registered_session_id")


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {c["name"] for c in inspector.get_columns("agents")}

    with op.batch_alter_table("agents", recreate="never") as batch_op:
        if "registered_session_id" not in columns:
            batch_op.add_column(sa.Column("registered_session_id", sa.String(128), nullable=True))
        if "pilot" not in columns:
            batch_op.add_column(sa.Column("pilot", sa.Boolean, default=False, nullable=False))
