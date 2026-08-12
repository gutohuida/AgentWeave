"""add spec_documents and spec_document_events

Revision ID: 0065
Revises: 0064
Create Date: 2026-08-12 18:20:00.000000

The document is the file on disk. These two tables hold what cannot live in a file the operator can
edit: the phase, the digests that detect an edit made outside the Hub, and the append-only history
of who changed what.

`spec_document_events` is written from the first document and read by nothing in this change. That
is deliberate — history cannot be backfilled, and a telemetry query added later would report on the
fraction of work that happened after the query existed, which reads as complete and is not.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

_PHASES = ("exploring", "proposed", "approved")
_ACTORS = ("operator", "agent", "system")
_ORIGINS = ("control", "submission", "lifecycle")


def _tables(conn) -> set[str]:
    """An upgrade starting from an early revision reaches this migration with only the tables
    those revisions created; `create_all` builds the rest from the model."""
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    present = _tables(op.get_bind())

    if "spec_documents" not in present:
        op.create_table(
            "spec_documents",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("path", sa.String(255), nullable=False),
            sa.Column("title", sa.String(512), nullable=False, server_default=""),
            sa.Column("kind", sa.String(32), nullable=False, server_default="change-spec"),
            sa.Column("phase", sa.String(32), nullable=False, server_default="exploring"),
            sa.Column("content_digest", sa.String(64), nullable=True),
            sa.Column("requirement_digests", sa.JSON, nullable=True),
            sa.Column("explore_closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("project_id", "path", name="uq_spec_documents_project_path"),
            sa.CheckConstraint(
                "phase IN ('" + "', '".join(_PHASES) + "')",
                name="ck_spec_documents_phase",
            ),
        )

    if "spec_document_events" not in present:
        op.create_table(
            "spec_document_events",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column(
                "document_id", sa.String(64), sa.ForeignKey("spec_documents.id"), nullable=False
            ),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("actor_kind", sa.String(16), nullable=False),
            sa.Column("actor", sa.String(128), nullable=False, server_default=""),
            sa.Column("origin", sa.String(16), nullable=False),
            sa.Column("run_id", sa.String(64), nullable=True),
            sa.Column("detail", sa.JSON, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "actor_kind IN ('" + "', '".join(_ACTORS) + "')",
                name="ck_spec_document_events_actor_kind",
            ),
            sa.CheckConstraint(
                "origin IN ('" + "', '".join(_ORIGINS) + "')",
                name="ck_spec_document_events_origin",
            ),
        )
        op.create_index(
            "ix_spec_document_events_document",
            "spec_document_events",
            ["document_id", "created_at"],
        )


def downgrade() -> None:
    present = _tables(op.get_bind())
    if "spec_document_events" in present:
        op.drop_index("ix_spec_document_events_document", table_name="spec_document_events")
        op.drop_table("spec_document_events")
    if "spec_documents" in present:
        op.drop_table("spec_documents")
