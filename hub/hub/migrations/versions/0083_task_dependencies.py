"""add task_dependencies and spec_documents.first_approved_at

Revision ID: 0083
Revises: 0082
Create Date: 2026-08-21 07:00:00.000000

Two independent additions landed together because both are `task-dependencies` design D3/D6:

`task_dependencies` is a join table (`task_id`, `depends_on_task_id`), the precedent being
`task_requirement_links` (`0067`) rather than a JSON column — the gate reads one direction, the
board reads both, and neither is answerable from a JSON array.

`spec_documents.first_approved_at` is a nullable timestamp, backfilled here from the `kind="phase"`
event history (`detail` carries `{"from", "to"}`): the earliest event whose `detail["to"] ==
"approved"` for each document, following `0067`'s own approach of parsing a JSON column's raw text
in Python rather than relying on `json_extract` (no existing migration uses it, and the value may
already be a dict depending on driver). A document with no such event in its history was never
approved and is correctly left NULL, not backfilled to anything.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def _tables(conn) -> set[str]:
    """An upgrade starting from an early revision reaches this migration with only the tables
    those revisions created; `create_all` builds the rest from the model."""
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "task_dependencies" not in present and "tasks" in present and "projects" in present:
        op.create_table(
            "task_dependencies",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column(
                "task_id",
                sa.String(64),
                sa.ForeignKey("tasks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "depends_on_task_id",
                sa.String(64),
                sa.ForeignKey("tasks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependencies_pair"),
        )
        op.create_index("ix_task_dependencies_task", "task_dependencies", ["task_id"])
        op.create_index(
            "ix_task_dependencies_depends_on", "task_dependencies", ["depends_on_task_id"]
        )

    if "spec_documents" in present:
        if "first_approved_at" not in _columns(conn, "spec_documents"):
            op.add_column(
                "spec_documents",
                sa.Column("first_approved_at", sa.DateTime(timezone=True), nullable=True),
            )
        # Unconditional, like `0067`'s own backfill: it only ever fills a NULL
        # (see the `WHERE first_approved_at IS NULL` in the UPDATE below), so running it again
        # against a column that already exists is a no-op, not a second write.
        _backfill_first_approved_at(conn)


def _backfill_first_approved_at(conn) -> None:
    """The earliest `phase` event moving a document `to: "approved"`, per document."""
    if "spec_document_events" not in _tables(conn):
        return

    earliest: dict[str, datetime] = {}
    for document_id, detail, created_at in conn.execute(
        sa.text(
            "SELECT document_id, detail, created_at FROM spec_document_events "
            "WHERE kind = 'phase' ORDER BY document_id, created_at"
        )
    ):
        value = detail
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                continue
        if not isinstance(value, dict) or value.get("to") != "approved":
            continue
        if document_id in earliest:
            continue
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        earliest[document_id] = created_at

    for document_id, when in earliest.items():
        conn.execute(
            sa.text(
                "UPDATE spec_documents SET first_approved_at = :when "
                "WHERE id = :id AND first_approved_at IS NULL"
            ),
            {"when": when, "id": document_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "spec_documents" in present and "first_approved_at" in _columns(conn, "spec_documents"):
        op.drop_column("spec_documents", "first_approved_at")

    if "task_dependencies" in present:
        op.drop_index("ix_task_dependencies_depends_on", table_name="task_dependencies")
        op.drop_index("ix_task_dependencies_task", table_name="task_dependencies")
        op.drop_table("task_dependencies")
