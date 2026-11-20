"""A conversation owns its document -- conversations.spec_document_id

Revision ID: 0188
Revises: 0187
Create Date: 2026-11-20 01:00:00.000000

`every-spec-entry-point-leads-into-the-journey`, FR-11 and FR-12 (design D3). One nullable column,
`conversations.spec_document_id`: the id of the document open in that conversation (the id, not
the path, so a rename keeps it), foreign key to `spec_documents.id` ON DELETE SET NULL, indexed.

Runs on the operator's :8000 data at its next restart. Adds one column and its index; no row is
changed and nothing is backfilled: every existing conversation starts with no document, which is
what any conversation reopened from the sidebar already shows today.

Added with SQLite's own `ALTER TABLE ... ADD COLUMN ... REFERENCES`, because alembic adds a
column's foreign key as a separate ALTER, which SQLite cannot run, and a batch recreate of the
live `conversations` table is the larger hazard for one additive column.

Rollback: the downgrade drops the index and the column, losing only which document each
conversation had open; code before this change reads neither. Guarded for a missing table, as
0033/0034 are.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "0188"
down_revision = "0187"
branch_labels = None
depends_on = None

_TABLE = "conversations"
_COLUMN = "spec_document_id"
_INDEX = "ix_conversations_spec_document_id"


def _columns(conn) -> set[str] | None:
    inspector = sa.inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return None
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _columns(conn)
    if present is None or _COLUMN in present:
        return
    if conn.dialect.name == "sqlite":
        op.execute(
            f"ALTER TABLE {_TABLE} ADD COLUMN {_COLUMN} VARCHAR(32) "
            "REFERENCES spec_documents (id) ON DELETE SET NULL"
        )
    else:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(32), nullable=True))
        op.create_foreign_key(
            "fk_conversations_spec_document_id",
            _TABLE,
            "spec_documents",
            [_COLUMN],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    conn = op.get_bind()
    present = _columns(conn)
    if present is None or _COLUMN not in present:
        return
    indexes = {ix["name"] for ix in sa.inspect(conn).get_indexes(_TABLE)}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name=_TABLE)
    if conn.dialect.name != "sqlite":
        op.drop_constraint("fk_conversations_spec_document_id", _TABLE, type_="foreignkey")
        op.drop_column(_TABLE, _COLUMN)
        return
    # The column this upgrade added carries its own REFERENCES clause, which SQLite drops in
    # place. A table `create_all` built instead names it in a table-level FOREIGN KEY, which SQLite
    # refuses to drop in place ("unknown column in foreign key definition"); only that table is
    # recreated, with the constraint left out.
    if _column_level_reference(conn):
        op.execute(f"ALTER TABLE {_TABLE} DROP COLUMN {_COLUMN}")
        return
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.drop_column(_COLUMN)


def _column_level_reference(conn) -> bool:
    created = conn.execute(
        sa.text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
        {"name": _TABLE},
    ).scalar()
    table_level = re.compile(rf'FOREIGN\s+KEY\s*\(\s*["`]?{_COLUMN}["`]?\s*\)', re.IGNORECASE)
    return not table_level.search(created or "")
