"""`Task.workspace_scheme` — the stamp that says which workspace scheme a task belongs to.

`2026-08-27-work-is-isolated-per-task`, design D4, tasks 4.5 and 4.11.

Two claims are under test and they are different in kind:

- **Who gets stamped** (`0095`). Exactly the tasks that had at least one `Run` when the migration
  ran, and no others. The discriminator is the *existence* of a run — R1 proposed reading
  `snapshot_commit_sha` instead, and `test_a_task_whose_runs_committed_nothing_is_grandfathered_too`
  is that correction stated as a measurement rather than a paragraph.
- **Who may write it** (source scan). Nobody but the migration. "The grandfathered set can only
  shrink" is not an argument about reachable states; it is true if and only if that one write is the
  only write, so the only way to hold it is to read the source.

The resolver that *reads* the column is phase 4B and is not tested here.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from hub.config import settings
from hub.db.engine import async_session_factory
from hub.db.models import Task

ALEMBIC_INI = Path(__file__).parent.parent / "hub" / "alembic.ini"
REPO_ROOT = Path(__file__).parent.parent.parent

# The revision under test, and the one a synthetic database is stamped at so that upgrading runs
# this migration and only this migration.
REVISION = "0095"
PREVIOUS_REVISION = "0094"


def _run_alembic_with(db_url: str, revision: str = "head") -> None:
    """Run `alembic upgrade`/`downgrade` synchronously against *db_url*.

    **Every call here passes `REVISION` rather than taking the `head` default.** This file is about
    what migration 0095 does, so it must stop where 0095 stops: upgrading to `head` made
    `_version(...) == REVISION` an assertion about the newest migration in the tree, and adding
    0096 turned two tests red without either one's subject having changed.

    Same shape as `test_migrations._run_alembic_with`, including the `settings.database_url` patch —
    `env.py` reads the singleton to build its engine, so without it alembic would migrate whatever
    database the suite happens to be configured for instead of the temporary one.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        command.upgrade(cfg, revision)


def _downgrade_alembic_with(db_url: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        command.downgrade(cfg, revision)


_TASKS_DDL = (
    "CREATE TABLE tasks ("
    "id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64) NOT NULL, title VARCHAR(256) NOT NULL, "
    "description TEXT NOT NULL DEFAULT '', status VARCHAR(32) NOT NULL DEFAULT 'pending', "
    "priority VARCHAR(16) NOT NULL DEFAULT 'medium', assignee VARCHAR(64), "
    "created_at DATETIME NOT NULL, updated DATETIME NOT NULL)"
)

# `snapshot_commit_sha` is here precisely because the migration must not read it. A synthetic
# schema without the column could not tell a correct migration from R1's rejected one.
_RUNS_DDL = (
    "CREATE TABLE runs ("
    "id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64) NOT NULL, agent VARCHAR(64) NOT NULL, "
    "task_id VARCHAR(64), status VARCHAR(32) NOT NULL DEFAULT 'completed', "
    "snapshot_commit_sha VARCHAR(64), started_at DATETIME NOT NULL)"
)


def _add_task(conn, task_id: str) -> None:
    conn.execute(
        "INSERT INTO tasks (id, project_id, title, created_at, updated) "
        "VALUES (?, 'proj-x', ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
        (task_id, f"Work for {task_id}"),
    )


def _add_run(conn, run_id: str, task_id: str | None, snapshot: str | None) -> None:
    conn.execute(
        "INSERT INTO runs (id, project_id, agent, task_id, snapshot_commit_sha, started_at) "
        "VALUES (?, 'proj-x', 'builder', ?, ?, '2026-01-01T00:00:00Z')",
        (run_id, task_id, snapshot),
    )


def _database_at_0094(tmp_path: Path, *, with_runs: bool = True, with_tasks: bool = True) -> Path:
    """A database stamped one revision below the one under test, so `upgrade head` runs only it."""
    db_file = tmp_path / "old_0094.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES (?)", (PREVIOUS_REVISION,))
        if with_tasks:
            conn.execute(_TASKS_DDL)
        if with_runs:
            conn.execute(_RUNS_DDL)
    return db_file


def _schemes(db_file: Path) -> dict[str, str]:
    with sqlite3.connect(db_file) as conn:
        return {row[0]: row[1] for row in conn.execute("SELECT id, workspace_scheme FROM tasks")}


def _columns(db_file: Path, table: str) -> set[str]:
    with sqlite3.connect(db_file) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _load_migration_module():
    """Import `0095_task_workspace_scheme` from its path — `versions/` is not a package."""
    import importlib.util

    path = (
        Path(__import__("hub").__file__).parent
        / "migrations"
        / "versions"
        / f"{REVISION}_task_workspace_scheme.py"
    )
    spec = importlib.util.spec_from_file_location(f"_migration_{REVISION}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _version(db_file: Path) -> str:
    with sqlite3.connect(db_file) as conn:
        return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]


# ---------------------------------------------------------------------------
# 4.5 — who the migration stamps
# ---------------------------------------------------------------------------


