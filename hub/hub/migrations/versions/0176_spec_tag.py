"""A spec's short tag -- spec_documents.tag

Revision ID: 0176
Revises: 0175
Create Date: 2026-11-12 16:00:00.000000

`find-a-spec-s-tasks-without-knowing-its-name`, task `picker`, FR-4. Task cards name their spec by a
tag of at most 24 characters, unique within the project: written by the author in a submission,
else derived from the title.

Runs on the operator's :8000 data at its next restart. One nullable column; no row is read or
rewritten, and a null tag is derived (and then stored) the first time a board asks. The downgrade
drops the column, losing only tags.

Guarded for a database without `spec_documents` and for the column already present.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0176"
down_revision = "0175"
branch_labels = None
depends_on = None


def _columns(conn) -> set:
    inspector = sa.inspect(conn)
    if "spec_documents" not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns("spec_documents")}


def upgrade() -> None:
    columns = _columns(op.get_bind())
    if not columns or "tag" in columns:
        return
    op.add_column("spec_documents", sa.Column("tag", sa.String(24), nullable=True))


def downgrade() -> None:
    if "tag" in _columns(op.get_bind()):
        op.execute(sa.text("ALTER TABLE spec_documents DROP COLUMN tag"))
