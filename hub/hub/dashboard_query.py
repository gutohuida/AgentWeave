"""Read-only queries over one project's data, for dashboards (`ask-any-agent-for-a-dashboard-and-
get-one-that-stays`, FR-1 to FR-7 and FR-14).

**The project boundary is the Hub's, not the query's** (FR-2). A query never sees the Hub's
database directly. Each one gets a fresh in-memory SQLite connection; the Hub's database file is
attached to it read-only (`mode=ro`) under a schema name drawn at random for that query alone, and
every queryable table is a TEMP view of the same name selecting only this project's rows and only
its queryable columns. An unqualified `tasks` resolves to the view (TEMP comes first), and the
authorizer refuses every read of the attached file that is not made through one of those views, so
`main.tasks`, `sqlite_master`, `pragma_database_list` and a table no view covers are refused rather
than answered. The random schema name is refused by name as well, so a CTE named like a view cannot
reach the file around it.

**Never queryable** (FR-3): credentials and this machine's paths. Their tables have no view and
their columns are left out of the views, so `select *` cannot reach them; a query that names one is
refused `not_queryable` with a message naming it, before anything runs.

**Read-only** (FR-4): the file is opened `mode=ro`, `query_only` is on, and the authorizer refuses
every write, schema change, attach and pragma with `read_only`. Recursive CTEs are reads.

**Bounded and off the loop** (FR-6, FR-14): a progress handler stops a query at
`aw_dashboard_query_timeout` seconds (`timeout`); a result is cut at `aw_dashboard_query_max_rows`
and says `truncated`. The query runs on this module's own threads, never the event loop's and never
the blocking pool git uses, and SQLite releases the GIL while it steps.

`x REGEXP 'pattern'` searches any text column (FR-5) with the `regex` package (Python `re` syntax),
not `re`: a single `re.search` cannot be interrupted and holds the GIL throughout, so one
backtracking pattern would run past the time limit and stall the event loop with it. `regex` is
given the time left before the query's deadline and releases the GIL while it matches.

`query_reference()` is generated from the running models (FR-7): exactly the tables and columns
the views expose, with each column's type and a meaning taken from the model's own comments.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import re
import secrets
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, TypedDict
from urllib.parse import quote

import regex
from sqlalchemy.dialects import sqlite as sqlite_dialect

from hub import config
from hub.db.models import Base

#: Tables no query can read, and what each holds, for the refusal's message.
NOT_QUERYABLE_TABLES: Dict[str, str] = {
    "api_keys": "API keys are credentials",
    "operator_credentials": "operator credentials are credentials",
    "workspace_fingerprints": "workspace fingerprints hold this machine's paths",
}

#: Columns no query can read, by table, and what each holds.
NOT_QUERYABLE_COLUMNS: Dict[Tuple[str, str], str] = {
    ("runs", "capability_token_hash"): "run tokens are credentials",
    ("runs", "workspace_dir"): "a run's workspace is this machine's path",
    ("trace_settings", "otlp_headers"): "the trace exporter's headers are credentials",
    ("projects", "working_directory"): "the project directory is this machine's path",
    ("projects", "path_key"): "the project directory's key is this machine's path",
    ("inbound_queue_entries", "work_dir"): "a run's workspace is this machine's path",
    ("vault_settings", "private_location"): "the private vault's folder is this machine's path",
}

#: Prefix of the per-query schema name the database file is attached under.
_SOURCE_PREFIX = "aw_src_"

#: Statements that are not reads, by their first keyword.
_WRITE_KEYWORDS = frozenset(
    {
        "insert", "update", "delete", "replace", "upsert", "drop", "create", "alter", "attach",
        "detach", "pragma", "vacuum", "reindex", "analyze", "begin", "commit", "end", "rollback",
        "savepoint", "release",
    }
)  # fmt: skip

# Authorizer action codes (sqlite3.h), named in the stdlib only from 3.11 on some builds.
_SQLITE_PRAGMA = 19
_SQLITE_READ = 20
_SQLITE_SELECT = 21
_SQLITE_FUNCTION = 31
_SQLITE_RECURSIVE = 33
_ALLOWED_ACTIONS = frozenset({_SQLITE_SELECT, _SQLITE_RECURSIVE})

#: How many SQLite VM instructions run between two looks at the clock.
_PROGRESS_STEPS = 10_000

#: Separate threads, so a query running to its time limit never waits behind, or holds up, git.
_MAX_WORKERS = 4
_executor: Optional[ThreadPoolExecutor] = None


class QueryResult(TypedDict):
    columns: List[str]
    rows: List[List[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: float


class QueryRefused(Exception):  # noqa: N818 - "refused" is the outcome, not a fault
    """A query the Hub will not answer: `code` is `not_queryable`, `read_only`, `timeout` or
    `query_error`; routes answer it as 422 `{"detail": {"code", "message"}}`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def detail(self) -> Dict[str, str]:
        return {"code": self.code, "message": self.message}


