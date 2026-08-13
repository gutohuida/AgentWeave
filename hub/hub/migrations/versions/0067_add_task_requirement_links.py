"""add task_requirement_links and task_requirement_references

Revision ID: 0067
Revises: 0066
Create Date: 2026-08-13 21:30:00.000000

Links replace the JSON. `Task.requirements` stays exactly where it is, nullable and now read by
nothing that answers a traceability question, so a mis-parse below can be re-derived from the
original rather than reconstructed from a backup. Dropping it belongs to a later change, once the
unresolved set is empty.

The backfill here converts what it can and preserves the rest verbatim. It resolves against
`spec_requirements`, which is populated when a document is saved or a project is reindexed — so a
project whose documents predate the index converts nothing at this point and everything lands as an
unresolved reference. That is the honest outcome rather than a lossy one: reindexing the project and
running `requirement_links.backfill_project` afterwards converts the references that then resolve,
and never has to guess.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None

_ACTORS = ("operator", "agent", "system")

# The observed legacy shape is `"FR-8 — initialize-members"`: an identifier and a key, em-dash
# separated. That is a convention one agent happened to follow, not a guarantee, so only a leading
# identifier is trusted and anything else is kept whole.
_LEADING_IDENTIFIER = re.compile(r"^\s*(FR-\d+)\b")


def _tables(conn) -> set[str]:
    """An upgrade starting from an early revision reaches this migration with only the tables
    those revisions created; `create_all` builds the rest from the model."""
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "task_requirement_links" not in present:
        op.create_table(
            "task_requirement_links",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=False),
            sa.Column(
                "requirement_id",
                sa.String(64),
                sa.ForeignKey("spec_requirements.id"),
                nullable=False,
            ),
            sa.Column("actor_kind", sa.String(16), nullable=False, server_default="system"),
            sa.Column("actor", sa.String(128), nullable=False, server_default=""),
            sa.Column("run_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("task_id", "requirement_id", name="uq_task_requirement_links_pair"),
            sa.CheckConstraint(
                "actor_kind IN ('" + "', '".join(_ACTORS) + "')",
                name="ck_task_requirement_links_actor_kind",
            ),
        )
        op.create_index(
            "ix_task_requirement_links_requirement", "task_requirement_links", ["requirement_id"]
        )
        op.create_index("ix_task_requirement_links_task", "task_requirement_links", ["task_id"])

    if "task_requirement_references" not in present:
        op.create_table(
            "task_requirement_references",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=False),
            sa.Column("reference", sa.Text, nullable=False),
            sa.Column("reason", sa.String(32), nullable=False, server_default="unknown"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_task_requirement_references_task", "task_requirement_references", ["task_id"]
        )

    _backfill(conn, _tables(conn))


def _backfill(conn, present: set[str]) -> None:
    """Convert every legacy value, or keep it. Never drop one, never invent a requirement."""
    if "tasks" not in present:
        return

    import json
    import uuid

    now = datetime.now(timezone.utc)

    indexed: dict[tuple[str, str], list[str]] = {}
    if "spec_requirements" in present:
        for project_id, identifier, requirement_id in conn.execute(
            sa.text("SELECT project_id, identifier, id FROM spec_requirements")
        ):
            indexed.setdefault((project_id, identifier), []).append(requirement_id)

    linked: list[dict] = []
    unresolved: list[dict] = []

    for task_id, project_id, raw in conn.execute(
        sa.text("SELECT id, project_id, requirements FROM tasks WHERE requirements IS NOT NULL")
    ):
        values = raw
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except (TypeError, ValueError):
                values = [values]
        if not isinstance(values, list):
            values = [values]

        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str) or not value.strip():
                continue
            match = _LEADING_IDENTIFIER.match(value)
            candidates = indexed.get((project_id, match.group(1)), []) if match else []

            if len(candidates) == 1:
                requirement_id = candidates[0]
                if requirement_id in seen:
                    continue
                seen.add(requirement_id)
                linked.append(
                    {
                        "id": f"trl-{uuid.uuid4().hex[:8]}",
                        "project_id": project_id,
                        "task_id": task_id,
                        "requirement_id": requirement_id,
                        "actor_kind": "system",
                        "actor": "migration",
                        "run_id": None,
                        "created_at": now,
                    }
                )
                continue

            unresolved.append(
                {
                    "id": f"trr-{uuid.uuid4().hex[:8]}",
                    "project_id": project_id,
                    "task_id": task_id,
                    "reference": value,
                    "reason": "ambiguous" if len(candidates) > 1 else "unknown",
                    "created_at": now,
                }
            )

    if linked:
        conn.execute(
            sa.text(
                "INSERT INTO task_requirement_links "
                "(id, project_id, task_id, requirement_id, actor_kind, actor, run_id, created_at) "
                "VALUES (:id, :project_id, :task_id, :requirement_id, :actor_kind, :actor, "
                ":run_id, :created_at)"
            ),
            linked,
        )
    if unresolved:
        conn.execute(
            sa.text(
                "INSERT INTO task_requirement_references "
                "(id, project_id, task_id, reference, reason, created_at) "
                "VALUES (:id, :project_id, :task_id, :reference, :reason, :created_at)"
            ),
            unresolved,
        )


def downgrade() -> None:
    present = _tables(op.get_bind())
    if "task_requirement_references" in present:
        op.drop_index(
            "ix_task_requirement_references_task", table_name="task_requirement_references"
        )
        op.drop_table("task_requirement_references")
    if "task_requirement_links" in present:
        op.drop_index("ix_task_requirement_links_task", table_name="task_requirement_links")
        op.drop_index("ix_task_requirement_links_requirement", table_name="task_requirement_links")
        op.drop_table("task_requirement_links")
