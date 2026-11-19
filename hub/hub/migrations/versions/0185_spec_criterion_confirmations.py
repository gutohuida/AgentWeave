"""Confirmed acceptance criteria -- spec_criterion_confirmations

Revision ID: 0185
Revises: 0184
Create Date: 2026-11-19 01:00:00.000000

`existing-behaviour-is-caught-before-the-build` D1. An agent records, per acceptance criterion, that
it checked the criterion against the current code and that it is new behaviour or a guard. Kept
beside the document, never in its payload.

Runs on the operator's :8000 data at its next restart. Creates one new table; no existing row is
read, deleted or rewritten. Its live effect is the approval gate, not the table: every exploring
change document with criteria is refused at approval until an agent confirms them (the operator's
choice, 2026-11-18).

Rollback: the downgrade drops the table, losing only the confirmations, never a document; removing
`criteria_unconfirmed` from `spec_completeness.REFUSAL_CODES` reverts the gate without touching
data. Guarded for a database without `spec_documents` (an upgrade from an early revision, as
0033/0034 are) and for the table already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0185"
down_revision = "0184"
branch_labels = None
depends_on = None

_TABLE = "spec_criterion_confirmations"
_INDEX = "ix_spec_criterion_confirmations_document"


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if _TABLE in tables or "spec_documents" not in tables:
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("spec_documents.id"), nullable=False),
        sa.Column("criterion_key", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("criterion_digest", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("document_id", "criterion_key", name="uq_spec_criterion_confirmation"),
    )
    op.create_index(_INDEX, _TABLE, ["document_id"])


def downgrade() -> None:
    if _TABLE in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index(_INDEX, table_name=_TABLE)
        op.drop_table(_TABLE)