# ------------------------------------------------------------------------------- what is exposed


@dataclass(frozen=True)
class _Exposed:
    name: str
    columns: Tuple[str, ...]
    #: SQL condition selecting the project's rows; `{src}` and `{pid}` are filled per query.
    scope: str


@functools.lru_cache(maxsize=1)
def _exposed_tables() -> Tuple[_Exposed, ...]:
    """Every queryable table from the running models, with its queryable columns and the
    condition that keeps it to one project. A table with neither a `project_id` nor a foreign key
    to a table that has one is not project data, and is not exposed."""
    tables = Base.metadata.tables
    scoped = {name for name, t in tables.items() if "project_id" in t.columns}
    out: List[_Exposed] = []
    for name in sorted(tables):
        if name in NOT_QUERYABLE_TABLES:
            continue
        table = tables[name]
        if name == "projects":
            scope = "id = {pid}"
        elif name in scoped:
            scope = "project_id = {pid}"
        else:
            fks = [fk for fk in table.foreign_keys if fk.column.table.name in scoped]
            if not fks:
                continue
            fk = fks[0]
            scope = (
                f'"{fk.parent.name}" IN (SELECT "{fk.column.name}" FROM {{src}}."{fk.column.table.name}"'
                " WHERE project_id = {pid})"
            )
        columns = tuple(
            c.name for c in table.columns if (name, c.name) not in NOT_QUERYABLE_COLUMNS
        )
        out.append(_Exposed(name, columns, scope))
    return tuple(out)


def _forbidden_names() -> Dict[str, str]:
    names = dict(NOT_QUERYABLE_TABLES)
    names.update({column: why for (_, column), why in NOT_QUERYABLE_COLUMNS.items()})
    return names


# --------------------------------------------------------------------------------- the reference


def _type_name(column: Any) -> str:
    try:
        compiled = column.type.compile(dialect=sqlite_dialect.dialect())
    except Exception:  # noqa: BLE001 - a type SQLite cannot name still has a class name
        compiled = type(column.type).__name__.upper()
    if compiled.startswith("DATETIME"):
        return "DATETIME (UTC, text 'YYYY-MM-DD HH:MM:SS.ffffff')"
    if compiled == "JSON":
        return "JSON (text; read with json_extract)"
    return compiled


