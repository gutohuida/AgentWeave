"""add checkpoint notes

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-08 23:55:00.000000

What an agent knew that never reached the transcript: intent in flight, unverified suspicions,
warnings for a successor. Hub-side generation cannot recover any of it from the record, because
none of it was ever in the record.

A table rather than a column on `conversations`, so that "the agent had nothing to add" and "the
agent was never asked, or never answered" are distinguishable. That distinction is the whole
reason notes are collected through a tool call instead of parsed out of prose.

Guarded, like 0038-0044.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

_TABLE = "checkpoint_notes"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    tables = _tables(op.get_bind())
    if _TABLE in tables or "projects" not in tables:
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("agent", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("suspicions", sa.JSON(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=True),
        sa.Column("consumed_by_checkpoint_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_checkpoint_notes_conversation_id", _TABLE, ["conversation_id"])
    op.create_index(
        "ix_checkpoint_notes_conversation_created", _TABLE, ["conversation_id", "created_at"]
    )


def downgrade() -> None:
    if _TABLE not in _tables(op.get_bind()):
        return
    op.drop_index("ix_checkpoint_notes_conversation_created", table_name=_TABLE)
    op.drop_index("ix_checkpoint_notes_conversation_id", table_name=_TABLE)
    op.drop_table(_TABLE)
