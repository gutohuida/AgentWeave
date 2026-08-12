"""make the agent name unique within a project

Revision ID: 0063
Revises: 0062
Create Date: 2026-08-12 09:50:00.000000

`ix_agents_project_name` has existed since 0004 as a plain index. Closing umbrella task 13.2 of
`2026-07-30-hub-native-experience`, it becomes unique.

**What this actually fixes is a race, not a missing check.** Registration already refuses a
duplicate with 409 (`api/v1/agents.py:627` and `:1152`), so the ordinary path was never the
problem. Both of those read with a SELECT and then INSERT, which two concurrent registrations can
interleave: both see no existing row, both insert, and the project ends up with two agents
answering to one name. Every lookup in the Hub addresses an agent as
`(project_id, name)` — messages, task assignment, triggers, context — and with two matching rows
`scalar()` silently returns whichever the database hands back first. The index makes the second
insert fail rather than succeed wrongly.

**Pre-existing duplicates are renamed, not deleted, and not left to fail the upgrade.**

A database that already holds duplicates cannot take a unique index, so this migration has to
decide something. The three options are to fail the upgrade, to delete the extra rows, or to rename
them:

- Failing leaves the operator with a Hub that will not start and no in-app way to fix it, because
  the only repair surface is the UI that will not come up.
- Deleting is unacceptable. An agent owns conversations, runs, tasks and messages by `id`; removing
  the row to satisfy an index destroys real history to tidy a column.
- Renaming preserves every row and every foreign key, because relationships reference `agents.id`
  and never the name.

So the oldest row (lowest `rowid`) keeps the name and each later collision becomes `<name>-2`,
`<name>-3`, and so on, retrying past any suffix that is itself taken. The result is truncated to 32
characters to stay inside `AGENT_NAME_RE` (`^[a-zA-Z0-9_-]{1,32}$`), and the operator can rename it
to anything they prefer afterwards.

This is a real change to operator-visible data, which is why it is spelled out here rather than
done quietly: a duplicate name was *already* broken — the agent could not be addressed reliably —
so renaming makes an existing ambiguity visible instead of introducing a new one.

Guarded for a missing table, like 0038-0062.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

_AGENTS = "agents"
_INDEX = "ix_agents_project_name"
_MAX_NAME = 32


def _has_table(conn) -> bool:
    return _AGENTS in set(sa.inspect(conn).get_table_names())


def _index_names(conn) -> set:
    return {index["name"] for index in sa.inspect(conn).get_indexes(_AGENTS)}


def _suffixed(name: str, ordinal: int) -> str:
    """`name-2`, truncated so the result still satisfies AGENT_NAME_RE's 32-character limit."""
    suffix = f"-{ordinal}"
    return f"{name[: _MAX_NAME - len(suffix)]}{suffix}"


def _dedupe_agent_names(conn) -> None:
    duplicates = conn.execute(
        sa.text(
            "SELECT project_id, name FROM agents " "GROUP BY project_id, name HAVING COUNT(*) > 1"
        )
    ).fetchall()

    for project_id, name in duplicates:
        # The oldest row keeps the name; every later one is renamed in insertion order.
        rows = conn.execute(
            sa.text("SELECT rowid FROM agents WHERE project_id = :p AND name = :n ORDER BY rowid"),
            {"p": project_id, "n": name},
        ).fetchall()

        for position, (rowid,) in enumerate(rows[1:], start=2):
            ordinal = position
            while True:
                candidate = _suffixed(name, ordinal)
                taken = conn.execute(
                    sa.text("SELECT 1 FROM agents WHERE project_id = :p AND name = :n LIMIT 1"),
                    {"p": project_id, "n": candidate},
                ).fetchone()
                if taken is None:
                    break
                ordinal += 1
            conn.execute(
                sa.text("UPDATE agents SET name = :new WHERE rowid = :r"),
                {"new": candidate, "r": rowid},
            )


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_table(conn):
        return

    _dedupe_agent_names(conn)

    if _INDEX in _index_names(conn):
        op.drop_index(_INDEX, table_name=_AGENTS)
    op.create_index(_INDEX, _AGENTS, ["project_id", "name"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    if not _has_table(conn):
        return

    # The renames are not undone: the names are now the agents' real names, and reverting them
    # would reintroduce the ambiguity this migration removed.
    if _INDEX in _index_names(conn):
        op.drop_index(_INDEX, table_name=_AGENTS)
    op.create_index(_INDEX, _AGENTS, ["project_id", "name"])