def _clean(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _attribute_comments(cls: type) -> Dict[str, str]:
    """The comment lines written just above (or beside) each `name: Mapped[...]` in a model."""
    try:
        lines, _ = inspect.getsourcelines(cls)
    except (OSError, TypeError):
        return {}
    found: Dict[str, str] = {}
    attribute = re.compile(r"^\s+(\w+)\s*:\s*Mapped\[")
    for i, line in enumerate(lines):
        match = attribute.match(line)
        if not match:
            continue
        above: List[str] = []
        j = i - 1
        while j >= 0 and lines[j].strip().startswith("#"):
            above.insert(0, lines[j].strip().lstrip("#").strip())
            j -= 1
        inline = line.split("#", 1)[1].strip() if "#" in line else ""
        text = " ".join(part for part in (*above, inline) if part)
        if text:
            found[match.group(1)] = text
    return found


def _fallback_meaning(column: str) -> str:
    words = column.replace("_", " ")
    if column == "id":
        return "this row's id"
    if column == "project_id":
        return "the project's id (always this project)"
    if column.endswith("_id"):
        return f"id of the {words[:-3]} this row refers to"
    if column.endswith("_at"):
        return f"when it was {words[:-3]} (UTC)"
    return words


@functools.lru_cache(maxsize=1)
def _reference_tables() -> Tuple[Dict[str, Any], ...]:
    by_table: Dict[str, Tuple[type, Dict[str, str]]] = {}
    for mapper in Base.registry.mappers:
        table = getattr(mapper, "local_table", None)
        if table is None or getattr(table, "name", None) is None:
            continue
        comments = _attribute_comments(mapper.class_)
        by_column: Dict[str, str] = {}
        for prop in mapper.column_attrs:
            if prop.key in comments and prop.columns:
                by_column[prop.columns[0].name] = comments[prop.key]
        by_table[table.name] = (mapper.class_, by_column)

    out: List[Dict[str, Any]] = []
    for exposed in _exposed_tables():
        table = Base.metadata.tables[exposed.name]
        cls, comments = by_table.get(exposed.name, (None, {}))
        doc = inspect.getdoc(cls) if cls is not None else None
        meaning = _clean(doc.split("\n\n", 1)[0], 400) if doc else exposed.name.replace("_", " ")
        columns = []
        for name in exposed.columns:
            column = table.columns[name]
            text = column.comment or column.doc or comments.get(name) or _fallback_meaning(name)
            columns.append({"name": name, "type": _type_name(column), "meaning": _clean(text)})
        out.append({"name": exposed.name, "meaning": meaning, "columns": columns})
    return tuple(out)


def query_reference() -> Dict[str, Any]:
    """Everything a dashboard query can reach, generated from the running models."""
    timeout = config.settings.aw_dashboard_query_timeout
    max_rows = config.settings.aw_dashboard_query_max_rows
    return {
        "tables": [dict(t) for t in _reference_tables()],
        "notes": [
            "Every table holds only the current project's rows; no project filter is needed.",
            "SQLite SQL, read-only: SELECT and WITH (recursive CTEs included). Writes, schema "
            "changes, ATTACH and PRAGMA are refused.",
            "Regular expressions: `text_column REGEXP 'pattern'` (Python re syntax; a match counts as part of the query's time limit).",
            "JSON columns are text: read fields with json_extract(column, '$.field').",
            "Times are UTC text; julianday(end) - julianday(start) gives days between two.",
            f"A query is stopped after {timeout} s; a result is cut at {max_rows} rows "
            "and marked truncated.",
            "Credentials and this machine's paths are not queryable: "
            + ", ".join(sorted(_forbidden_names()))
            + ".",
        ],
        "limits": {"timeout_seconds": timeout, "max_rows": max_rows},
    }


# ---------------------------------------------------------------------------------- the query


def _identifiers(sql: str) -> Tuple[List[str], Set[str]]:
    """The query's words outside string literals and comments, in order, lowercased; and the
    set of every identifier (bare or quoted)."""
    words: List[str] = []
    idents: Set[str] = set()
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if sql.startswith("--", i):
            end = sql.find("\n", i)
            i = n if end < 0 else end + 1
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif ch == "'":
            i += 1
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2
                        continue
                    break
                i += 1
            i += 1
        elif ch in '"`[':
            close = "]" if ch == "[" else ch
            j = i + 1
            buf: List[str] = []
            while j < n:
                if sql[j] == close:
                    if close != "]" and j + 1 < n and sql[j + 1] == close:
                        buf.append(close)
                        j += 2
                        continue
                    break
                buf.append(sql[j])
                j += 1
            name = "".join(buf).lower()
            idents.add(name)
            words.append(name)
            i = j + 1
        elif ch.isalnum() or ch in "_$":
            j = i
            while j < n and (sql[j].isalnum() or sql[j] in "_$"):
                j += 1
            word = sql[i:j].lower()
            idents.add(word)
            words.append(word)
            i = j
        else:
            i += 1
    return words, idents


def _check_text(sql: str) -> None:
    words, idents = _identifiers(sql)
    forbidden = _forbidden_names()
    named = sorted(name for name in idents if name in forbidden)
    if named:
        raise QueryRefused(
            "not_queryable",
            "Not queryable: "
            + "; ".join(f"{name} ({forbidden[name]})" for name in named)
            + ". Credentials and this machine's paths cannot be read by a dashboard query.",
        )
    sources = sorted(name for name in idents if name.startswith(_SOURCE_PREFIX))
    if sources:
        raise QueryRefused("not_queryable", f"Not queryable: {', '.join(sources)}.")
    if words and words[0] in _WRITE_KEYWORDS:
        raise QueryRefused(
            "read_only",
            f"{words[0].upper()} is refused: dashboard queries are read-only (SELECT or WITH).",
        )


@functools.lru_cache(maxsize=512)
def _compiled(pattern: str) -> "regex.Pattern[str]":
    return regex.compile(pattern)


def _cell(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _run_sync(
    database_file: str, project_id: str, sql: str, timeout: float, max_rows: int
) -> QueryResult:
    started = time.monotonic()
    _check_text(sql)

    schema = _SOURCE_PREFIX + secrets.token_hex(8)
    refusal: List[QueryRefused] = []
    regex_error: List[str] = []
    regex_timed_out: List[bool] = []
    deadline = time.monotonic() + timeout
    conn = sqlite3.connect("file::memory:", uri=True, check_same_thread=False)
    try:
        uri = "file:" + quote(database_file.replace("\\", "/"), safe="/:") + "?mode=ro"
        conn.execute(f"ATTACH DATABASE ? AS {schema}", (uri,))
        present = {
            row[0]
            for row in conn.execute(f"SELECT name FROM {schema}.sqlite_master WHERE type = 'table'")
        }
        views: Dict[str, str] = {}
        pid = _sql_literal(project_id)
        for exposed in _exposed_tables():
            if exposed.name not in present:
                continue
            actual = {
                row[1] for row in conn.execute(f'PRAGMA {schema}.table_info("{exposed.name}")')
            }
            columns = [c for c in exposed.columns if c in actual]
            if not columns:
                continue
            scope = exposed.scope.format(src=schema, pid=pid)
            select = ", ".join(f'"{c}"' for c in columns)
            conn.execute(
                f'CREATE TEMP VIEW "{exposed.name}" AS SELECT {select} '
                f'FROM {schema}."{exposed.name}" WHERE {scope}'
            )
            views[exposed.name] = exposed.name
        conn.execute("PRAGMA query_only = ON")

        def regexp(pattern: Any, value: Any) -> Optional[int]:
            if pattern is None or value is None:
                return None
            try:
                compiled = _compiled(str(pattern))
            except regex.error as exc:
                regex_error.append(f"invalid regular expression {pattern!r}: {exc}")
                raise
            if isinstance(value, (bytes, bytearray)):
                value = bytes(value).decode("utf-8", "replace")
            text = value if isinstance(value, str) else str(value)
            try:
                found = compiled.search(
                    text, timeout=max(deadline - time.monotonic(), 0.001), concurrent=True
                )
            except TimeoutError:
                regex_timed_out.append(True)
                raise
            return 1 if found else 0

        conn.create_function("regexp", 2, regexp, deterministic=True)

        def refuse(code: str, message: str) -> int:
            if not refusal:
                refusal.append(QueryRefused(code, message))
            return sqlite3.SQLITE_DENY

        def authorize(
            action: int,
            arg1: Optional[str],
            arg2: Optional[str],
            db: Optional[str],
            source: Optional[str],
        ) -> int:
            if action == _SQLITE_READ:
                # No database: a CTE's or subquery's own result (`count(*)` over one), not storage.
                if db is None or (db == "temp" and arg1 in views):
                    return sqlite3.SQLITE_OK
                if db == schema and source in views:
                    return sqlite3.SQLITE_OK
                table = arg1 or "?"
                why = NOT_QUERYABLE_TABLES.get(
                    table, "it is not part of this project's queryable data"
                )
                return refuse("not_queryable", f"Not queryable: {table} ({why}).")
            if action in _ALLOWED_ACTIONS:
                return sqlite3.SQLITE_OK
            if action == _SQLITE_FUNCTION:
                if (arg2 or "").lower() == "load_extension":
                    return refuse("read_only", "load_extension is refused.")
                return sqlite3.SQLITE_OK
            if action == _SQLITE_PRAGMA:
                return refuse("read_only", "PRAGMA is refused: dashboard queries are read-only.")
            return refuse("read_only", "Refused: dashboard queries are read-only (SELECT or WITH).")

        conn.set_authorizer(authorize)
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, _PROGRESS_STEPS)

        try:
            cursor = conn.execute(sql)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            fetched = cursor.fetchmany(max_rows + 1)
        except sqlite3.Error as exc:
            if refusal:
                raise refusal[0] from None
            text = str(exc).replace(schema + ".", "")
            if "interrupted" in text or regex_timed_out:
                raise QueryRefused(
                    "timeout", f"The query ran longer than {timeout:g} seconds and was stopped."
                ) from None
            if regex_error:
                raise QueryRefused("query_error", regex_error[0]) from None
            lowered = text.lower()
            if "readonly" in lowered or "read-only" in lowered or "cannot modify" in lowered:
                raise QueryRefused(
                    "read_only", f"Refused: dashboard queries are read-only ({text})."
                ) from None
            raise QueryRefused("query_error", text) from None
        truncated = len(fetched) > max_rows
        rows = [[_cell(v) for v in row] for row in fetched[:max_rows]]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        }
    finally:
        conn.close()


