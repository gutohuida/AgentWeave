"""an Ask me card says what Workspace only would decide -- permission_requests.workspace_verdict

Revision ID: 0114
Revises: 0113
Create Date: 2026-09-30 17:00:00.000000

`an-ask-me-card-says-what-workspace-only-would-decide`, design D3. Under "Ask me" the operator is
asked about every call, and the card they answer now carries what "Workspace only" would have
decided for it, as advice: `{"allow": bool, "reason": str}`, or null when no verdict was worked
out (an older approver, or a request the Hub opens itself). One nullable JSON column; nothing is
backfilled, since a request already answered has no card left to show it on.

Guarded for a missing `permission_requests` (an upgrade starting from an early revision reaches
this with only that revision's tables), as `0033`/`0034` do.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0114"
down_revision = "0113"
branch_labels = None
depends_on = None

_TABLE = "permission_requests"
_COLUMN = "workspace_verdict"


def _columns(conn) -> set[str] | None:
    inspector = sa.inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return None
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    columns = _columns(op.get_bind())
    if columns is None or _COLUMN in columns:
        return
    with op.batch_alter_table(_TABLE, recreate="never") as batch_op:
        batch_op.add_column(sa.Column(_COLUMN, sa.JSON, nullable=True))


def downgrade() -> None:
    columns = _columns(op.get_bind())
    if columns is None or _COLUMN not in columns:
        return
    with op.batch_alter_table(_TABLE, recreate="never") as batch_op:
        batch_op.drop_column(_COLUMN)
