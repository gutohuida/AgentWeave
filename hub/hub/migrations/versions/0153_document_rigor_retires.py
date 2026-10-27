"""document rigor retires -- open contract/gate tasks keep their rule as a level; pending edit
proposals are marked stale

Revision ID: 0153
Revises: 0152
Create Date: 2026-10-27 00:00:00.000000

`amendments-main-watch-and-the-next-slice` (slice D2, Tier 2), task `rigor-retires`. Nothing sets
or reads a document's rigor any more: approval's evidence rule is the task's level, and a task with
none is judged by `sketch`'s rule. So that a stricter document's open work does not loosen silently
on another install, each open task (not approved or rejected) of a `contract` or `gate` document
outside any build records the level that rule implies: `reviewed` or `gated`. Each pending edit
proposal is marked `stale`, with a reason naming the retirement: nothing will ever list or accept it.

The `rigor` column, `spec_rigor_events` and `spec_edit_proposals` stay, unread (dropping a column is
an SQLite table rebuild for no behaviour). On the operator's database (read-only, 2026-10-27) every
document is `sketch` and there are no edit proposals, so this changes no row there.

Downgrade puts back exactly what this wrote: the levels of tasks outside any build return to null
(no other writer records a level outside a build) and the proposals stale for this reason return to
pending.

Guarded for a database without the tables or columns (an upgrade from an early revision).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0153"
down_revision = "0152"
branch_labels = None
depends_on = None

RETIRED_REASON = (
    "document rigor retired (amendments-main-watch-and-the-next-slice): an edit before approval "
    "applies directly, and after approval it is an amendment"
)
_LEVELS = {"contract": "reviewed", "gate": "gated"}


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _ready(conn) -> bool:
    tables = _tables(conn)
    return (
        {"tasks", "spec_documents"} <= tables
        and {"build_id", "level", "spec_document_id"} <= _columns(conn, "tasks")
        and "rigor" in _columns(conn, "spec_documents")
    )


def upgrade() -> None:
    conn = op.get_bind()
    if _ready(conn):
        for rigor, level in _LEVELS.items():
            conn.execute(
                sa.text(
                    "UPDATE tasks SET level = :level WHERE build_id IS NULL AND level IS NULL "
                    "AND status NOT IN ('approved', 'rejected') AND spec_document_id IN "
                    "(SELECT id FROM spec_documents WHERE rigor = :rigor)"
                ),
                {"level": level, "rigor": rigor},
            )
    if "spec_edit_proposals" in _tables(conn):
        conn.execute(
            sa.text(
                "UPDATE spec_edit_proposals SET status = 'stale', resolution_reason = :reason, "
                "resolved_at = CURRENT_TIMESTAMP WHERE status = 'pending'"
            ),
            {"reason": RETIRED_REASON},
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _ready(conn):
        conn.execute(
            sa.text(
                "UPDATE tasks SET level = NULL WHERE build_id IS NULL AND level IN "
                "('reviewed', 'gated')"
            )
        )
    if "spec_edit_proposals" in _tables(conn):
        conn.execute(
            sa.text(
                "UPDATE spec_edit_proposals SET status = 'pending', resolution_reason = '', "
                "resolved_at = NULL WHERE status = 'stale' AND resolution_reason = :reason"
            ),
            {"reason": RETIRED_REASON},
        )