def _pool() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=_MAX_WORKERS, thread_name_prefix="aw-dashboard-query"
        )
    return _executor


async def _database_file() -> str:
    """The file the Hub's engine actually has open (in the suite, the current test's file)."""
    from hub.db.engine import engine

    if engine.dialect.name != "sqlite":
        raise QueryRefused("query_error", "Dashboard queries need the Hub's SQLite database.")
    async with engine.connect() as conn:
        rows = (await conn.exec_driver_sql("PRAGMA database_list")).fetchall()
    for row in rows:
        if row[1] == "main" and row[2]:
            return str(row[2])
    raise QueryRefused("query_error", "The Hub's database is not a file a query can open.")


async def run_query(project_id: str, sql: str) -> QueryResult:
    """Run `sql` read-only over `project_id`'s data, off the event loop.

    Raises `QueryRefused` (`not_queryable`, `read_only`, `timeout`, `query_error`)."""
    if not isinstance(sql, str) or not sql.strip():
        raise QueryRefused("query_error", "The query is empty.")
    database_file = await _database_file()
    timeout = float(config.settings.aw_dashboard_query_timeout)
    max_rows = int(config.settings.aw_dashboard_query_max_rows)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _pool(), _run_sync, database_file, project_id, sql, timeout, max_rows
    )


def exposed_table_names() -> Sequence[str]:
    """The tables a query can read, in the reference's order."""
    return [t.name for t in _exposed_tables()]
