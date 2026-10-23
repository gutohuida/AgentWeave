"""stalls, and the mender's queue and conversation origin

Revision ID: 0141
Revises: 0140
Create Date: 2026-10-23 12:00:00.000000

`a-stalled-project-wakes-a-doctor-that-unblocks-it` (Tier 2). Three moves:

1. A new `stalls` table: one row per time a project's work stopped moving, keyed by cause and
   subject. Nothing existing is read or backfilled; a stall from before this revision is simply
   unrecorded.
2. `mender` joins `ck_inbound_queue_origin_type` and `ck_inbound_queue_origin_agent`: the Hub
   briefing the mender on a stall it recorded. Its own value, for the reason `0058` and `0108` give:
   no operator asked for it and no agent sent it.
3. `mender` joins `ck_conversations_origin`, for `0093`'s reason: the mender's thread is one the
   Hub opened, and a conversation belongs to one agent.

Both constraint moves recreate their table with `batch_alter_table`, because SQLite cannot alter a
CHECK constraint in place -- the approach `0093` and `0108` take, including their guards. Rollback:
the downgrade rewrites `mender` rows to `job` (the surviving value that also means "the Hub opened
this") in both tables, restores the constraints and drops `stalls`, losing only the stall record.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0141"
down_revision = "0140"
branch_labels = None
depends_on = None

_QUEUE_ORIGINS = ("operator", "agent", "job", "checkpoint", "divergence", "evidence")
_CONVERSATION_ORIGINS = ("operator", "peer", "handoff", "spec", "job", "divergence")


def _quoted(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _replace_queue_constraints(*, include_mender: bool) -> None:
    origins = _QUEUE_ORIGINS + (("mender",) if include_mender else ())
    origin_agent = " OR ".join(
        (
            f"(origin_type = '{origin}' AND origin_agent IS NOT NULL)"
            if origin == "agent"
            else f"(origin_type = '{origin}' AND origin_agent IS NULL)"
        )
        for origin in origins
    )
    with op.batch_alter_table("inbound_queue_entries", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_inbound_queue_origin_type", type_="check")
        batch_op.drop_constraint("ck_inbound_queue_origin_agent", type_="check")
        batch_op.create_check_constraint(
            "ck_inbound_queue_origin_type", f"origin_type IN ({_quoted(origins)})"
        )
        batch_op.create_check_constraint("ck_inbound_queue_origin_agent", origin_agent)


def _replace_conversation_constraint(*, include_mender: bool) -> None:
    origins = _CONVERSATION_ORIGINS + (("mender",) if include_mender else ())
    with op.batch_alter_table("conversations", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_conversations_origin", type_="check")
        batch_op.create_check_constraint(
            "ck_conversations_origin", f"origin IN ({_quoted(origins)})"
        )


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "projects" not in tables:
        return
    if "stalls" not in tables:
        op.create_table(
            "stalls",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("key", sa.String(255), nullable=False),
            sa.Column("cause", sa.String(32), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("task_id", sa.String(64), nullable=True),
            sa.Column("loop_id", sa.String(64), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("seen_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("conversation_id", sa.String(64), nullable=True),
            sa.Column("mender_turns", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("outcome", sa.String(16), nullable=False, server_default="open"),
            sa.Column("outcome_detail", sa.Text(), nullable=False, server_default=""),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "cause IN ('loop_stalled', 'delivery_refused', 'integration_skipped', "
                "'integration_failed', 'review_unstaffed', 'dead_run', 'stuck_task', "
                "'no_progress')",
                name="ck_stalls_cause",
            ),
            sa.CheckConstraint(
                "outcome IN ('open', 'fixed', 'gave_up', 'resolved')", name="ck_stalls_outcome"
            ),
        )
        op.create_index("ix_stalls_project_seen", "stalls", ["project_id", "last_seen_at"])
        op.create_index(
            "ix_stalls_open_key",
            "stalls",
            ["project_id", "key"],
            unique=True,
            sqlite_where=sa.text("ended_at IS NULL"),
        )
    if "inbound_queue_entries" in tables:
        _replace_queue_constraints(include_mender=True)
    if "conversations" in tables:
        _replace_conversation_constraint(include_mender=True)


def downgrade() -> None:
    tables = _tables()
    if "projects" not in tables:
        return
    conn = op.get_bind()
    if "inbound_queue_entries" in tables:
        conn.execute(
            sa.text(
                "UPDATE inbound_queue_entries SET origin_type = 'job' WHERE origin_type = 'mender'"
            )
        )
        _replace_queue_constraints(include_mender=False)
    if "conversations" in tables:
        conn.execute(sa.text("UPDATE conversations SET origin = 'job' WHERE origin = 'mender'"))
        _replace_conversation_constraint(include_mender=False)
    if "stalls" in tables:
        op.drop_index("ix_stalls_open_key", table_name="stalls")
        op.drop_index("ix_stalls_project_seen", table_name="stalls")
        op.drop_table("stalls")