def test_the_migration_stamps_the_agent_scheme_on_exactly_the_tasks_that_had_a_run(
    tmp_path,
) -> None:
    """The whole discriminator in one table: a run, or no run.

    Four tasks, differing only in their runs. `task-ran` and `task-ran-twice` are grandfathered;
    `task-never-ran` and `task-only-an-unbound-run-exists` are not. Nothing about the run is read,
    which is what the next two tests pin individually.
    """
    db_file = _database_at_0094(tmp_path)
    with sqlite3.connect(db_file) as conn:
        for task_id in (
            "task-ran",
            "task-ran-twice",
            "task-never-ran",
            "task-only-an-unbound-run-exists",
        ):
            _add_task(conn, task_id)
        _add_run(conn, "run-1", "task-ran", "abc1234")
        _add_run(conn, "run-2", "task-ran-twice", "def5678")
        _add_run(conn, "run-3", "task-ran-twice", None)
        _add_run(conn, "run-4", None, "999aaaa")

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}", REVISION)

    assert _schemes(db_file) == {
        "task-ran": "agent",
        "task-ran-twice": "agent",
        "task-never-ran": "task",
        "task-only-an-unbound-run-exists": "task",
    }
    assert _version(db_file) == REVISION


def test_a_task_whose_runs_committed_nothing_is_grandfathered_too(tmp_path) -> None:
    """**R1's discriminator was wrong, and this is the case that proves it.**

    R1 proposed grandfathering on "a prior run with a non-null `snapshot_commit_sha`".
    `worktrees.snapshot_worktree` returns `None` for a clean tree (`hub/hub/worktrees.py:457-458`),
    so an agent that commits its own work — the normal case — ends its turn clean and records
    `NULL`. Under R1's rule that task keeps real committed work on the per-agent branch and is *not*
    grandfathered, so its next turn starts in a fresh task checkout cut from the integration base
    with its own history missing.

    The task here has one run, and that run's `snapshot_commit_sha` is `NULL`. It must be stamped
    `agent` anyway. A migration that read the snapshot column would leave it on `task` and fail
    here — which is exactly the mutation this test exists to catch.
    """
    db_file = _database_at_0094(tmp_path)
    with sqlite3.connect(db_file) as conn:
        _add_task(conn, "task-committed-its-own-work")
        _add_run(conn, "run-clean", "task-committed-its-own-work", None)

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}", REVISION)

    assert _schemes(db_file) == {"task-committed-its-own-work": "agent"}


def test_a_task_with_no_runs_at_all_keeps_the_task_scheme(tmp_path) -> None:
    """The other direction, stated on its own so a migration that stamped everything fails here.

    A task nobody has run has no work on any per-agent branch, so it has nothing to lose and gets
    the isolation this change exists to give it.
    """
    db_file = _database_at_0094(tmp_path)
    with sqlite3.connect(db_file) as conn:
        _add_task(conn, "task-fresh")

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}", REVISION)

    assert _schemes(db_file) == {"task-fresh": "task"}


def test_an_existing_row_is_never_left_null(tmp_path) -> None:
    """The column is `NOT NULL`, and rows that predate it are filled by the server default.

    An `ADD COLUMN ... NOT NULL` without one fails outright on a populated table, so this is the
    assertion that the migration's `server_default` is not decorative.
    """
    db_file = _database_at_0094(tmp_path)
    with sqlite3.connect(db_file) as conn:
        _add_task(conn, "task-old")

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}", REVISION)

    with sqlite3.connect(db_file) as conn:
        nulls = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE workspace_scheme IS NULL"
        ).fetchone()[0]
    assert nulls == 0


# ---------------------------------------------------------------------------
# 4.11 — the guards, the downgrade, the default, and who may write
# ---------------------------------------------------------------------------


def test_the_migration_is_a_no_op_when_tasks_is_missing(tmp_path) -> None:
    """The `0033`/`0034` guard shape. An upgrade starting from an early revision reaches this
    migration with only that revision's tables; `create_all` then builds `tasks` from the model with
    the column already on it. Without the guard the upgrade raises and the database is stranded."""
    db_file = _database_at_0094(tmp_path, with_tasks=False, with_runs=False)

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}", REVISION)

    assert _version(db_file) == REVISION
    with sqlite3.connect(db_file) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "tasks" not in tables


def test_the_column_is_added_but_nothing_is_stamped_when_runs_is_missing(tmp_path) -> None:
    """`runs` is guarded separately from `tasks`, because a chain can have one without the other.

    A database with tasks and no runs table has no runs, so "no task is grandfathered" is the
    correct answer rather than an error — and the column must still arrive, or the model and the
    schema disagree.
    """
    db_file = _database_at_0094(tmp_path, with_runs=False)
    with sqlite3.connect(db_file) as conn:
        _add_task(conn, "task-in-a-runless-database")

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}", REVISION)

    assert "workspace_scheme" in _columns(db_file, "tasks")
    assert _schemes(db_file) == {"task-in-a-runless-database": "task"}


