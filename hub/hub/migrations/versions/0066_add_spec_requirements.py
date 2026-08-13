"""add spec_requirements and spec_requirement_revisions

Revision ID: 0066
Revises: 0065
Create Date: 2026-08-13 20:40:00.000000

The requirement index. Derived from the documents and reconstructible from them, so dropping either
table costs a reindex and nothing else — which is the property that lets it be an index rather than a
second source of truth.

`spec_requirement_revisions` is append-only and, like `spec_document_events`, **cannot be
backfilled**: a digest that was never recorded is not recoverable from the current file. It ships
before anything reads it for that reason alone.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None

_STATES = ("active", "retired")
_SOURCES = ("hub", "external")
_CLASSIFICATIONS = ("created", "reworded", "retired", "restored")
_ACTORS = ("operator", "agent", "system")


def _tables(conn) -> set[str]:
    """An upgrade starting from an early revision reaches this migration with only the tables
    those revisions created; `create_all` builds the rest from the model."""
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    present = _tables(op.get_bind())

    if "spec_requirements" not in present:
        op.create_table(
            "spec_requirements",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column(
                "document_id", sa.String(64), sa.ForeignKey("spec_documents.id"), nullable=False
            ),
            sa.Column("identifier", sa.String(32), nullable=False),
            sa.Column("key", sa.String(64), nullable=False),
            sa.Column("state", sa.String(16), nullable=False, server_default="active"),
            sa.Column("digest", sa.String(64), nullable=False),
            sa.Column("digest_version", sa.Integer, nullable=False, server_default="1"),
            sa.Column("anchor", sa.String(128), nullable=False, server_default=""),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "project_id",
                "document_id",
                "identifier",
                name="uq_spec_requirements_document_identifier",
            ),
            sa.CheckConstraint(
                "state IN ('" + "', '".join(_STATES) + "')",
                name="ck_spec_requirements_state",
            ),
        )
        op.create_index(
            "ix_spec_requirements_document", "spec_requirements", ["document_id", "identifier"]
        )
        op.create_index(
            "ix_spec_requirements_project_state", "spec_requirements", ["project_id", "state"]
        )

    if "spec_requirement_revisions" not in present:
        op.create_table(
            "spec_requirement_revisions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column(
                "requirement_id",
                sa.String(64),
                sa.ForeignKey("spec_requirements.id"),
                nullable=False,
            ),
            sa.Column(
                "document_id", sa.String(64), sa.ForeignKey("spec_documents.id"), nullable=False
            ),
            sa.Column("previous_digest", sa.String(64), nullable=True),
            sa.Column("digest", sa.String(64), nullable=False),
            sa.Column("digest_version", sa.Integer, nullable=False, server_default="1"),
            sa.Column("source", sa.String(16), nullable=False),
            sa.Column("classification", sa.String(32), nullable=False),
            sa.Column("actor_kind", sa.String(16), nullable=False),
            sa.Column("actor", sa.String(128), nullable=False, server_default=""),
            sa.Column("run_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "source IN ('" + "', '".join(_SOURCES) + "')",
                name="ck_spec_requirement_revisions_source",
            ),
            sa.CheckConstraint(
                "classification IN ('" + "', '".join(_CLASSIFICATIONS) + "')",
                name="ck_spec_requirement_revisions_classification",
            ),
            sa.CheckConstraint(
                "actor_kind IN ('" + "', '".join(_ACTORS) + "')",
                name="ck_spec_requirement_revisions_actor_kind",
            ),
        )
        op.create_index(
            "ix_spec_requirement_revisions_requirement",
            "spec_requirement_revisions",
            ["requirement_id", "created_at"],
        )


def downgrade() -> None:
    present = _tables(op.get_bind())
    if "spec_requirement_revisions" in present:
        op.drop_index(
            "ix_spec_requirement_revisions_requirement", table_name="spec_requirement_revisions"
        )
        op.drop_table("spec_requirement_revisions")
    if "spec_requirements" in present:
        op.drop_index("ix_spec_requirements_project_state", table_name="spec_requirements")
        op.drop_index("ix_spec_requirements_document", table_name="spec_requirements")
        op.drop_table("spec_requirements")
