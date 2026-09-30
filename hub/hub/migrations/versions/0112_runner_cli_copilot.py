"""a Copilot agent runs over ACP -- admit `copilot` as a runner CLI

Revision ID: 0112
Revises: 0111
Create Date: 2026-09-30 11:00:00.000000

`a-copilot-agent-runs-over-acp`, design D1. `RUNNER_CLIS` gains `copilot`, and `runners.cli`
carries `ck_runners_cli`, created by `0023` as `cli IN ('claude', 'codex')`. SQLite cannot alter a
CHECK constraint in place, so the table is recreated with `batch_alter_table(recreate="always")`,
the approach `0019`, `0035` and `0058` take.

Upgrade only widens the constraint: no row changes. Downgrade restores the two-value constraint
and **refuses** while a `copilot` runner exists, rather than deleting it -- a runner is referenced
by agents (`agents.runner_id`), and deleting one on a downgrade would silently unbind them.

Guarded for a missing `runners` (an upgrade starting from an early revision reaches this with
only that revision's tables) and for a missing `projects`, whose foreign-key reflection a rebuild
needs (`0058`'s guard).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0112"
down_revision = "0111"
branch_labels = None
depends_on = None

_TABLE = "runners"
_CHECK = "ck_runners_cli"


def _present(conn) -> bool:
    return {_TABLE, "projects"} <= set(sa.inspect(conn).get_table_names())


def _replace_check(clis: tuple[str, ...]) -> None:
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.drop_constraint(_CHECK, type_="check")
        batch_op.create_check_constraint(
            _CHECK, "cli IN (" + ", ".join(f"'{cli}'" for cli in clis) + ")"
        )


def upgrade() -> None:
    if not _present(op.get_bind()):
        return
    _replace_check(("claude", "codex", "copilot"))


def downgrade() -> None:
    conn = op.get_bind()
    if not _present(conn):
        return
    count = conn.execute(sa.text("SELECT COUNT(*) FROM runners WHERE cli = 'copilot'")).scalar()
    if count:
        raise RuntimeError(
            f"Cannot downgrade below 0112: {count} runner(s) use the copilot CLI. Delete or "
            "rebind them first; this downgrade does not delete runners."
        )
    _replace_check(("claude", "codex"))
