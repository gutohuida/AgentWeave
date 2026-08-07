"""add conversation title and origin

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-07 23:55:00.000000

`title` is nullable: an existing conversation was never named, and nothing here invents a name
for it — the title is set when a first message is recorded, and a surface listing a titleless
conversation labels it as new rather than by its identifier.

`origin` is NOT NULL defaulting to `operator`. That is true of every conversation an operator has
actually used and unknowable for the rest, which is the honest floor; the alternative — a nullable
column — would leave the tree unable to state provenance for any row predating this migration.

The table is recreated because SQLite cannot add a CHECK constraint to an existing table, the same
approach `0019` takes for the inbound-queue origin constraints — including its guard on `projects`.
Recreating reflects `conversations`, and reflecting it resolves its foreign key, so an upgrade
running without `projects` (alembic alone, no `create_all`) would raise `NoSuchTableError`. Such a
database gets these columns from the model when `create_all` builds the rest.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

_TABLE = "conversations"
_COLUMNS = ("title", "title_set_by_operator", "origin")
_ORIGIN_CHECK = "origin IN ('operator', 'peer', 'handoff', 'spec', 'job')"


def _columns(conn) -> set[str] | None:
    """Columns of `conversations`, or None when it or its foreign key target is not there.

    Upgrades starting from an early revision reach this migration with only the tables those
    revisions created; `create_all` builds the rest from the model, these columns included.
    """
    inspector = sa.inspect(conn)
    if not {_TABLE, "projects"} <= set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None:
        return
    if all(name in existing for name in _COLUMNS):
        return
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        if "title" not in existing:
            batch_op.add_column(sa.Column("title", sa.String(120), nullable=True))
        if "title_set_by_operator" not in existing:
            batch_op.add_column(
                sa.Column(
                    "title_set_by_operator",
                    sa.Boolean(),
                    nullable=False,
                    server_default="0",
                )
            )
        if "origin" not in existing:
            batch_op.add_column(
                sa.Column("origin", sa.String(16), nullable=False, server_default="operator")
            )
            batch_op.create_check_constraint("ck_conversations_origin", _ORIGIN_CHECK)


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None:
        return
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        if "origin" in existing:
            batch_op.drop_constraint("ck_conversations_origin", type_="check")
            batch_op.drop_column("origin")
        if "title_set_by_operator" in existing:
            batch_op.drop_column("title_set_by_operator")
        if "title" in existing:
            batch_op.drop_column("title")
