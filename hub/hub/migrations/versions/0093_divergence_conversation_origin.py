"""let a conversation say it was opened to answer a divergence

Revision ID: 0093
Revises: 0092
Create Date: 2026-08-26 19:20:00.000000

Finding F67. A divergence response was queued with **no conversation at all**, and
`turn_scheduler.schedule_agent` refuses exactly that shape — *"queued entry has no conversation"* —
so the entry sat `queued` forever. Measured on the beta database before the fix: 25 divergence rows,
**zero** carrying a `response_run_id`. No divergence response has ever produced a run.

It stayed hidden because `_queue_response` is reached only on `retried` and `escalated`. `escalate`
requires `task.escalation_agent`, NULL on every task ever recorded; no task carried `retry`. All 24
historical divergences are `surfaced`, which queues nothing. `one-answer-to-what-is-happening`
group 2 added `restaffed`, which reaches the path on an ordinary `surface` task, and walked
straight into it on the first live drive.

A response to a *different* agent — `escalate`, and now `restaffed` — cannot reuse the diverged
run's thread, because a conversation belongs to one agent and `schedule_agent` checks
`conversation.agent != agent`. So it needs its own, and this widens `ck_conversations_origin` to
let it say what it is.

`divergence` rather than borrowing `job` or `operator`, for exactly the reason migration `0058`
gives for the queue entry's own `origin_type`: *"a signal that reports something other than what it
names is the exact defect this whole capability exists to remove. Reusing `operator` would put the
operator's name on work they did not ask for."* Nobody asked for this thread; the Hub opened it
because a run ended holding work nobody moved.

Table recreation with `batch_alter_table`, because SQLite cannot alter a CHECK constraint in place —
the same approach `0058` and `0092` take, including the guard on `projects`, whose foreign key
reflection would otherwise raise on a database alembic reaches without `create_all`.

The downgrade rewrites `divergence` to `job`: of the five surviving origins it is the only one that
also means "the Hub opened this, not a person", so the row keeps the truer half of its meaning
rather than being deleted.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None

_TABLE = "conversations"


def _replace_constraint(*, include_divergence: bool) -> None:
    origins = "'operator', 'peer', 'handoff', 'spec', 'job'"
    if include_divergence:
        origins += ", 'divergence'"
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.drop_constraint("ck_conversations_origin", type_="check")
        batch_op.create_check_constraint("ck_conversations_origin", f"origin IN ({origins})")


def _present(conn) -> bool:
    """Whether this migration has a table to act on.

    Upgrades starting from an early revision reach here with only that revision's tables, and
    `create_all` builds the rest from the model with the widened constraint already in place.
    `projects` is named because `conversations.project_id` is a foreign key into it, and batch
    mode's `recreate="always"` reflects that target to preserve the relationship.
    """
    tables = set(sa.inspect(conn).get_table_names())
    return {_TABLE, "projects"} <= tables


def upgrade() -> None:
    if not _present(op.get_bind()):
        return
    _replace_constraint(include_divergence=True)


def downgrade() -> None:
    conn = op.get_bind()
    if not _present(conn):
        return
    conn.execute(sa.text(f"UPDATE {_TABLE} SET origin = 'job' WHERE origin = 'divergence'"))
    _replace_constraint(include_divergence=False)
