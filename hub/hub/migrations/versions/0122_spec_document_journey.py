"""a spec is written one step at a time -- spec_documents.step and .size

Revision ID: 0122
Revises: 0121
Create Date: 2026-10-08 00:00:00.000000

`a-spec-is-written-one-step-at-a-time` (step-journey, Tier 2). Two nullable columns. The backfill
places every exploring change document at `intake` when it has written no requirements and at
`requirements` otherwise; every other document (another phase, a roadmap, a capability) has no step.
No size is guessed: a null size is briefed as large.

`explore_closed_at` is kept and simply no longer read, so a downgraded Hub gates proposing as
before. Downgrade drops both columns. Guarded for a missing table, and for columns already present
(a database built by `create_all` from these models and stamped at an earlier revision).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0122"
down_revision = "0121"
branch_labels = None
depends_on = None


def _columns(conn) -> set:
    inspector = sa.inspect(conn)
    if "spec_documents" not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns("spec_documents")}


def upgrade() -> None:
    conn = op.get_bind()
    columns = _columns(conn)
    if not columns:
        return
    with op.batch_alter_table("spec_documents") as batch_op:
        if "step" not in columns:
            batch_op.add_column(sa.Column("step", sa.String(48), nullable=True))
        if "size" not in columns:
            batch_op.add_column(sa.Column("size", sa.String(16), nullable=True))
    conn.execute(
        sa.text(
            "UPDATE spec_documents SET step = CASE "
            "WHEN requirement_digests IS NULL OR requirement_digests IN ('{}', 'null') "
            "THEN 'intake' ELSE 'requirements' END "
            "WHERE kind = 'change-spec' AND phase = 'exploring' AND step IS NULL"
        )
    )


def downgrade() -> None:
    columns = _columns(op.get_bind())
    if not {"step", "size"} & columns:
        return
    with op.batch_alter_table("spec_documents") as batch_op:
        for name in ("size", "step"):
            if name in columns:
                batch_op.drop_column(name)
