"""a conversation's provider session records which CLI made it -- conversations.provider_session_cli

Revision ID: 0148
Revises: 0147
Create Date: 2026-10-27 00:00:00.000000

`rebinding-an-agents-runner-starts-clean` (FR-9, F1023). A turn resumes the conversation's provider
session whatever CLI wrote it, so an agent rebound from Claude to Copilot and back handed Claude
Copilot's session id and failed the operator's turn twice. The launch needs to know whose session
it holds; this adds one nullable column beside `provider_session_id` that says so.

**It writes to every row of `conversations` that holds a session**, on the operator's real database
at their next restart. Back the database up first. The backfill reads only: for each conversation
holding a session, `turn_usage.runner` of its latest *completed* run whose `session_id` equals that
session, else NULL. NULL means "not known" and keeps today's behaviour (the session is resumed), so a
conversation the backfill cannot attribute is no worse off than before. Nothing else is changed.

The downgrade drops the column (a plain `DROP COLUMN`, SQLite 3.35+, as `0145`'s and `0147`'s do);
no other value is touched, and a reverted Hub never reads it.

Guarded for a database without the table (an upgrade from an early revision), without `runs` or
`turn_usage` (the backfill is then skipped), and for a column already present (a database built by
`create_all`, whose rows then hold NULL and are attributed by the same statement).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0148"
down_revision = "0147"
branch_labels = None
depends_on = None


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


# The latest completed run of the conversation that bound the session it holds, and the runner its
# accounting row recorded. `LEFT JOIN`, so a run with no accounting row (or a NULL runner) answers
# NULL rather than falling through to an older run of another CLI.
_BACKFILL = sa.text("""
    UPDATE conversations
    SET provider_session_cli = (
        SELECT usage.runner
        FROM runs
        LEFT JOIN turn_usage AS usage ON usage.run_id = runs.id
        WHERE runs.conversation_id = conversations.id
          AND runs.status = 'completed'
          AND runs.session_id = conversations.provider_session_id
        ORDER BY runs.started_at DESC, runs.id DESC
        LIMIT 1
    )
    WHERE provider_session_id IS NOT NULL
      AND provider_session_cli IS NULL
    """)


def upgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "conversations" not in tables:
        return
    if "provider_session_cli" not in _columns(conn, "conversations"):
        op.add_column(
            "conversations", sa.Column("provider_session_cli", sa.String(length=32), nullable=True)
        )
    if {"runs", "turn_usage"} <= tables:
        conn.execute(_BACKFILL)


def downgrade() -> None:
    conn = op.get_bind()
    if "conversations" in _tables(conn) and "provider_session_cli" in _columns(
        conn, "conversations"
    ):
        op.execute(sa.text("ALTER TABLE conversations DROP COLUMN provider_session_cli"))
