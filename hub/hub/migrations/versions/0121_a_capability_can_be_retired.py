"""a capability can be archived -- relax ck_spec_documents_kind_phase

Revision ID: 0121
Revises: 0120
Create Date: 2026-10-08 00:00:00.000000

`a-capability-can-be-retired` (F536, Tier 2). `0074` tied `kind = 'capability'` to
`phase = 'current'` in both directions, so a capability that no longer describes the product could
never leave the corpus. This lets a capability also be `archived` (retired); every other rule stays:
only a capability is ever `current`. No row changes value on the way up.

Downgrade puts every archived capability back to `current` before restoring the narrow CHECK -- the
retirement is lost, the document becomes an ordinary current capability again -- for the same reason
`0074`'s downgrade parks rows before narrowing: a batch recreate applies the new CHECK to the copied
rows. Table recreation, because SQLite cannot alter a CHECK in place; guarded for a missing table,
as `0074` is.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0121"
down_revision = "0120"
branch_labels = None
depends_on = None

_WIDE = (
    "(kind = 'capability' AND phase IN ('current', 'archived')) OR "
    "(kind != 'capability' AND phase != 'current')"
)
_NARROW = (
    "(kind = 'capability' AND phase = 'current') OR "
    "(kind != 'capability' AND phase != 'current')"
)


def _present(conn) -> bool:
    return {"spec_documents", "projects"} <= set(sa.inspect(conn).get_table_names())


def _replace(check: str) -> None:
    with op.batch_alter_table("spec_documents", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_spec_documents_kind_phase", type_="check")
        batch_op.create_check_constraint("ck_spec_documents_kind_phase", check)


def upgrade() -> None:
    if _present(op.get_bind()):
        _replace(_WIDE)


def downgrade() -> None:
    conn = op.get_bind()
    if _present(conn):
        conn.execute(
            sa.text(
                "UPDATE spec_documents SET phase = 'current' "
                "WHERE kind = 'capability' AND phase = 'archived'"
            )
        )
        _replace(_NARROW)
