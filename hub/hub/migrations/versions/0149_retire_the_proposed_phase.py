"""retire the proposed phase, and name the last exploring step `build`

Revision ID: 0149
Revises: 0148
Create Date: 2026-10-27 12:00:00.000000

`exploring-ends-at-an-approved-plan` (Tier 2: it rewrites live rows). Check reports a document's
readiness without moving it and approval goes straight from `exploring`, so no document can be in
`proposed` any more (FR-2). Every document in it is moved back to `exploring`, its exploration
reopened as a reopen does (`explore_closed_at` cleared), and an event records the move and why,
attributed to the system. The phase CHECK is then narrowed so the database refuses the phase too.

The last exploring step was `delivery`; it now recommends a build and is called `build`
(FR-10). Documents standing at it move with it. A project's `spec/journey.json` that still names
`delivery` is read as `build` (`spec_journey.parse`), so no file needs rewriting.

Rollback: the downgrade widens the CHECK to admit `proposed` again and moves `build` back to
`delivery`. The documents this moved stay in `exploring`, where proposing them again is one click
on the code that still has the button; their events stay, as history does.

SQLite cannot alter a CHECK in place, so the table is recreated, as `0074` and `0121` do; guarded for
a database without `spec_documents` or `projects` (an upgrade from an early revision).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0149"
down_revision = "0148"
branch_labels = None
depends_on = None

#: The phases a row may hold from here on; mirrors `db.models.SPEC_PHASES` (a test holds them equal).
_PHASES = ("exploring", "approved", "archived", "current")
_PHASES_BEFORE = ("exploring", "proposed", "approved", "archived", "current")
_REASON = (
    "the proposed phase was retired: Check reports a document's readiness without moving it, and "
    "Approve approves it from exploring"
)

_events = sa.table(
    "spec_document_events",
    sa.column("id", sa.String),
    sa.column("document_id", sa.String),
    sa.column("project_id", sa.String),
    sa.column("kind", sa.String),
    sa.column("actor_kind", sa.String),
    sa.column("actor", sa.String),
    sa.column("origin", sa.String),
    sa.column("run_id", sa.String),
    sa.column("detail", sa.JSON),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def _phase_check(phases) -> None:
    with op.batch_alter_table("spec_documents", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_spec_documents_phase", type_="check")
        batch_op.create_check_constraint(
            "ck_spec_documents_phase", "phase IN ('" + "', '".join(phases) + "')"
        )


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)
    if not {"spec_documents", "projects"} <= present:
        return
    moved = conn.execute(
        sa.text("SELECT id, project_id FROM spec_documents WHERE phase = 'proposed'")
    ).fetchall()
    if moved:
        conn.execute(
            sa.text(
                "UPDATE spec_documents SET phase = 'exploring', explore_closed_at = NULL "
                "WHERE phase = 'proposed'"
            )
        )
        if "spec_document_events" in present:
            now = datetime.now(timezone.utc)
            conn.execute(
                _events.insert(),
                [
                    {
                        "id": f"spev-{uuid.uuid4().hex[:12]}",
                        "document_id": document_id,
                        "project_id": project_id,
                        "kind": "phase",
                        "actor_kind": "system",
                        "actor": "migration 0149",
                        "origin": "lifecycle",
                        "run_id": None,
                        "detail": {"from": "proposed", "to": "exploring", "reason": _REASON},
                        "created_at": now,
                    }
                    for document_id, project_id in moved
                ],
            )
    conn.execute(sa.text("UPDATE spec_documents SET step = 'build' WHERE step = 'delivery'"))
    _phase_check(_PHASES)


def downgrade() -> None:
    conn = op.get_bind()
    if not {"spec_documents", "projects"} <= _tables(conn):
        return
    _phase_check(_PHASES_BEFORE)
    conn.execute(sa.text("UPDATE spec_documents SET step = 'delivery' WHERE step = 'build'"))
