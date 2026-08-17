"""add spec_edit_proposals

Revision ID: 0076
Revises: 0075
Create Date: 2026-08-17 06:10:00.000000

`openspec/changes/2026-08-17-authoring-rigor-and-scope` (design D3): a `contract`/`gate`-rigor
document's submissions no longer write the live document directly — they land here, one row per
changed unit, until an operator accepts or rejects it.

Brand new table only. No existing column touched, no `CheckConstraint` naming a column — the
`models.py:1637-1640` SQLite undroppable-column trap `0074` had to work around does not apply here,
because `status`/`unit_kind`/`change_kind` are validated the same way `SpecDocument.rigor` already
is: refused on the way in by the one writer function (`spec_service.propose_edit`), not by a
table-level CHECK. Guarded for a missing parent table the way 0033/0034/0073/0074/0075 do.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None

_TABLE = "spec_edit_proposals"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _indexes(conn, table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(conn).get_indexes(table)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if _TABLE not in present and "spec_documents" in present:
        op.create_table(
            _TABLE,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column(
                "document_id", sa.String(64), sa.ForeignKey("spec_documents.id"), nullable=False
            ),
            sa.Column("unit_kind", sa.String(16), nullable=False),
            sa.Column("unit_key", sa.String(64), nullable=False),
            sa.Column("change_kind", sa.String(16), nullable=False),
            sa.Column("position_after_key", sa.String(64), nullable=True),
            sa.Column("proposed_payload", sa.JSON(), nullable=False),
            sa.Column("previous_payload", sa.JSON(), nullable=True),
            sa.Column("expected_digest", sa.String(64), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("proposer_actor_kind", sa.String(16), nullable=True),
            sa.Column("proposer_actor_name", sa.String(128), nullable=True),
            sa.Column("proposer_run_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_by_actor_name", sa.String(128), nullable=True),
            sa.Column("resolution_reason", sa.Text(), nullable=False, server_default=""),
        )
        op.create_index("ix_spec_edit_proposals_document_status", _TABLE, ["document_id", "status"])


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if _TABLE in present:
        if "ix_spec_edit_proposals_document_status" in _indexes(conn, _TABLE):
            op.drop_index("ix_spec_edit_proposals_document_status", table_name=_TABLE)
        op.drop_table(_TABLE)
