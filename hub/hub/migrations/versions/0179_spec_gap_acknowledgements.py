"""Acknowledged gaps on a specification document -- spec_gap_acknowledgements

Revision ID: 0179
Revises: 0178
Create Date: 2026-11-16 10:00:00.000000

`ready-means-the-same-thing-to-the-author-and-the-operator`, FR-3, FR-4. The author's agent or the
operator records that a gap is left on purpose, with a reason, beside the document and not inside
its payload.

Runs on the operator's :8000 data at its next restart. Creates one new table; no existing row is
read, deleted or rewritten. The downgrade drops the table, losing only the acknowledgements, never
a document. Guarded for a table already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0179"
down_revision = "0178"
branch_labels = None
depends_on = None

_TABLE = "spec_gap_acknowledgements"
_INDEX = "ix_spec_gap_acknowledgements_document"


def upgrade() -> None:
    if _TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("spec_documents.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("place", sa.String(255), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False, server_default=""),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("document_id", "code", "place", name="uq_spec_gap_ack_gap"),
    )
    op.create_index(_INDEX, _TABLE, ["document_id"])


def downgrade() -> None:
    if _TABLE in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index(_INDEX, table_name=_TABLE)
        op.drop_table(_TABLE)
