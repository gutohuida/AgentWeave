"""spell an unknown footprint branch one way

Revision ID: 0109
Revises: 0108
Create Date: 2026-09-26 04:00:00.000000

A detached checkout used to be footprinted with the branch `HEAD` (git's `--abbrev-ref` answer),
while a commit no branch could be named for was written `''`. `task_integration` groups by the
string, so the two were different lines of work. The Hub now writes `''` and never `HEAD`; this
rewrites the rows written before. Data only, idempotent, and a no-op when nothing holds `HEAD`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "evidence_footprints" not in sa.inspect(bind).get_table_names():
        return
    bind.execute(sa.text("UPDATE evidence_footprints SET branch = '' WHERE branch = 'HEAD'"))


def downgrade() -> None:
    # The rewritten rows cannot be told from rows that were always `''`.
    pass
