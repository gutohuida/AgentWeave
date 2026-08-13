"""add document rigor, its history, and the policy digest on a transition

Revision ID: 0069
Revises: 0068
Create Date: 2026-08-13 23:30:00.000000

Rigor is what happens to work that ignores a document — not whether the operator agreed to it, which
is `phase`. Every existing document becomes a `sketch`, which blocks nothing: a change that made
approved documents start refusing approvals would be a barrier nobody asked for, arriving as an
upgrade.

`task_transitions.policy_digest` records what governed each move. Rigor being operator-editable is
precisely what makes that necessary rather than theoretical: without it, a gate that passed last
month cannot be explained today. Existing rows stay null — no policy is a fact about them, and a
synthetic digest would be a claim nothing observed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None

_ACTORS = ("operator", "agent", "system")


def _tables(conn) -> set[str]:
    """An upgrade starting from an early revision reaches this migration with only the tables
    those revisions created; `create_all` builds the rest from the model."""
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "spec_documents" in present and "rigor" not in _columns(conn, "spec_documents"):
        op.add_column(
            "spec_documents",
            sa.Column("rigor", sa.String(16), nullable=False, server_default="sketch"),
        )

    if "task_transitions" in present and "policy_digest" not in _columns(conn, "task_transitions"):
        op.add_column("task_transitions", sa.Column("policy_digest", sa.String(64), nullable=True))

    if "spec_rigor_events" not in present:
        op.create_table(
            "spec_rigor_events",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column(
                "document_id", sa.String(64), sa.ForeignKey("spec_documents.id"), nullable=False
            ),
            sa.Column("from_rigor", sa.String(16), nullable=False),
            sa.Column("to_rigor", sa.String(16), nullable=False),
            sa.Column("actor_kind", sa.String(16), nullable=False),
            sa.Column("actor", sa.String(128), nullable=False, server_default=""),
            sa.Column("reason", sa.Text, nullable=False, server_default=""),
            sa.Column("digest", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "actor_kind IN ('" + "', '".join(_ACTORS) + "')",
                name="ck_spec_rigor_events_actor_kind",
            ),
        )
        op.create_index(
            "ix_spec_rigor_events_document", "spec_rigor_events", ["document_id", "created_at"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)
    if "spec_rigor_events" in present:
        op.drop_index("ix_spec_rigor_events_document", table_name="spec_rigor_events")
        op.drop_table("spec_rigor_events")
    if "task_transitions" in present and "policy_digest" in _columns(conn, "task_transitions"):
        op.drop_column("task_transitions", "policy_digest")
    if "spec_documents" in present and "rigor" in _columns(conn, "spec_documents"):
        op.drop_column("spec_documents", "rigor")