def test_the_migration_is_idempotent_over_an_already_migrated_column(tmp_path) -> None:
    """Re-running the upgrade step against a schema that already has the column must not raise.

    Alembic will not normally run a revision twice, but this migration's own `_columns` check is
    what lets an operator recover a half-applied chain, and a guard nothing exercises is a guard
    that rots.
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    db_file = _database_at_0094(tmp_path)
    with sqlite3.connect(db_file) as conn:
        _add_task(conn, "task-ran")
        _add_run(conn, "run-1", "task-ran", None)

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}", REVISION)

    # Loaded by path, not by name: `versions/` is not a package and the module's name starts with
    # a digit, so alembic itself reaches it this way.
    module = _load_migration_module()
    sync_engine = sa.create_engine(f"sqlite:///{db_file}")
    with sync_engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()
    sync_engine.dispose()

    assert _schemes(db_file) == {"task-ran": "agent"}


def test_the_downgrade_drops_the_column(tmp_path) -> None:
    """A migration that cannot be undone strands anyone who upgrades by accident. `tasks` carries
    no CHECK constraint naming this column, which is what makes the drop possible on SQLite at
    all — the trap already documented on `TaskTransition.origin` and `SpecDocument.rigor`."""
    db_file = _database_at_0094(tmp_path)
    with sqlite3.connect(db_file) as conn:
        _add_task(conn, "task-ran")
        _add_run(conn, "run-1", "task-ran", None)

    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run_alembic_with(db_url, REVISION)
    assert "workspace_scheme" in _columns(db_file, "tasks")

    _downgrade_alembic_with(db_url, PREVIOUS_REVISION)

    assert "workspace_scheme" not in _columns(db_file, "tasks")
    assert _version(db_file) == PREVIOUS_REVISION


@pytest.mark.asyncio
async def test_a_task_created_today_defaults_to_the_task_scheme(app) -> None:
    """The default is the whole reason the grandfathered set can only shrink: every task created
    after the migration is a task-scheme task, and nothing may make it anything else."""
    async with async_session_factory() as session:
        session.add(Task(id="task-new", project_id="proj-test", title="Fresh"))
        await session.commit()
        stored = await session.get(Task, "task-new")
        assert stored is not None
        assert stored.workspace_scheme == "task"


def test_nothing_outside_the_migration_writes_the_column() -> None:
    """D4's mechanism, and the only place it can be enforced.

    "The grandfathered set can only shrink" is true if and only if `0095` holds the only write.
    Python cannot express that, and a comment is not a mechanism, so the codebase's answer is a
    source scan — the same one `test_task_attribution.py::test_the_owning_module_is_the_only_reader`
    uses, for the same reason.

    **Four spellings, not the three the review named.** R3 corrected R1's single-form scan to three
    — `.workspace_scheme =`, `workspace_scheme=` and `values(workspace_scheme` — because a scan for
    one form passes against a real write in either of the others. Implementing it showed the same
    hole one level down: all three are *Python* write forms, and `0095`'s own write is raw SQL
    (`SET workspace_scheme = 'agent'`), which none of them matches. A three-form scan would
    therefore have exempted a file it never matched — vacuously — while a runtime `session.execute`
    of the same SQL anywhere else went unseen. The fourth form closes that, and it is also what
    makes the exemption below mean something.

    What this still cannot see: `setattr(task, "workspace_scheme", ...)` and any write assembled
    from a variable. Recorded rather than chased — both are visible in review in a way an ordinary
    assignment is not, and a scan that tried to catch them would match this docstring.
    """
    forms = (
        ".workspace_scheme =",
        "workspace_scheme=",
        "values(workspace_scheme",
        "set workspace_scheme",
    )
    allowed = {Path("migrations") / "versions" / f"{REVISION}_task_workspace_scheme.py"}

    roots = {
        "hub": Path(__import__("hub").__file__).parent,
        "src": REPO_ROOT / "src",
    }
    assert roots["src"].is_dir(), f"{roots['src']} is not there — the scan would pass vacuously"

    offenders: list[str] = []
    matched_allowed = False
    for label, root in roots.items():
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(root)
            source = path.read_text(encoding="utf-8").lower()
            hits = [form for form in forms if form in source]
            if not hits:
                continue
            if label == "hub" and relative in allowed:
                matched_allowed = True
                continue
            offenders.append(f"{label}/{relative} ({', '.join(hits)})")

    assert offenders == [], (
        f"{offenders} write Task.workspace_scheme. Only migration {REVISION} may: the column is "
        f"stamped once and read forever, and that single write is the entire reason the "
        f"grandfathered set of tasks can only shrink. A runtime write would let a task change "
        f"schemes mid-life — which is the failure design D4 rejected R1's live discriminator for."
    )
    assert matched_allowed, (
        f"migration {REVISION} matched none of {forms}, so the allow-list exempted a file that "
        f"never triggered the scan and this test proved nothing about the source it read"
    )
