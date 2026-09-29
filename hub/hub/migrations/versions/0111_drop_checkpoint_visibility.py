"""the checkpoint grant says it reaches every checkpoint -- drop the unwritten visibility column

Revision ID: 0111
Revises: 0110
Create Date: 2026-09-29 01:00:00.000000

`the-checkpoint-grant-says-it-reaches-every-checkpoint` (F235). `checkpoints.visibility` has had
no writer since it shipped: every row reads `project` (`0097` rewrote every stored `private`), and
`may_read_checkpoint` no longer reads the column at all -- the operator's grant is the whole
answer. The operator's control said the grant was "bounded by each checkpoint's own visibility",
which nothing could ever set; the column is now removed rather than left as a documented dead
end, per design D3.

**A table rebuild, on SQLite** (`batch_alter_table(..., recreate="always")`, the same shape `0088`
uses): `ALTER TABLE ... DROP COLUMN` fails outright while `ck_checkpoints_visibility` still names
the column ("no such column: visibility"), so the check has to go in the same rebuild as the
column.

**Save and restore every partial index by hand, rather than trust reflection for it.** A rebuild
regenerates indexes from what the connection reflects, and whether that carries a partial index's
`WHERE` clause is a SQLAlchemy-version question this migration should not depend on
(`pyproject.toml` allows any `sqlalchemy>=2.0`). `checkpoints` carries one today --
`ix_checkpoints_one_handover_per_conversation` (`0106`) -- found generically by querying
`sqlite_master` for every index on the table whose SQL has a `WHERE`, not by that name, so this
migration does not need to know about `0106` or any partial index a later migration adds. Each is
dropped before the batch and its saved DDL re-executed after, only if an index of that name is not
already present (reflection may have recreated it under the same name; re-running the same DDL a
second time would fail with "index already exists").

Downgrade re-adds the column and restores `ck_checkpoints_visibility`, with server default
`'project'` -- deliberately not `0044`'s `'private'`. `0097` only ever rewrote row *values*; the
column's server default stayed `'private'` the whole time, and `'project'` was only ever the ORM
default (`db/models.py`, pre-removal). Every row downgrade restores reads `'project'` (that is what
every row in a live database holds), and a row written by raw SQL after a downgrade should be born
the same way every row the model ever wrote was: readable.

Guarded for a missing table (an upgrade starting from an early revision reaches this with only
that revision's tables) and for the column already being gone (a database whose `checkpoints`
table `create_all` built from the model *after* this migration lands has never had the column --
this is the state the F329 parity test's reference build reaches, so that test does not exercise
this migration's rebuild at all; `test_migrations.py` covers the rebuild directly).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None

_TABLE = "checkpoints"
_COLUMN = "visibility"
_CHECK = "ck_checkpoints_visibility"


def _columns(conn) -> set[str] | None:
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def _partial_indexes(conn) -> list[tuple[str, str]]:
    """Every partial index on `checkpoints`, as `(name, create_sql)`, found generically rather
    than by name -- this migration does not need to know what any other migration named its
    index."""
    rows = conn.execute(
        sa.text(
            "SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = :table "
            "AND sql IS NOT NULL AND sql LIKE '%WHERE%'"
        ),
        {"table": _TABLE},
    ).fetchall()
    return [(row[0], row[1]) for row in rows]


def _existing_index_names(conn) -> set[str]:
    return {idx["name"] for idx in sa.inspect(conn).get_indexes(_TABLE) if idx["name"]}


def upgrade() -> None:
    conn = op.get_bind()
    existing = _columns(conn)
    if existing is None or _COLUMN not in existing:
        return

    saved = _partial_indexes(conn)
    for name, _ in saved:
        op.drop_index(name, table_name=_TABLE)

    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.drop_constraint(_CHECK, type_="check")
        batch_op.drop_column(_COLUMN)

    present = _existing_index_names(conn)
    for name, create_sql in saved:
        if name not in present:
            conn.execute(sa.text(create_sql))


def downgrade() -> None:
    conn = op.get_bind()
    existing = _columns(conn)
    if existing is None or _COLUMN in existing:
        return

    saved = _partial_indexes(conn)
    for name, _ in saved:
        op.drop_index(name, table_name=_TABLE)

    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(_COLUMN, sa.String(16), nullable=False, server_default="project")
        )
        batch_op.create_check_constraint(_CHECK, "visibility IN ('private', 'project', 'granted')")

    present = _existing_index_names(conn)
    for name, create_sql in saved:
        if name not in present:
            conn.execute(sa.text(create_sql))
