"""tickets have readable ids -- tasks.readable_id, acronyms, acronym_counters

Revision ID: 0158
Revises: 0157
Create Date: 2026-11-01 00:00:00.000000

`tickets-have-readable-ids` (Tier 2). A task gets a readable id, `BPS-3`, beside its stored one.

Additive, on live data: `tasks.readable_id`, `spec_documents.acronym` and `acronym_chosen`,
`projects.acronym`, and a new table `acronym_counters`. Every project and document is given an
acronym, and every existing task a number in creation order within its acronym, its spec's where the
spec still exists and otherwise its project's. No stored id, branch or reference is read for anything
but ordering, or rewritten.

`tasks.readable_id` stays nullable at the database: SQLite cannot add a NOT NULL column without a
table rebuild, and rebuilding the table twelve foreign keys point at is the hazard this design set
out to avoid.

A task whose project row is gone has nothing to be numbered under and keeps a NULL, which the
partial-free unique index allows.

Rollback: the downgrade drops what this added (plain `DROP COLUMN`, SQLite 3.35+, as `0152` does).
Ids written in text after the upgrade stop resolving, which is why the drawer also shows the stored
id.

`_candidates` restates `readable_ids.candidates` at the time of writing, so that this migration keeps
doing what it was run to do; `test_tickets_have_readable_ids` pins the two together.

Guarded for a database without the tables (an upgrade from an early revision) and for columns already
present (a database built by `create_all`).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterator, List, Optional, Set, Tuple
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0158"
down_revision = "0157"
branch_labels = None
depends_on = None

_ACRONYM_RE = re.compile(r"^[A-Z][A-Z0-9]{1,4}$")
_NEVER = frozenset({"TASK", "SK", "FR"})
_STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    ]
)
_WORD_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")
_INDEX = "uq_tasks_project_readable_id"


def _words(title: str) -> List[str]:
    folded = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    words = _WORD_RE.findall(folded)
    significant = [word for word in words if word.lower() not in _STOP_WORDS]
    return [word.upper() for word in (significant if len(significant) >= 2 else words)]


def _candidates(title: str, fallback: str) -> Iterator[str]:
    def proposals() -> Iterator[str]:
        words = _words(title) or [fallback]
        while words and not words[0][0].isalpha():
            words = words[1:]
        words = words or [fallback]
        initials = "".join(word[0] for word in words)[:5]
        yield initials
        others = initials[1:]
        for length in range(2 if others else 3, 6):
            yield (words[0][:length] + others)[:5]
        joined = "".join(words)
        for length in (3, 4, 5, 2):
            yield joined[:length]
        for digits, keep in ((1, 4), (2, 3), (3, 2)):
            for number in range(2, 10**digits):
                yield f"{joined[:keep]}{number}"

    seen: Set[str] = set()
    for proposal in proposals():
        if proposal in seen or proposal in _NEVER or not _ACRONYM_RE.match(proposal):
            continue
        seen.add(proposal)
        yield proposal
    while True:
        yield "X" + uuid4().hex[:4].upper()


def _take(title: str, fallback: str, taken: Set[str]) -> str:
    for candidate in _candidates(title, fallback):
        if candidate not in taken:
            taken.add(candidate)
            return candidate
    raise AssertionError("_candidates does not end")  # pragma: no cover


def _add_column(inspector: sa.Inspector, table: str, column: sa.Column) -> None:
    if column.name not in {c["name"] for c in inspector.get_columns(table)}:
        op.add_column(table, column)


def _backfill(conn: sa.engine.Connection) -> None:
    """Acronyms, then numbers. Only rows still without one, so a re-run after `create_all` is safe."""
    taken_by_project: Dict[str, Set[str]] = {}
    high_water: Dict[Tuple[str, str], int] = {}
    for project_id, acronym, mark in conn.execute(
        sa.text("SELECT project_id, acronym, high_water FROM acronym_counters")
    ):
        taken_by_project.setdefault(project_id, set()).add(acronym)
        high_water[(project_id, acronym)] = mark

    project_acronyms: Dict[str, str] = {}
    # The project first: it is what the operator most expects to read as itself.
    for project_id, name, acronym in conn.execute(
        sa.text("SELECT id, name, acronym FROM projects ORDER BY created_at, id")
    ).all():
        taken = taken_by_project.setdefault(project_id, set())
        if not acronym:
            acronym = _take(name or "", "PROJ", taken)
            conn.execute(
                sa.text("UPDATE projects SET acronym = :a WHERE id = :i"),
                {"a": acronym, "i": project_id},
            )
        project_acronyms[project_id] = acronym
        high_water.setdefault((project_id, acronym), 0)

    document_acronyms: Dict[str, Tuple[str, str]] = {}
    for document_id, project_id, title, acronym in conn.execute(
        sa.text("SELECT id, project_id, title, acronym FROM spec_documents ORDER BY created_at, id")
    ).all():
        taken = taken_by_project.setdefault(project_id, set())
        if not acronym:
            acronym = _take(title or "", "SPEC", taken)
            conn.execute(
                sa.text("UPDATE spec_documents SET acronym = :a WHERE id = :i"),
                {"a": acronym, "i": document_id},
            )
        document_acronyms[document_id] = (project_id, acronym)
        high_water.setdefault((project_id, acronym), 0)

    updates = []
    for task_id, project_id, document_id in conn.execute(
        sa.text(
            "SELECT id, project_id, spec_document_id FROM tasks WHERE readable_id IS NULL "
            "ORDER BY created_at, rowid"
        )
    ).all():
        acronym: Optional[str] = None
        owner = document_acronyms.get(document_id) if document_id else None
        if owner is not None and owner[0] == project_id:
            acronym = owner[1]
        else:
            acronym = project_acronyms.get(project_id)
        if acronym is None:
            continue
        number = high_water[(project_id, acronym)] + 1
        high_water[(project_id, acronym)] = number
        updates.append({"r": f"{acronym}-{number}", "i": task_id})
    if updates:
        conn.execute(sa.text("UPDATE tasks SET readable_id = :r WHERE id = :i"), updates)

    conn.execute(sa.text("DELETE FROM acronym_counters"))
    rows = [
        {"p": project_id, "a": acronym, "h": mark}
        for (project_id, acronym), mark in high_water.items()
    ]
    if rows:
        conn.execute(
            sa.text(
                "INSERT INTO acronym_counters (project_id, acronym, high_water) "
                "VALUES (:p, :a, :h)"
            ),
            rows,
        )


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if not {"tasks", "projects", "spec_documents"} <= tables:
        return
    if "acronym_counters" not in tables:
        op.create_table(
            "acronym_counters",
            sa.Column("project_id", sa.String(64), primary_key=True),
            sa.Column("acronym", sa.String(5), primary_key=True),
            sa.Column("high_water", sa.Integer(), nullable=False, server_default="0"),
        )
    _add_column(inspector, "projects", sa.Column("acronym", sa.String(5), nullable=True))
    _add_column(inspector, "spec_documents", sa.Column("acronym", sa.String(5), nullable=True))
    _add_column(
        inspector,
        "spec_documents",
        sa.Column("acronym_chosen", sa.Boolean(), nullable=False, server_default="0"),
    )
    _add_column(inspector, "tasks", sa.Column("readable_id", sa.String(32), nullable=True))
    _backfill(conn)
    if _INDEX not in {i["name"] for i in sa.inspect(conn).get_indexes("tasks")}:
        op.create_index(_INDEX, "tasks", ["project_id", "readable_id"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if "tasks" in tables:
        if _INDEX in {i["name"] for i in inspector.get_indexes("tasks")}:
            op.drop_index(_INDEX, table_name="tasks")
        if "readable_id" in {c["name"] for c in inspector.get_columns("tasks")}:
            op.drop_column("tasks", "readable_id")
    if "spec_documents" in tables:
        existing = {c["name"] for c in inspector.get_columns("spec_documents")}
        for column in ("acronym", "acronym_chosen"):
            if column in existing:
                op.drop_column("spec_documents", column)
    if "projects" in tables and "acronym" in {c["name"] for c in inspector.get_columns("projects")}:
        op.drop_column("projects", "acronym")
    if "acronym_counters" in tables:
        op.drop_table("acronym_counters")
