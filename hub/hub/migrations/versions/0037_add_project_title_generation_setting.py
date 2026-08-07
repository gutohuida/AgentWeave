"""add the project-level conversation title generation setting

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-07 23:57:00.000000

Defaults to `truncate`, so an existing project is opted out: generating a title spends the
operator's tokens, and nothing may start spending them because a migration ran.

No CHECK constraint on the mode. Adding one to `projects` means recreating a table that 22 foreign
keys point at, to guard two values that are validated where they are set — the same trade already
made for `permission_requests.status` and `unasked_questions.status`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

_TABLE = "projects"
_COLUMNS = ("conversation_title_mode", "conversation_title_runner_id")


def _columns(conn) -> set[str] | None:
    """Columns of `projects`, or None when the table is not there.

    Upgrades starting from an early revision reach this migration with only the tables those
    revisions created; `create_all` builds the rest from the model, these columns included.
    """
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None:
        return
    if "conversation_title_mode" not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                "conversation_title_mode",
                sa.String(16),
                nullable=False,
                server_default="truncate",
            ),
        )
    if "conversation_title_runner_id" not in existing:
        op.add_column(
            _TABLE, sa.Column("conversation_title_runner_id", sa.String(64), nullable=True)
        )


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None:
        return
    for name in reversed(_COLUMNS):
        if name in existing:
            op.drop_column(_TABLE, name)
