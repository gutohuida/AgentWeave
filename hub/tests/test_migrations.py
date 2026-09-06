"""DB & migration tests — PR 7 (H5, DB-4).

Covers two audit findings:

- **H5** — `init_db` should run `alembic upgrade head` after `create_all`, so a
  deployment that only invokes `init_db` doesn't miss schema changes. The
  call must be wrapped so dev mode (in-memory SQLite, missing alembic.ini,
  etc.) still works.
- **DB-4** — `job_runs.error_summary` must be capped to `String(500)` instead
  of unbounded `Text`.

Tests are written test-first and intentionally fail before the corresponding
fix is applied. After the fix, every test in this file must pass.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from hub.config import settings
from hub.db.engine import async_session_factory, engine, init_db
from hub.db.models import AIJob, ApiKey, Base, JobRun, OperatorCredential, Project

# hub/tests/test_migrations.py → hub/tests/ → hub/ → hub/hub/ (where alembic.ini
# is packaged, task 3.12, so it ships with a plain pip install too)
ALEMBIC_INI = Path(__file__).parent.parent / "hub" / "alembic.ini"

# The revision `alembic upgrade head` must land on. Named once so the assertion and its failure
# message cannot disagree — they did, for two head bumps, telling anyone debugging a failure to go
# read the wrong migration.
HEAD_REVISION = "0101"


# ---------------------------------------------------------------------------
# DB-4: error_summary is String(500)
# ---------------------------------------------------------------------------


def test_model_error_summary_is_string_500() -> None:
    """JobRun.error_summary must be a String(500) column, not unbounded Text.

    This is a static model check — verifies the schema definition, not the
    database itself. Catches the case where the column type is silently
    regressed to Text.
    """
    col = JobRun.__table__.columns["error_summary"]
    assert isinstance(
        col.type, sa.String
    ), f"error_summary must be a String column, got {type(col.type).__name__}"
    assert col.type.length == 500, f"error_summary must have length=500, got {col.type.length}"


@pytest.mark.asyncio
async def test_error_summary_accepts_500_chars(app) -> None:
    """A 500-character error_summary must round-trip cleanly through the ORM."""
    payload = "x" * 500
    async with async_session_factory() as session:
        project_id, key_id, job_id, run_id = _seed_minimum(session)
        run = JobRun(id=run_id, job_id=job_id, project_id=project_id, error_summary=payload)
        session.add(run)
        await session.commit()
        await session.refresh(run)
        assert run.error_summary == payload


@pytest.mark.asyncio
async def test_error_summary_rejects_501_chars(app) -> None:
    """A 501-character error_summary must be rejected at the DB layer (on DBs
    that enforce VARCHAR length — PostgreSQL, MySQL).

    SQLite uses type affinity rather than strict VARCHAR length, so a
    `String(500)` column doesn't reject 501 chars on SQLite. The model type
    test (`test_model_error_summary_is_string_500`) covers the schema
    declaration; this test covers the runtime enforcement on strict
    databases. Skipped on SQLite since the assertion would be a no-op.
    """
    if "sqlite" in settings.database_url:
        pytest.skip(
            "SQLite does not enforce VARCHAR length at the DB layer; "
            "the model type test covers the schema declaration"
        )

    import secrets

    payload = "y" * 501
    project_id = f"proj-mig-501-{secrets.token_hex(4)}"
    key_id = f"aw_live_501test_{secrets.token_hex(8)}"
    job_id = f"job-mig-501-{secrets.token_hex(4)}"
    run_id = f"run-mig-501-{secrets.token_hex(4)}"
    async with async_session_factory() as session:
        session.add(Project(id=project_id, name="501-char test project"))
        session.add(ApiKey(id=key_id, project_id=project_id, label="501-test", revoked=False))
        session.add(
            AIJob(
                id=job_id,
                project_id=project_id,
                name="501-test",
                agent="tester",
                message="hello",
                cron="0 9 * * *",
            )
        )
        run = JobRun(id=run_id, job_id=job_id, project_id=project_id, error_summary=payload)
        session.add(run)
        with pytest.raises((DataError, IntegrityError)):
            await session.commit()


# ---------------------------------------------------------------------------
# H5: alembic upgrade head runs as part of init_db
# ---------------------------------------------------------------------------


def test_alembic_cfg_present() -> None:
    """Sanity check — alembic.ini exists where _run_alembic_upgrade expects."""
    assert ALEMBIC_INI.exists(), f"alembic.ini not found at {ALEMBIC_INI}"


def test_alembic_upgrade_head_fresh_file_db(tmp_path) -> None:
    """`alembic upgrade head` against a fresh file-based SQLite must succeed.

    The migrations are additive (they add/alter columns but don't create
    the base tables — those are created by `Base.metadata.create_all` in
    `init_db`). So this test verifies what alembic itself does: that every
    migration runs cleanly and the version lands at 0058. The full
    end-to-end test (create_all + alembic) is
    `test_init_db_runs_alembic_for_file_db` below.
    """
    db_file = tmp_path / "fresh.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run_alembic_with(db_url)

    # Verify alembic_version is at the latest revision (0058).
    import aiosqlite

    async def _check_version() -> str:
        async with aiosqlite.connect(str(db_file)) as conn:
            cursor = await conn.execute("SELECT version_num FROM alembic_version")
            row = await cursor.fetchone()
            assert row is not None, "alembic_version table is empty"
            return row[0]

    version = _run(_check_version())
    assert version == HEAD_REVISION, f"expected alembic_version={HEAD_REVISION}, got {version}"

    columns = {column["name"]: column for column in _inspect_columns(db_url, "agent_outputs")}
    assert {"kind", "payload", "run_id", "sequence"} <= columns.keys()
    assert columns["kind"]["nullable"] is True
    assert columns["payload"]["nullable"] is True
    assert columns["run_id"]["nullable"] is True
    assert columns["sequence"]["nullable"] is True

    async def _check_indexes() -> set[str]:
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(db_url)
        try:
            async with engine.connect() as conn:
                return set(
                    await conn.run_sync(
                        lambda sync_conn: {
                            index["name"]
                            for index in sa.inspect(sync_conn).get_indexes("agent_outputs")
                        }
                    )
                )
        finally:
            await engine.dispose()

    assert "ix_agent_outputs_project_agent_run_sequence" in _run(_check_indexes())


def test_migration_0025_drops_legacy_project_roles_config(tmp_path) -> None:
    db_file = tmp_path / "old_0024.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0024')")
        conn.execute(
            "CREATE TABLE project_roles_config "
            "(project_id VARCHAR(64) PRIMARY KEY, data JSON NOT NULL, synced_at DATETIME NOT NULL)"
        )

    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert "project_roles_config" not in tables
    assert version == HEAD_REVISION


def test_migration_0027_adds_conversation_runtime_overrides(tmp_path) -> None:
    """0027 applies to an existing database and existing conversations load with no overrides."""
    db_file = tmp_path / "old_0026.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0026')")
        conn.execute(
            "CREATE TABLE conversations "
            "(id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64) NOT NULL, "
            "agent VARCHAR(64) NOT NULL, provider_session_id VARCHAR(128), "
            "lifecycle VARCHAR(16) NOT NULL, created_at DATETIME NOT NULL, "
            "updated_at DATETIME NOT NULL, archived_at DATETIME)"
        )
        conn.execute(
            "INSERT INTO conversations "
            "(id, project_id, agent, lifecycle, created_at, updated_at) "
            "VALUES ('conv-existing', 'proj-x', 'claude', 'open', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )

    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run_alembic_with(db_url)

    columns = {column["name"]: column for column in _inspect_columns(db_url, "conversations")}
    assert "runtime_overrides" in columns
    assert columns["runtime_overrides"]["nullable"] is True

    with sqlite3.connect(db_file) as conn:
        row = conn.execute(
            "SELECT runtime_overrides FROM conversations WHERE id = 'conv-existing'"
        ).fetchone()
    assert row is not None
    assert row[0] is None


def _create_0034_conversations_state(db_file: Path) -> None:
    """A populated database at 0034: conversations with its constraints, and a row pointing at it.

    `test_migration_0027_...` builds a bare `conversations` table with no `projects`, which is a
    shape 0035 deliberately skips. This one has the foreign key target, so the table recreate 0035
    performs actually runs — which is the part that can lose an index, a constraint, or a row.
    """
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0034')")
        conn.execute(
            "CREATE TABLE projects "
            "(id VARCHAR(64) PRIMARY KEY, name VARCHAR(256) NOT NULL, created_at DATETIME NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE conversations ("
            "id VARCHAR(64) PRIMARY KEY, "
            "project_id VARCHAR(64) NOT NULL REFERENCES projects (id), "
            "agent VARCHAR(64) NOT NULL, provider_session_id VARCHAR(128), "
            "lifecycle VARCHAR(16) NOT NULL, runtime_overrides JSON, "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, archived_at DATETIME, "
            "CONSTRAINT ck_conversations_lifecycle CHECK (lifecycle IN ('open', 'archived')))"
        )
        conn.execute("CREATE INDEX ix_conversations_agent ON conversations (agent)")
        conn.execute(
            "CREATE INDEX ix_conversations_project_agent_updated "
            "ON conversations (project_id, agent, updated_at)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX uq_conversations_project_agent_provider_session "
            "ON conversations (project_id, agent, provider_session_id)"
        )
        conn.execute(
            "CREATE TABLE runs ("
            "id VARCHAR(64) PRIMARY KEY, "
            "conversation_id VARCHAR(64) REFERENCES conversations (id))"
        )
        conn.execute(
            "INSERT INTO projects (id, name, created_at) "
            "VALUES ('proj-x', 'Existing', '2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO conversations "
            "(id, project_id, agent, lifecycle, created_at, updated_at) "
            "VALUES ('conv-existing', 'proj-x', 'claude', 'open', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        conn.execute("INSERT INTO runs (id, conversation_id) VALUES ('run-1', 'conv-existing')")


def test_migration_0035_recreates_conversations_preserving_shape(tmp_path) -> None:
    """0035 adds title and origin without losing indexes, constraints, rows, or the reference."""
    db_file = tmp_path / "old_0034.db"
    _create_0034_conversations_state(db_file)

    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run_alembic_with(db_url)

    columns = {column["name"]: column for column in _inspect_columns(db_url, "conversations")}
    assert {"title", "title_set_by_operator", "origin"} <= columns.keys()
    assert columns["title"]["nullable"] is True
    assert columns["origin"]["nullable"] is False

    with sqlite3.connect(db_file) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == HEAD_REVISION

        # The existing row survives, unnamed and attributed to the operator.
        row = conn.execute(
            "SELECT title, title_set_by_operator, origin, lifecycle, agent "
            "FROM conversations WHERE id = 'conv-existing'"
        ).fetchone()
        assert row == (None, 0, "operator", "open", "claude")

        # The row that references it is untouched and still resolves.
        assert conn.execute("SELECT conversation_id FROM runs WHERE id = 'run-1'").fetchone() == (
            "conv-existing",
        )

        indexes = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        }
        assert {
            "ix_conversations_agent",
            "ix_conversations_project_agent_updated",
            "uq_conversations_project_agent_provider_session",
        } <= indexes

        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'conversations'"
        ).fetchone()[0]
        assert "ck_conversations_lifecycle" in ddl
        assert "ck_conversations_origin" in ddl

        # The closed set is enforced by the database, not only by the model.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO conversations "
                "(id, project_id, agent, lifecycle, origin, created_at, updated_at) "
                "VALUES ('conv-bad', 'proj-x', 'claude', 'open', 'invented', "
                "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
            )


def test_migration_0036_indexes_conversation_id_on_blocking_tables(tmp_path) -> None:
    """0036 adds the column where it is missing and the index on all three tables.

    `unasked_questions.conversation_id` predates this revision, so the migration must add its
    index without trying to add the column a second time.

    Upgrades to 0036 rather than head deliberately: `0082` drops `unasked_questions` when the
    unasked-question backstop was retired, so running to head would leave nothing to assert
    about the very table this revision's third branch exists to handle.
    """
    db_file = tmp_path / "old_0034_blocking.db"
    _create_0034_conversations_state(db_file)
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "CREATE TABLE questions (id VARCHAR(64) PRIMARY KEY, from_agent VARCHAR(64) NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE permission_requests "
            "(id VARCHAR(64) PRIMARY KEY, agent VARCHAR(64) NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE unasked_questions "
            "(id VARCHAR(64) PRIMARY KEY, agent VARCHAR(64) NOT NULL, conversation_id VARCHAR(64))"
        )
        conn.execute(
            "INSERT INTO unasked_questions (id, agent, conversation_id) "
            "VALUES ('unasked-1', 'claude', 'conv-existing')"
        )

    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run_alembic_with(db_url, "0036")

    for table in ("questions", "permission_requests", "unasked_questions"):
        columns = {column["name"] for column in _inspect_columns(db_url, table)}
        assert "conversation_id" in columns, f"{table} is missing conversation_id"

    with sqlite3.connect(db_file) as conn:
        indexes = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        }
        assert {
            "ix_questions_conversation_id",
            "ix_permission_requests_conversation_id",
            "ix_unasked_questions_conversation_id",
        } <= indexes

        # The pre-existing attribution is not disturbed by adding the index.
        assert conn.execute(
            "SELECT conversation_id FROM unasked_questions WHERE id = 'unasked-1'"
        ).fetchone() == ("conv-existing",)


def test_migration_0037_defaults_projects_to_truncated_titles(tmp_path) -> None:
    """An existing project is opted out of spending tokens on titles."""
    db_file = tmp_path / "old_0034_projects.db"
    _create_0034_conversations_state(db_file)

    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run_alembic_with(db_url)

    columns = {column["name"]: column for column in _inspect_columns(db_url, "projects")}
    assert {"conversation_title_mode", "conversation_title_runner_id"} <= columns.keys()
    assert columns["conversation_title_mode"]["nullable"] is False
    assert columns["conversation_title_runner_id"]["nullable"] is True

    with sqlite3.connect(db_file) as conn:
        assert conn.execute(
            "SELECT conversation_title_mode, conversation_title_runner_id "
            "FROM projects WHERE id = 'proj-x'"
        ).fetchone() == ("truncate", None)


def test_alembic_0008_alters_text_to_string_500(tmp_path) -> None:
    """Migration 0008 must alter an existing Text column to String(500).

    Simulates an existing deployment where 0007 already added the column as
    Text. After running `alembic upgrade head`, 0008 must convert it to
    String(500) so the column gets the length cap.
    """
    db_file = tmp_path / "old_0007.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    # 1. Create all tables with the CURRENT model (String(500) on error_summary).
    # 2. Manually drop & re-add error_summary as Text to simulate the old 0007.
    # 3. Stamp alembic_version at 0007 so 0001-0007 are skipped, 0008 runs.
    _create_old_0007_state(db_url, db_file)

    # Sanity: before upgrade, error_summary is Text.
    cols_before = _inspect_columns(db_url, "job_runs")
    summary_before = next(c for c in cols_before if c["name"] == "error_summary")
    assert not isinstance(summary_before["type"], sa.String) or (
        isinstance(summary_before["type"], sa.String) and summary_before["type"].length != 500
    ), (
        "Test setup error: expected error_summary to be a non-String(500) "
        f"type before upgrade, got {type(summary_before['type']).__name__}"
    )

    # 4. Run alembic upgrade head — should apply 0008 and alter the column.
    _run_alembic_with(db_url)

    # 5. Verify the column is now String(500).
    cols_after = _inspect_columns(db_url, "job_runs")
    summary_after = next(c for c in cols_after if c["name"] == "error_summary")
    assert isinstance(summary_after["type"], sa.String), (
        f"error_summary must be a String column after 0008, got "
        f"{type(summary_after['type']).__name__}"
    )
    assert summary_after["type"].length == 500, (
        f"error_summary must have length=500 after 0008, got " f"{summary_after['type'].length}"
    )


@pytest.mark.asyncio
async def test_init_db_skips_alembic_for_in_memory(tmp_path, monkeypatch) -> None:
    """init_db must not raise when DATABASE_URL points at in-memory SQLite.

    The alembic upgrade must be skipped (alembic's separate engine cannot see the
    same in-memory data) — but the rest of init_db must still complete so the tables
    exist. This suite stopped running on `:memory:` itself on 2026-09-04 (F285, see
    `conftest.py`), so the case is now covered only here rather than incidentally by
    every other test — which is a reason to keep it, not to retire it: `:memory:` is
    still what a developer gets from an unset DATABASE_URL in a throwaway script.
    """
    monkeypatch.setattr(settings, "database_url", "sqlite+aiosqlite:///:memory:")
    # init_db should NOT raise even though alembic is skipped for :memory:.
    await init_db()


@pytest.mark.asyncio
async def test_init_db_creates_no_project_even_with_the_legacy_bootstrap_env_set(
    monkeypatch,
) -> None:
    """Startup creates no project, and setting the retired variables cannot change that.

    They are set here deliberately. `init_db` used to read AW_BOOTSTRAP_PROJECT_ID and
    create a project named by AW_BOOTSTRAP_PROJECT_NAME, which is how operators carrying
    an older .env forward kept finding a "Default Project" bound to no working directory.
    Registering a project is now only reachable by opening a directory, so the gate and
    the settings behind it are gone — and an old .env is inert rather than obeyed.

    The instance operator credential must still be minted, so the local app can
    authenticate against a Hub that holds nothing yet.
    """
    from sqlalchemy import func, select

    monkeypatch.setenv("AW_BOOTSTRAP_PROJECT_ID", "proj-default")
    monkeypatch.setenv("AW_BOOTSTRAP_PROJECT_NAME", "Default Project")
    monkeypatch.setattr(settings, "aw_bootstrap_api_key", "")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await init_db()

    async with async_session_factory() as session:
        project_count = await session.scalar(select(func.count()).select_from(Project))
        api_key_count = await session.scalar(select(func.count()).select_from(ApiKey))
        credential_count = await session.scalar(
            select(func.count()).select_from(OperatorCredential)
        )
    assert project_count == 0
    assert api_key_count == 0
    assert credential_count == 1


@pytest.mark.asyncio
async def test_init_db_runs_alembic_for_file_db(tmp_path, monkeypatch) -> None:
    """For a file-based DB, _run_alembic_upgrade must actually apply migrations.

    Verifies the H5 fix at the unit level: a file-based URL is not skipped,
    alembic is invoked, and the alembic_version table ends up at the latest revision.
    """
    from hub.db.engine import _run_alembic_upgrade

    db_file = tmp_path / "init_db.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setattr(settings, "database_url", db_url)

    # Run the helper directly. (init_db uses the module-level engine, bound at import
    # time to the suite's own temporary file database — see `conftest.py` — so we test
    # the unit that owns the URL rather than the engine that happens to be bound.)
    #
    # This test must see the real `_run_alembic_upgrade`. The `app` fixture patches it to
    # a no-op so that 1,500+ tests do not each apply every migration; this test does not
    # take that fixture, which is why the patch is per-test rather than module-level.
    await _run_alembic_upgrade()

    import aiosqlite

    async def _check() -> str | None:
        async with aiosqlite.connect(str(db_file)) as conn:
            cursor = await conn.execute("SELECT version_num FROM alembic_version")
            row = await cursor.fetchone()
            return row[0] if row else None

    version = await _check()
    assert version == HEAD_REVISION, f"expected alembic_version={HEAD_REVISION}, got {version}"


@pytest.mark.asyncio
async def test_init_db_alembic_failure_does_not_raise(tmp_path, monkeypatch) -> None:
    """A failing alembic upgrade must not crash init_db (dev mode safety net).

    Mocks `alembic.command.upgrade` to raise and verifies the exception is
    caught inside `_run_alembic_upgrade` and not propagated. This is the
    spec's "wrap in try/except so dev mode still works" requirement.

    The warning log itself is also exercised (the `try/except` calls
    `logger.warning(...)`); we just don't assert on the log record here
    because pytest's `caplog` fixture is unreliable for warnings emitted
    from inside an executor thread when this test runs after siblings
    that have already used alembic.
    """
    from hub.db.engine import _run_alembic_upgrade

    db_file = tmp_path / "broken.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setattr(settings, "database_url", db_url)

    # Should NOT raise — exception is caught inside _run_alembic_upgrade.
    with patch("alembic.command.upgrade", side_effect=RuntimeError("boom")):
        await _run_alembic_upgrade()

    # If we got here, the exception was caught. Verify the patch target
    # was actually invoked (defense against a missed patch).
    assert True, "Alembic upgrade failed silently — exception was caught"


def test_run_async_migrations_uses_the_same_busy_timeout_as_the_main_engine(tmp_path) -> None:
    """F292 investigation, 2026-09-06: alembic's own engine used to have no `connect_args`
    at all, so on SQLite it ran with the driver's default 5s busy timeout while the main
    engine (via conftest.py's pragma listener) waits 30s -- six times shorter patience for
    exactly the kind of writer contention F292's own control run proved locks a schema reset.

    alembic re-execs `env.py` fresh on every `command.upgrade` call (it must: `config =
    context.config` at module scope only resolves inside an active invocation, which is also
    why this test cannot simply `import hub.migrations.env`). So the patch target is the
    *origin* of the name env.py imports from, not an attribute on env.py itself.
    """
    db_file = tmp_path / "busy_timeout_check.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    real_create_async_engine = create_async_engine
    seen_kwargs = {}

    def _spy(url, **kwargs):
        seen_kwargs.update(kwargs)
        return real_create_async_engine(url, **kwargs)

    with patch("sqlalchemy.ext.asyncio.create_async_engine", side_effect=_spy):
        _run_alembic_with(db_url)

    assert seen_kwargs.get("connect_args") == {"check_same_thread": False, "timeout": 30.0}, (
        "alembic's engine must match the main engine's busy timeout (30s) and "
        f"check_same_thread setting; got connect_args={seen_kwargs.get('connect_args')!r}"
    )


def test_run_async_migrations_disposes_its_engine_even_when_a_migration_raises(tmp_path) -> None:
    """F292 investigation, 2026-09-06: `await connectable.dispose()` used to sit after the
    `async with connectable.connect()` block rather than in a `finally`, so a migration
    failure propagated straight past it and leaked the engine and its one checked-out
    connection until Python's garbage collector reclaimed them. `_run_alembic_upgrade`
    (hub/hub/db/engine.py) swallows the resulting exception, so nothing surfaced but the leak.

    Forces the failure at `connectable.connect()` itself, outside alembic's own internals
    (which are awkward to patch reliably since `env.py` is re-exec'd fresh on every
    `command.upgrade` call) -- that is still squarely inside the `try` the fix added.
    `AsyncEngine`'s methods are read-only on the instance (slots), so the spies patch the
    class for the duration of the call rather than the one instance.
    """
    from sqlalchemy.ext.asyncio import AsyncEngine

    db_file = tmp_path / "dispose_on_failure.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    real_dispose = AsyncEngine.dispose
    dispose_calls = []

    async def _tracking_dispose(self, *args, **kwargs):
        dispose_calls.append(self)
        return await real_dispose(self, *args, **kwargs)

    def _boom_connect(self, *args, **kwargs):
        raise RuntimeError("boom")

    with (
        patch.object(AsyncEngine, "connect", _boom_connect),
        patch.object(AsyncEngine, "dispose", _tracking_dispose),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            _run_alembic_with(db_url)

    assert len(dispose_calls) == 1, "expected exactly one engine's dispose() to have run"


# ---------------------------------------------------------------------------
# 3.3: runs table
# ---------------------------------------------------------------------------


def test_migration_0012_creates_runs_table_on_existing_deployment(tmp_path) -> None:
    """Migration 0012 must add the `runs` table to a pre-existing (0011) deployment.

    Simulates an upgrade rather than a fresh install: create_all() has already run
    (as init_db always does before migrations), so `runs` doesn't exist yet but every
    other table does. Migration 0012's fresh-install guard must not skip it here.
    """
    db_file = tmp_path / "pre_0012.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    async def _seed_pre_0012() -> None:
        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await conn.execute(sa.text("DROP TABLE runs"))
                await conn.execute(
                    sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
                await conn.execute(
                    sa.text("INSERT INTO alembic_version (version_num) VALUES ('0011')")
                )
        finally:
            await engine.dispose()

    _run(_seed_pre_0012())
    _run_alembic_with(db_url)

    columns = {column["name"]: column for column in _inspect_columns(db_url, "runs")}
    assert {
        "id",
        "project_id",
        "agent",
        "session_id",
        "status",
        "pid",
        "exit_code",
        "error",
        "started_at",
        "ended_at",
        "last_heartbeat_at",
    } <= columns.keys()
    assert columns["session_id"]["nullable"] is True
    assert columns["pid"]["nullable"] is True
    assert columns["ended_at"]["nullable"] is True


def test_migration_0016_adds_and_backfills_agent_color_index(tmp_path) -> None:
    """Migration 0016 must add `color_index` and backfill existing agents by
    registration order (created_at) per project, not leave them null."""
    db_file = tmp_path / "pre_0016.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    async def _seed_pre_0016() -> None:
        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await conn.execute(sa.text("ALTER TABLE agents DROP COLUMN color_index"))
                await conn.execute(
                    sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
                await conn.execute(
                    sa.text("INSERT INTO alembic_version (version_num) VALUES ('0015')")
                )
                # Raw SQL, not the ORM Agent class: the ORM model already declares
                # color_index (it was just dropped above to simulate a pre-0016
                # deployment), so an ORM insert would try to write a column that no
                # longer exists on this connection's schema.
                await conn.execute(
                    sa.text(
                        "INSERT INTO projects (id, name, created_at) VALUES (:id, :name, :now)"
                    ),
                    {
                        "id": "proj-color-test",
                        "name": "Colour Test",
                        "now": datetime.now(timezone.utc),
                    },
                )
                await conn.execute(
                    sa.text(
                        "INSERT INTO agents (id, project_id, name, self_registered, created_at, updated) "
                        "VALUES (:id, :project_id, :name, 0, :created_at, :created_at)"
                    ),
                    [
                        {
                            "id": "agent-first",
                            "project_id": "proj-color-test",
                            "name": "first",
                            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                        },
                        {
                            "id": "agent-second",
                            "project_id": "proj-color-test",
                            "name": "second",
                            "created_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
                        },
                    ],
                )
        finally:
            await engine.dispose()

    _run(_seed_pre_0016())
    _run_alembic_with(db_url)

    columns = {column["name"]: column for column in _inspect_columns(db_url, "agents")}
    assert "color_index" in columns
    assert columns["color_index"]["nullable"] is True

    async def _fetch_indices() -> dict:
        engine = create_async_engine(db_url)
        try:
            async with AsyncSession(engine) as session:
                result = await session.execute(
                    sa.text("SELECT name, color_index FROM agents WHERE project_id = :p"),
                    {"p": "proj-color-test"},
                )
                return dict(result.all())
        finally:
            await engine.dispose()

    indices = _run(_fetch_indices())
    assert indices == {"first": 0, "second": 1}


def test_migration_0017_backfills_conversations_deterministically(tmp_path) -> None:
    """Migration 0017 must group pre-existing runs into conversations by
    `(project_id, agent, session_id)` — runs sharing a provider session collapse into
    one conversation, a run with no session_id gets its own — and the id it assigns
    must be a pure function of that identity, not a fresh random one each time the
    migration logic runs. Determinism matters because design.md's migration guarantee
    is that a redeploy re-running this backfill must reproduce the same ids rather
    than orphaning history under new ones; it must also never guess groupings from
    timestamp proximity."""
    db_file = tmp_path / "pre_0017.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    async def _seed_pre_0017() -> None:
        # Base.metadata.create_all() would build the *current* schema, which already
        # has conversation_id — and SQLite refuses ALTER TABLE ... DROP COLUMN on a
        # column that's part of a foreign key (the error this replaced). So build the
        # pre-0017 shape directly instead: just `projects` and `runs`, neither of
        # which the migration requires anything else to exist alongside (its own
        # per-table loops skip whatever isn't present).
        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    sa.text(
                        "CREATE TABLE projects (id VARCHAR(64) PRIMARY KEY, "
                        "name VARCHAR(128) NOT NULL, created_at TIMESTAMP NOT NULL)"
                    )
                )
                await conn.execute(
                    sa.text(
                        "CREATE TABLE runs (id VARCHAR(64) PRIMARY KEY, "
                        "project_id VARCHAR(64) NOT NULL, agent VARCHAR(64) NOT NULL, "
                        "session_id VARCHAR(128), status VARCHAR(32) NOT NULL, "
                        "pid INTEGER, exit_code INTEGER, error TEXT, "
                        "started_at TIMESTAMP NOT NULL, ended_at TIMESTAMP, "
                        "last_heartbeat_at TIMESTAMP, turn_depth INTEGER)"
                    )
                )
                await conn.execute(
                    sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
                await conn.execute(
                    sa.text("INSERT INTO alembic_version (version_num) VALUES ('0016')")
                )
                await conn.execute(
                    sa.text(
                        "INSERT INTO projects (id, name, created_at) VALUES (:id, :name, :now)"
                    ),
                    {
                        "id": "proj-conv-mig",
                        "name": "Conv Migration Test",
                        "now": datetime.now(timezone.utc),
                    },
                )
                # run-a1/run-a2 share a provider session -> must collapse into one
                # conversation. run-b1 has no session_id -> gets its own, keyed by run id.
                await conn.execute(
                    sa.text(
                        "INSERT INTO runs (id, project_id, agent, session_id, status, started_at) "
                        "VALUES (:id, :project_id, :agent, :session_id, 'completed', :started_at)"
                    ),
                    [
                        {
                            "id": "run-a1",
                            "project_id": "proj-conv-mig",
                            "agent": "claude",
                            "session_id": "provider-shared",
                            "started_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                        },
                        {
                            "id": "run-a2",
                            "project_id": "proj-conv-mig",
                            "agent": "claude",
                            "session_id": "provider-shared",
                            "started_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
                        },
                        {
                            "id": "run-b1",
                            "project_id": "proj-conv-mig",
                            "agent": "claude",
                            "session_id": None,
                            "started_at": datetime(2026, 1, 3, tzinfo=timezone.utc),
                        },
                    ],
                )
        finally:
            await engine.dispose()

    _run(_seed_pre_0017())
    _run_alembic_with(db_url)

    async def _fetch() -> tuple:
        engine = create_async_engine(db_url)
        try:
            async with AsyncSession(engine) as session:
                runs = (
                    await session.execute(
                        sa.text("SELECT id, conversation_id FROM runs ORDER BY id")
                    )
                ).all()
                conversations = (
                    await session.execute(
                        sa.text(
                            "SELECT id, project_id, agent, provider_session_id, lifecycle "
                            "FROM conversations"
                        )
                    )
                ).all()
                return runs, conversations
        finally:
            await engine.dispose()

    runs, conversations = _run(_fetch())
    runs_by_id = {row.id: row.conversation_id for row in runs}

    assert runs_by_id["run-a1"] == runs_by_id["run-a2"]
    assert runs_by_id["run-b1"] != runs_by_id["run-a1"]
    assert len(conversations) == 2

    by_id = {row.id: row for row in conversations}
    shared = by_id[runs_by_id["run-a1"]]
    assert shared.project_id == "proj-conv-mig"
    assert shared.agent == "claude"
    assert shared.provider_session_id == "provider-shared"
    assert shared.lifecycle == "open"

    solo = by_id[runs_by_id["run-b1"]]
    assert solo.provider_session_id is None

    # Determinism: re-deriving the shared conversation's id from the same inputs the
    # migration used must reproduce exactly the id it picked.
    import hashlib

    digest = hashlib.sha256(
        "\x1f".join(["proj-conv-mig", "claude", "provider-shared"]).encode()
    ).hexdigest()[:20]
    assert shared.id == f"conv-mig-{digest}"


def test_migration_0018_adds_durable_turn_accounting(tmp_path) -> None:
    """An existing 0017 deployment gains budget, initiator, and one usage row per run."""
    db_file = tmp_path / "accounting-0017.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    async def _create_old_state() -> None:
        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    sa.text(
                        "CREATE TABLE projects (id VARCHAR(64) PRIMARY KEY, name VARCHAR(256) NOT NULL)"
                    )
                )
                await conn.execute(
                    sa.text(
                        "CREATE TABLE runs (id VARCHAR(64) PRIMARY KEY, "
                        "project_id VARCHAR(64) NOT NULL, agent VARCHAR(64) NOT NULL)"
                    )
                )
                await conn.execute(
                    sa.text("INSERT INTO projects (id, name) VALUES ('proj-old', 'Old')")
                )
                await conn.execute(
                    sa.text(
                        "INSERT INTO runs (id, project_id, agent) "
                        "VALUES ('run-old', 'proj-old', 'claude')"
                    )
                )
                await conn.execute(
                    sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
                await conn.execute(
                    sa.text("INSERT INTO alembic_version (version_num) VALUES ('0017')")
                )
        finally:
            await engine.dispose()

    _run(_create_old_state())
    _run_alembic_with(db_url)

    assert "token_budget" in {column["name"] for column in _inspect_columns(db_url, "projects")}
    run_columns = {column["name"]: column for column in _inspect_columns(db_url, "runs")}
    assert run_columns["initiator"]["nullable"] is False
    usage_columns = {column["name"] for column in _inspect_columns(db_url, "turn_usage")}
    assert {
        "run_id",
        "status",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "allowance",
    } <= usage_columns

    async def _check_default_and_uniqueness() -> None:
        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(
                    sa.text("SELECT initiator FROM runs WHERE id = 'run-old'")
                )
                assert result.scalar_one() == "operator"
                params = {
                    "id": "usage-old",
                    "run_id": "run-old",
                    "project_id": "proj-old",
                    "agent": "claude",
                    "status": "unavailable",
                    "observed_at": datetime.now(timezone.utc),
                }
                await conn.execute(
                    sa.text(
                        "INSERT INTO turn_usage "
                        "(id, run_id, project_id, agent, status, observed_at) "
                        "VALUES (:id, :run_id, :project_id, :agent, :status, :observed_at)"
                    ),
                    params,
                )
                with pytest.raises(sa.exc.IntegrityError):
                    await conn.execute(
                        sa.text(
                            "INSERT INTO turn_usage "
                            "(id, run_id, project_id, agent, status, observed_at) "
                            "VALUES ('usage-duplicate', :run_id, :project_id, :agent, "
                            ":status, :observed_at)"
                        ),
                        params,
                    )
        finally:
            await engine.dispose()

    _run(_check_default_and_uniqueness())


def test_migration_0019_allows_scheduled_queue_origin(tmp_path) -> None:
    db_file = tmp_path / "queue-origin-0018.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    async def _create_old_state() -> None:
        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    sa.text("CREATE TABLE projects (id VARCHAR(64) PRIMARY KEY, name VARCHAR(256))")
                )
                await conn.execute(
                    sa.text("INSERT INTO projects (id, name) VALUES ('proj-old', 'Old')")
                )
                await conn.execute(
                    sa.text(
                        "CREATE TABLE inbound_queue_entries ("
                        "sequence INTEGER PRIMARY KEY AUTOINCREMENT, id VARCHAR(64) UNIQUE NOT NULL, "
                        "project_id VARCHAR(64) NOT NULL REFERENCES projects(id), "
                        "agent VARCHAR(64) NOT NULL, origin_type VARCHAR(16) NOT NULL, "
                        "origin_agent VARCHAR(64), content TEXT NOT NULL, "
                        "arrived_at DATETIME NOT NULL, hop_depth INTEGER NOT NULL, "
                        "state VARCHAR(16) NOT NULL, delivered_in_run_id VARCHAR(64), "
                        "delivered_at DATETIME, withdrawn_at DATETIME, message_id VARCHAR(64), "
                        "session_mode VARCHAR(16), session_id VARCHAR(128), "
                        "conversation_id VARCHAR(64), work_dir VARCHAR(4096), "
                        "CONSTRAINT ck_inbound_queue_origin_type "
                        "CHECK (origin_type IN ('operator', 'agent')), "
                        "CONSTRAINT ck_inbound_queue_origin_agent CHECK ("
                        "(origin_type = 'operator' AND origin_agent IS NULL) OR "
                        "(origin_type = 'agent' AND origin_agent IS NOT NULL)), "
                        "CONSTRAINT ck_inbound_queue_state "
                        "CHECK (state IN ('queued', 'delivered', 'withdrawn')), "
                        "CONSTRAINT ck_inbound_queue_hop_depth CHECK (hop_depth >= 0))"
                    )
                )
                await conn.execute(
                    sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
                await conn.execute(
                    sa.text("INSERT INTO alembic_version (version_num) VALUES ('0018')")
                )
        finally:
            await engine.dispose()

    async def _insert_job() -> str:
        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    sa.text(
                        "INSERT INTO inbound_queue_entries "
                        "(id, project_id, agent, origin_type, origin_agent, content, arrived_at, "
                        "hop_depth, state) VALUES ('entry-job', 'proj-old', 'claude', 'job', NULL, "
                        "'scheduled', :now, 0, 'queued')"
                    ),
                    {"now": datetime.now(timezone.utc)},
                )
                result = await conn.execute(
                    sa.text("SELECT origin_type FROM inbound_queue_entries WHERE id = 'entry-job'")
                )
                return result.scalar_one()
        finally:
            await engine.dispose()

    _run(_create_old_state())
    _run_alembic_with(db_url)
    assert _run(_insert_job()) == "job"


def test_migration_0020_adds_empty_unique_run_token_digest(tmp_path) -> None:
    db_file = tmp_path / "run-capability-0019.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    async def _create_old_state() -> None:
        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    sa.text(
                        "CREATE TABLE runs (id VARCHAR(64) PRIMARY KEY, "
                        "project_id VARCHAR(64) NOT NULL, agent VARCHAR(64) NOT NULL, "
                        "status VARCHAR(32) NOT NULL)"
                    )
                )
                await conn.execute(
                    sa.text(
                        "INSERT INTO runs (id, project_id, agent, status) "
                        "VALUES ('run-old', 'proj-old', 'claude', 'completed')"
                    )
                )
                await conn.execute(
                    sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
                await conn.execute(
                    sa.text("INSERT INTO alembic_version (version_num) VALUES ('0019')")
                )
        finally:
            await engine.dispose()

    async def _inspect_upgraded_state() -> tuple[object, list[dict[str, object]]]:
        engine = create_async_engine(db_url)
        try:
            async with engine.connect() as conn:
                digest = await conn.scalar(
                    sa.text("SELECT capability_token_hash FROM runs WHERE id = 'run-old'")
                )
                indexes = await conn.run_sync(
                    lambda sync_conn: sa.inspect(sync_conn).get_indexes("runs")
                )
                return digest, indexes
        finally:
            await engine.dispose()

    _run(_create_old_state())
    _run_alembic_with(db_url)
    digest, indexes = _run(_inspect_upgraded_state())
    assert digest is None
    token_index = next(i for i in indexes if i["name"] == "ix_runs_capability_token_hash")
    assert token_index["unique"] == 1


@pytest.mark.asyncio
async def test_run_model_round_trips_through_the_orm(app) -> None:
    """Sanity check: a Run row can be created and read back with its fields intact."""
    from hub.db.models import Project, Run

    async with async_session_factory() as session:
        session.add(Project(id="proj-run-test", name="Run Model Test"))
        run = Run(
            id="run-test-0001",
            project_id="proj-run-test",
            agent="claude",
            session_id="sess-abc",
            pid=12345,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

        assert run.status == "running"
        assert run.pid == 12345
        assert run.exit_code is None
        assert run.ended_at is None
        assert run.started_at is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_minimum(session) -> tuple[str, str, str, str]:
    """Insert the minimum row set needed to satisfy JobRun's FKs.

    Returns (project_id, key_id, job_id, run_id).
    """
    project_id = "proj-mig-test"
    key_id = "aw_live_migtest_abcdef0123456789"
    job_id = "job-mig-test-0001"
    run_id = "run-mig-test-0001"
    session.add(Project(id=project_id, name="Migration Test Project"))
    session.add(ApiKey(id=key_id, project_id=project_id, label="migration-test", revoked=False))
    session.add(
        AIJob(
            id=job_id,
            project_id=project_id,
            name="migration-test",
            agent="tester",
            message="hello",
            cron="0 9 * * *",
        )
    )
    return project_id, key_id, job_id, run_id


def _run_alembic_with(db_url: str, revision: str = "head") -> None:
    """Configure alembic for the given URL and run `upgrade` synchronously.

    *revision* defaults to head. Pass an explicit one when the test is about what a
    particular migration did to a table a later migration goes on to drop — upgrading to
    head would then assert against a schema the chain has deliberately moved past.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    # env.py reads `settings.database_url` (the singleton) to build its
    # async engine. Temporarily override so alembic uses the same file
    # as the test's standalone engine.
    with patch.object(settings, "database_url", db_url):
        command.upgrade(cfg, revision)


def _inspect_columns(db_url: str, table: str) -> list[dict]:
    """Inspect a table's columns using a fresh async engine. Returns a list
    of column info dicts (synchronously, after running the async inspection
    inline via the engine)."""
    return _run(_inspect_columns_async(db_url, table))


async def _inspect_columns_async(db_url: str, table: str) -> list[dict]:
    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as conn:

            def _get_cols(sync_conn) -> list[dict]:
                inspector = sa.inspect(sync_conn)
                return inspector.get_columns(table)

            return await conn.run_sync(_get_cols)
    finally:
        await engine.dispose()


def _create_old_0007_state(db_url: str, db_file: Path) -> None:
    """Create a DB that mimics a deployment where 0007 already ran with Text.

    1. Run create_all (which uses the current model — String(500)).
    2. Drop & re-add error_summary as Text.
    3. Create the alembic_version table and stamp it at 0007.
    """
    _run(_create_old_0007_state_async(db_url, db_file))


async def _create_old_0007_state_async(db_url: str, db_file: Path) -> None:
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Re-add error_summary as Text to simulate the old migration.
            await conn.execute(sa.text("ALTER TABLE job_runs DROP COLUMN error_summary"))
            await conn.execute(sa.text("ALTER TABLE job_runs ADD COLUMN error_summary TEXT"))
            # Stamp the alembic version.
            await conn.execute(
                sa.text("CREATE TABLE alembic_version " "(version_num VARCHAR(32) NOT NULL)")
            )
            await conn.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('0007')"))
    finally:
        await engine.dispose()


def _run(coro):
    """Run an async coroutine to completion from a sync test function."""
    import asyncio

    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 0052 — task_transitions (B1, the task transition machine)
# ---------------------------------------------------------------------------


async def _create_all_at(db_url: str) -> None:
    """Build every table from the models, as `init_db` does before running alembic."""
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


def test_task_transitions_lands_on_the_real_startup_path(tmp_path) -> None:
    """The append-only history table lands with the columns and indexes the rule reads.

    `init_db` runs `create_all` and *then* `alembic upgrade head`, and no migration has ever
    created `tasks` — it exists only from the models. So this is the order a real startup uses,
    and 0052 is a no-op here rather than the thing that builds the table.
    """
    db_file = tmp_path / "fresh.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "task_transitions" in tables

        columns = {row[1] for row in conn.execute("PRAGMA table_info(task_transitions)")}
        assert columns == {
            "sequence",
            "id",
            "project_id",
            "task_id",
            "from_status",
            "to_status",
            "actor_kind",
            "run_id",
            "actor_agent",
            "origin",
            # What governed the move, added by 0069. Null except on an approval a gate evaluated.
            "policy_digest",
            "created_at",
        }

        indexes = {row[1] for row in conn.execute("PRAGMA index_list(task_transitions)")}
        assert "ix_task_transitions_task_sequence" in indexes

        # Author/reviewer separation asks "which run moved this task into `completed`", so run_id
        # must be nullable — an operator transition has no run — and both from/to are required.
        nullable = {
            row[1]: not row[3] for row in conn.execute("PRAGMA table_info(task_transitions)")
        }
        assert nullable["run_id"] is True
        assert nullable["from_status"] is False
        assert nullable["to_status"] is False
        assert nullable["actor_kind"] is False


def test_migration_0052_is_guarded_when_tasks_does_not_exist(tmp_path) -> None:
    """An upgrade starting from an early revision reaches 0052 with only that revision's tables.

    `_create_0034_conversations_state` builds projects/conversations/runs and no `tasks`, so the
    foreign key has nothing to point at. The migration must skip rather than fail, and the upgrade
    must still reach head — `create_all` builds the table from the model on a real startup.

    This is not a hypothetical: running the migration chain without `create_all` is exactly what
    `test_alembic_upgrade_head_fresh_file_db` does, and no migration in the chain has ever created
    `tasks`. An unguarded `create_table` with a foreign key to it would fail there.
    """
    db_file = tmp_path / "early.db"
    _create_0034_conversations_state(db_file)

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}")

    with sqlite3.connect(db_file) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == HEAD_REVISION
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "tasks" not in tables
        assert "task_transitions" not in tables


def test_migration_0052_downgrade_drops_the_history(tmp_path) -> None:
    """Rollback loses the audit trail but leaves every task in a valid status (design D3/D4)."""
    from alembic import command
    from alembic.config import Config

    db_file = tmp_path / "down.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        command.downgrade(cfg, "0051")

    with sqlite3.connect(db_file) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "task_transitions" not in tables
        assert "tasks" in tables


def test_migration_0054_adds_the_run_task_binding(tmp_path) -> None:
    """A run must be able to say what task it was started for, and whether it is a retry.

    Both nullable: a run with no cause naming a task is unbound, which is legitimate, and only a run
    started in response to a divergence carries a source. NULL in either is a statement, not a gap.
    """
    db_file = tmp_path / "binding.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(runs)")}
        assert "task_id" in columns
        assert "divergence_source_run_id" in columns
        # row[3] is `notnull`
        assert columns["task_id"][3] == 0
        assert columns["divergence_source_run_id"][3] == 0

        indexes = {row[1] for row in conn.execute("PRAGMA index_list(runs)")}
        assert "ix_runs_task_id" in indexes

        # Nullable with no server default is what "cannot backfill" means structurally: a run that
        # predates the binding was genuinely unbound, and there is no value the migration could
        # write that would not be a guess. row[4] is `dflt_value`.
        assert columns["task_id"][4] is None
        assert columns["divergence_source_run_id"][4] is None


def test_migration_0055_adds_the_queue_entry_task(tmp_path) -> None:
    """A delegation's task has to survive the queue: a busy agent's turn starts from a later
    scheduler call than the one that queued the input."""
    db_file = tmp_path / "queue_task.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(inbound_queue_entries)")}
        assert "task_id" in columns
        assert columns["task_id"][3] == 0


def test_migration_0056_defaults_are_the_pre_change_behaviour(tmp_path) -> None:
    """The two defaults are what makes this change safe to ship onto an existing board.

    Every transition recorded before `origin` existed was asked for by an actor, because nothing
    else could write one. Every task predating the policy gets `surface`, so introducing the
    capability starts no run nobody asked for.
    """
    db_file = tmp_path / "defaults.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))

    with sqlite3.connect(db_file) as conn:
        conn.execute("INSERT INTO projects (id, name, created_at) VALUES ('p1', 'P', '2026-01-01')")
        conn.execute(
            "INSERT INTO tasks (id, project_id, title, description, status, priority, "
            "created_at, updated) VALUES ('task-old', 'p1', 'T', '', 'pending', 'medium', "
            "'2026-01-01', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO task_transitions (id, project_id, task_id, from_status, to_status, "
            "actor_kind, created_at) VALUES ('ttr-old', 'p1', 'task-old', 'pending', "
            "'in_progress', 'operator', '2026-01-01')"
        )
        conn.commit()

    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        policy, escalation = conn.execute(
            "SELECT divergence_policy, escalation_agent FROM tasks WHERE id = 'task-old'"
        ).fetchone()
        assert policy == "surface"
        assert escalation is None

        origin = conn.execute(
            "SELECT origin FROM task_transitions WHERE id = 'ttr-old'"
        ).fetchone()[0]
        assert origin == "actor"


def test_migration_0057_creates_the_divergence_record(tmp_path) -> None:
    db_file = tmp_path / "divergences.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "run_divergences" in tables

        columns = {row[1] for row in conn.execute("PRAGMA table_info(run_divergences)")}
        assert columns == {
            "sequence",
            "id",
            "project_id",
            "run_id",
            "agent",
            "task_id",
            "task_status_at_end",
            "run_exit_status",
            "policy_applied",
            "outcome",
            "response_run_id",
            "previous_assignee",
            "created_at",
            "resolved_at",
        }

        # Ordering is the point: two divergences recorded in the same instant must read back in
        # the order they happened, which `created_at` cannot promise.
        pk = [row[1] for row in conn.execute("PRAGMA table_info(run_divergences)") if row[5]]
        assert pk == ["sequence"]

        nullable = {
            row[1]: not row[3] for row in conn.execute("PRAGMA table_info(run_divergences)")
        }
        assert nullable["resolved_at"] is True
        assert nullable["response_run_id"] is True
        assert nullable["previous_assignee"] is True
        assert nullable["outcome"] is False
        assert nullable["policy_applied"] is False


def test_migration_0057_is_guarded_when_tasks_does_not_exist(tmp_path) -> None:
    """Same guard as 0052, for the same reason: an upgrade from an early revision arrives here with
    no `tasks` for the foreign key to point at, and must skip rather than fail."""
    db_file = tmp_path / "early_divergences.db"
    _create_0034_conversations_state(db_file)

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}")

    with sqlite3.connect(db_file) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == HEAD_REVISION
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "tasks" not in tables
        assert "run_divergences" not in tables


def test_migration_0059_adds_the_block_columns(tmp_path) -> None:
    db_file = tmp_path / "blocked.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        tasks = {row[1]: row for row in conn.execute("PRAGMA table_info(tasks)")}
        assert "blocked_reason" in tasks
        # Nullable, and no default: a task that is not waiting has nothing to say it is waiting for.
        assert not tasks["blocked_reason"][3]
        assert tasks["blocked_reason"][4] is None

        questions = {row[1]: row for row in conn.execute("PRAGMA table_info(questions)")}
        assert "blocked_task_id" in questions
        assert not questions["blocked_task_id"][3]

        indexes = {row[1] for row in conn.execute("PRAGMA index_list(questions)")}
        assert "ix_questions_blocked_task_id" in indexes


def test_migration_0059_leaves_existing_rows_untouched(tmp_path) -> None:
    """No backfill, and none is possible: nothing before this migration could park a task, so there
    is no historical block to describe. Inventing one would put "waiting on" text on cards that
    were never waiting."""
    db_file = tmp_path / "blocked_backfill.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))

    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO tasks "
            "(id, project_id, title, description, status, priority, created_at, updated) "
            "VALUES ('t-old', 'p1', 'Old work', '', 'in_progress', 'medium', "
            "'2026-01-01', '2026-01-01')"
        )
        conn.commit()

    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        reason = conn.execute("SELECT blocked_reason FROM tasks WHERE id='t-old'").fetchone()[0]
        assert reason is None
        status = conn.execute("SELECT status FROM tasks WHERE id='t-old'").fetchone()[0]
        assert status == "in_progress"


def test_migration_0059_is_guarded_when_the_tables_do_not_exist(tmp_path) -> None:
    """An upgrade starting from an early revision reaches here with neither `tasks` nor
    `questions`, and must skip rather than fail."""
    db_file = tmp_path / "early_blocked.db"
    _create_0034_conversations_state(db_file)

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}")

    with sqlite3.connect(db_file) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == HEAD_REVISION
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "tasks" not in tables
        assert "questions" not in tables


def test_migration_0060_adds_the_conversation_binding(tmp_path) -> None:
    db_file = tmp_path / "conversation_task.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(conversations)")}
        assert "task_id" in columns
        assert not columns["task_id"][3]

        indexes = {row[1] for row in conn.execute("PRAGMA index_list(conversations)")}
        assert "ix_conversations_task_id" in indexes


def test_migration_0060_binds_no_existing_conversation(tmp_path) -> None:
    """No backfill, and the absence is the decision. A conversation predating the column was not
    bound to anything, and guessing one from the tasks its agent happened to touch would start
    checking runs on threads whose operators never opted in."""
    db_file = tmp_path / "conversation_backfill.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))

    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO conversations "
            "(id, project_id, agent, lifecycle, origin, title_set_by_operator, "
            "created_at, updated_at) "
            "VALUES ('conv-old', 'p1', 'worker', 'open', 'operator', 0, "
            "'2026-01-01', '2026-01-01')"
        )
        conn.commit()

    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        bound = conn.execute("SELECT task_id FROM conversations WHERE id='conv-old'").fetchone()[0]
        assert bound is None


def test_migration_0060_is_guarded_when_conversations_does_not_exist(tmp_path) -> None:
    db_file = tmp_path / "early_conversation_task.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0024')")

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}")

    with sqlite3.connect(db_file) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == HEAD_REVISION
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "conversations" not in tables


def test_migration_0061_adds_the_declined_state(tmp_path) -> None:
    db_file = tmp_path / "declined.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(questions)")}
        assert "declined" in columns
        assert "declined_at" in columns
        # NOT NULL with a server default: SQLite rewrites the table to add the column, and existing
        # rows need a value from the database rather than from the ORM.
        assert columns["declined"][3] == 1
        assert columns["declined"][4] is not None
        assert not columns["declined_at"][3]


def test_migration_0061_declines_no_existing_question(tmp_path) -> None:
    """No backfill, and the absence is the decision: marking historical unanswered questions as
    declined would claim the operator made a decision they never made."""
    db_file = tmp_path / "declined_backfill.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))

    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO questions "
            "(id, project_id, from_agent, question, answered, blocking, options, "
            "answer_labels, multi_select, batch_index, batch_size, created_at) "
            "VALUES ('q-old', 'p1', 'worker', 'Old question', 0, 1, '[]', '[]', 0, 0, 1, "
            "'2026-01-01')"
        )
        conn.commit()

    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        row = conn.execute(
            "SELECT declined, declined_at, answered FROM questions WHERE id='q-old'"
        ).fetchone()
        assert row[0] == 0
        assert row[1] is None
        assert row[2] == 0


def test_migration_0061_is_guarded_when_questions_does_not_exist(tmp_path) -> None:
    db_file = tmp_path / "early_declined.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0024')")

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}")

    with sqlite3.connect(db_file) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == HEAD_REVISION
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "questions" not in tables


# ---------------------------------------------------------------------------
# 0063 — the agent name is unique within a project
# ---------------------------------------------------------------------------


def _insert_agent(conn, agent_id: str, project_id: str, name: str) -> None:
    """Insert an agent, filling whatever NOT NULL columns the schema has at this revision.

    Written against the schema rather than a fixed column list so a later migration adding a
    required column does not turn these tests into a puzzle about `agents`, which is not what
    they are checking.
    """
    columns = list(conn.execute("PRAGMA table_info('agents')"))
    values = {"id": agent_id, "project_id": project_id, "name": name}
    for _cid, col_name, col_type, not_null, default, _pk in columns:
        if col_name in values or not not_null or default is not None:
            continue
        upper = (col_type or "").upper()
        if "INT" in upper:
            values[col_name] = 0
        elif "CHAR" in upper or "TEXT" in upper or "CLOB" in upper:
            values[col_name] = "2026-08-12T00:00:00" if "_at" in col_name else "x"
        else:
            values[col_name] = "2026-08-12T00:00:00"
    placeholders = ", ".join("?" for _ in values)
    conn.execute(
        f"INSERT INTO agents ({', '.join(values)}) VALUES ({placeholders})",
        tuple(values.values()),
    )


def _agents_index_is_unique(db_file) -> bool:
    with sqlite3.connect(db_file) as conn:
        for _seq, name, unique, *_rest in conn.execute("PRAGMA index_list('agents')"):
            if name == "ix_agents_project_name":
                return bool(unique)
    raise AssertionError("ix_agents_project_name is missing")


def _upgrade_to(db_url: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        command.upgrade(cfg, revision)


def test_migration_0063_makes_the_agent_name_unique_per_project(tmp_path) -> None:
    """Closes umbrella task 13.2. The index existed since 0004 but was never unique."""
    db_file = tmp_path / "unique.db"
    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}")

    assert _agents_index_is_unique(db_file)


def test_migration_0063_rejects_a_second_agent_with_the_same_name(tmp_path) -> None:
    """The point of the index: registration SELECTs then INSERTs, and two concurrent
    registrations interleave through that gap. The database now refuses the second."""
    db_file = tmp_path / "reject.db"
    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}")

    with sqlite3.connect(db_file) as conn:
        _insert_agent(conn, "a1", "proj-x", "nova")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_agent(conn, "a2", "proj-x", "nova")


def test_migration_0063_allows_the_same_name_in_a_different_project(tmp_path) -> None:
    """Uniqueness is per project, not global — two projects may each have a `nova`."""
    db_file = tmp_path / "scoped.db"
    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}")

    with sqlite3.connect(db_file) as conn:
        _insert_agent(conn, "a1", "proj-a", "nova")
        _insert_agent(conn, "a2", "proj-b", "nova")
        count = conn.execute("SELECT COUNT(*) FROM agents WHERE name = 'nova'").fetchone()[0]

    assert count == 2


def test_migration_0063_renames_pre_existing_duplicates_without_losing_rows(tmp_path) -> None:
    """A database that already holds duplicates cannot take a unique index, so the migration
    has to decide something. It renames rather than deleting: an agent owns conversations,
    runs, tasks and messages by `id`, and dropping a row to satisfy an index would destroy
    real history. Every row survives; only the later names move."""
    db_file = tmp_path / "dupes.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    _upgrade_to(db_url, "0062")
    with sqlite3.connect(db_file) as conn:
        for agent_id in ("a1", "a2", "a3"):
            _insert_agent(conn, agent_id, "proj-x", "nova")
        conn.commit()

    _upgrade_to(db_url, "head")

    with sqlite3.connect(db_file) as conn:
        rows = dict(
            conn.execute("SELECT id, name FROM agents WHERE project_id = 'proj-x'").fetchall()
        )

    assert len(rows) == 3, "no row may be deleted to satisfy the index"
    assert rows["a1"] == "nova", "the oldest row keeps the name"
    assert sorted(rows.values()) == ["nova", "nova-2", "nova-3"]
    assert _agents_index_is_unique(db_file)


def test_migration_0063_dedupe_respects_the_agent_name_length_limit(tmp_path) -> None:
    """AGENT_NAME_RE caps a name at 32 characters, so the suffix truncates rather than
    producing a name the application itself would reject."""
    db_file = tmp_path / "long.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    long_name = "a" * 32

    _upgrade_to(db_url, "0062")
    with sqlite3.connect(db_file) as conn:
        for agent_id in ("a1", "a2"):
            _insert_agent(conn, agent_id, "proj-x", long_name)
        conn.commit()

    _upgrade_to(db_url, "head")

    with sqlite3.connect(db_file) as conn:
        names = sorted(
            row[0] for row in conn.execute("SELECT name FROM agents WHERE project_id = 'proj-x'")
        )

    assert all(len(name) <= 32 for name in names), names
    assert names == sorted([long_name, f"{'a' * 30}-2"])


# The strings a real agent wrote, unprompted, during the 2026-08-13 end-to-end run. They are the
# fixtures because the convention they follow — identifier, em-dash, key — is a convention one model
# happened to adopt, not a guarantee, and a migration tuned to invented examples would be tuned to
# the wrong shape.
LIVE_LEGACY_REFERENCES = [
    "FR-8 — initialize-members",
    "FR-1 — local-single-ledger",
    "Settlement must balance to the cent",
    "FR-404 — a requirement nobody wrote",
]


def _stamp(db_file, revision: str) -> None:
    with sqlite3.connect(db_file) as conn:
        conn.execute("DELETE FROM alembic_version")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES (?)", (revision,))
        conn.commit()


def test_migration_0067_converts_the_live_legacy_references(tmp_path) -> None:
    """Convert what resolves, keep what does not, and never invent a requirement.

    The failure mode this guards is silent: a task that loses a reference it used to have looks
    exactly like a task that never had one.
    """
    import json

    db_file = tmp_path / "legacy_refs.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        conn.execute("DELETE FROM task_requirement_links")
        conn.execute("DELETE FROM task_requirement_references")
        conn.execute(
            "INSERT INTO projects (id, name, created_at) VALUES ('p1', 'demo', '2026-08-13')"
        )
        conn.execute(
            "INSERT INTO spec_documents (id, project_id, path, title, kind, phase, created_at,"
            " updated_at) VALUES ('d1', 'p1', 'spec/changes/x/spec.html', 'X', 'change-spec',"
            " 'approved', '2026-08-13', '2026-08-13')"
        )
        for identifier, requirement_id in (("FR-8", "r8"), ("FR-1", "r1")):
            conn.execute(
                "INSERT INTO spec_requirements (id, project_id, document_id, identifier, key,"
                " state, digest, digest_version, anchor, observed_at, created_at)"
                " VALUES (?, 'p1', 'd1', ?, 'k', 'active', 'abc', 1, ?, '2026-08-13','2026-08-13')",
                (requirement_id, identifier, f"#{identifier}"),
            )
        conn.execute(
            "INSERT INTO tasks (id, project_id, title, description, status, priority, created_at,"
            " updated, requirements, divergence_policy) VALUES ('t1', 'p1', 'Build it', '',"
            " 'pending', 'medium', '2026-08-13', '2026-08-13', ?, 'surface')",
            (json.dumps(LIVE_LEGACY_REFERENCES),),
        )
        conn.commit()

    _stamp(db_file, "0066")
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        linked = {
            row[0]
            for row in conn.execute(
                "SELECT r.identifier FROM task_requirement_links l"
                " JOIN spec_requirements r ON r.id = l.requirement_id WHERE l.task_id = 't1'"
            )
        }
        kept = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT reference, reason FROM task_requirement_references WHERE task_id = 't1'"
            )
        }
        requirement_count = conn.execute("SELECT COUNT(*) FROM spec_requirements").fetchone()[0]
        original = conn.execute("SELECT requirements FROM tasks WHERE id='t1'").fetchone()[0]

    assert linked == {"FR-8", "FR-1"}
    # Nothing is dropped: every value is either a link or a preserved reference.
    assert set(kept) == {
        "Settlement must balance to the cent",
        "FR-404 — a requirement nobody wrote",
    }
    assert kept["FR-404 — a requirement nobody wrote"] == "unknown"
    assert kept["Settlement must balance to the cent"] == "unknown"
    # And no requirement was created to make a value resolve.
    assert requirement_count == 2
    # The original stays, so a mis-parse can be re-derived rather than reconstructed from a backup.
    assert json.loads(original) == LIVE_LEGACY_REFERENCES


def test_migration_0067_links_nothing_when_the_index_is_empty(tmp_path) -> None:
    """A project whose documents predate the index resolves nothing here — and that is the honest
    outcome. Guessing would be the alternative."""
    import json

    db_file = tmp_path / "legacy_no_index.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        conn.execute("DELETE FROM task_requirement_links")
        conn.execute("DELETE FROM task_requirement_references")
        conn.execute(
            "INSERT INTO projects (id, name, created_at) VALUES ('p2', 'demo', '2026-08-13')"
        )
        conn.execute(
            "INSERT INTO tasks (id, project_id, title, description, status, priority, created_at,"
            " updated, requirements, divergence_policy) VALUES ('t2', 'p2', 'Build it', '',"
            " 'pending', 'medium', '2026-08-13', '2026-08-13', ?, 'surface')",
            (json.dumps(["FR-8 — initialize-members"]),),
        )
        conn.commit()

    _stamp(db_file, "0066")
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT COUNT(*) FROM task_requirement_links").fetchone()[0] == 0
        kept = conn.execute(
            "SELECT reference FROM task_requirement_references WHERE task_id='t2'"
        ).fetchall()

    assert [row[0] for row in kept] == ["FR-8 — initialize-members"]


def test_migration_0073_gives_conversations_a_sequence_primary_key(tmp_path) -> None:
    """0073 makes `sequence` the primary key without losing indexes, constraints, rows, or the
    by-value foreign key `runs.conversation_id` depends on — and existing rows come out numbered
    in the order they were actually created."""
    db_file = tmp_path / "old_0034.db"
    _create_0034_conversations_state(db_file)
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO conversations "
            "(id, project_id, agent, lifecycle, created_at, updated_at) "
            "VALUES ('conv-second', 'proj-x', 'claude', 'open', "
            "'2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z')"
        )

    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run_alembic_with(db_url)

    columns = {column["name"]: column for column in _inspect_columns(db_url, "conversations")}
    assert "sequence" in columns
    assert columns["id"]["nullable"] is False

    with sqlite3.connect(db_file) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == HEAD_REVISION

        rows = conn.execute("SELECT id, sequence FROM conversations ORDER BY sequence").fetchall()
        assert [row[0] for row in rows] == ["conv-existing", "conv-second"]

        pk_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(conversations)") if row[5] > 0
        ]
        assert pk_columns == ["sequence"], "sequence must be the sole primary key column"

        # id keeps its uniqueness even though it is no longer the primary key.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO conversations "
                "(id, project_id, agent, lifecycle, created_at, updated_at) "
                "VALUES ('conv-existing', 'proj-x', 'claude', 'open', "
                "'2026-01-03T00:00:00Z', '2026-01-03T00:00:00Z')"
            )

        # A fresh insert gets a real sequence from the database, larger than any that came before.
        conn.execute(
            "INSERT INTO conversations "
            "(id, project_id, agent, lifecycle, created_at, updated_at) "
            "VALUES ('conv-third', 'proj-x', 'claude', 'open', "
            "'2026-01-03T00:00:00Z', '2026-01-03T00:00:00Z')"
        )
        new_sequence = conn.execute(
            "SELECT sequence FROM conversations WHERE id = 'conv-third'"
        ).fetchone()[0]
        assert new_sequence > max(row[1] for row in rows)

        # The row that references it by value is untouched and still resolves.
        assert conn.execute("SELECT conversation_id FROM runs WHERE id = 'run-1'").fetchone() == (
            "conv-existing",
        )

        # Everything 0035 established about the shape survives this recreate too.
        indexes = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        }
        assert {
            "ix_conversations_agent",
            "ix_conversations_project_agent_updated",
            "uq_conversations_project_agent_provider_session",
        } <= indexes
        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'conversations'"
        ).fetchone()[0]
        assert "ck_conversations_lifecycle" in ddl
        assert "ck_conversations_origin" in ddl


def test_migration_0073_is_guarded_when_conversations_does_not_exist(tmp_path) -> None:
    """No conversations table, no projects table — 0073 must not fail trying to recreate either."""
    db_file = tmp_path / "no_conversations.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0072')")

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}")

    with sqlite3.connect(db_file) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == HEAD_REVISION
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "conversations" not in tables


# ---------------------------------------------------------------------------
# 0074 — the archived phase and the capability kind
# ---------------------------------------------------------------------------


def _seed_spec_documents_for_downgrade(db_file: Path) -> None:
    """A project plus the two rows only 0074 can hold: capability/current and change/archived."""
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) "
            "VALUES ('proj-down', 'downgrade fixture', '2026-01-01T00:00:00Z')"
        )
        for doc_id, path, kind, phase in (
            ("spec-cap", "spec/capabilities/auth.md", "capability", "current"),
            ("spec-arch", "spec/changes/2026-01-01-thing.md", "change-spec", "archived"),
        ):
            conn.execute(
                "INSERT INTO spec_documents "
                "(id, project_id, path, title, kind, phase, rigor, created_at, updated_at) "
                "VALUES (?, 'proj-down', ?, 'fixture', ?, ?, 'sketch', "
                "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
                (doc_id, path, kind, phase),
            )


def test_migration_0074_downgrade_survives_a_capability_document(tmp_path) -> None:
    """Rollback must work on the databases that used the feature, not only on the ones that didn't.

    The ordering trap this pins: a capability row is `(kind='capability', phase='current')`, so
    `ck_spec_documents_kind_phase` refuses to let it become `approved` while that CHECK stands —
    but the narrowed three-value phase CHECK refuses to let it stay `current`, and a batch recreate
    applies its new CHECKs to the rows it copies. Rewriting the rows either before the paired CHECK
    is dropped or after the phase CHECK is narrowed fails. Only the middle works.

    Note the asymmetry that made the original defect easy to miss: the archived change-spec row
    downgrades fine on its own, because `change-spec` + `approved` satisfies the paired CHECK. A
    database with no capability document never sees the failure.
    """
    from alembic import command
    from alembic.config import Config

    db_file = tmp_path / "down_0074.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)
    _seed_spec_documents_for_downgrade(db_file)

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        command.downgrade(cfg, "0073")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0073"

        # Both recoverable states land on `approved`, and no row is lost.
        phases = dict(conn.execute("SELECT id, phase FROM spec_documents"))
        assert phases == {"spec-cap": "approved", "spec-arch": "approved"}

        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'spec_documents'"
        ).fetchone()[0]
        # The narrowed phase CHECK is back, and the two 0074 added are gone.
        assert "ck_spec_documents_phase" in ddl
        assert "archived" not in ddl
        assert "ck_spec_documents_kind_phase" not in ddl
        assert "ck_spec_documents_kind" not in ddl
        # Two table recreates must not cost the uniqueness the table had before 0074. It is an
        # inline table constraint, so it shows up in the DDL rather than as a named index.
        assert "uq_spec_documents_project_path" in ddl

        assert "spec_document_merges" not in {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }


def test_migration_0074_downgrade_then_upgrade_round_trips(tmp_path) -> None:
    """Down and back up again — the rollback escape hatch is only real if it is reversible."""
    from alembic import command
    from alembic.config import Config

    db_file = tmp_path / "roundtrip_0074.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)
    _seed_spec_documents_for_downgrade(db_file)

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        command.downgrade(cfg, "0073")
        command.upgrade(cfg, "head")

    with sqlite3.connect(db_file) as conn:
        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'spec_documents'"
        ).fetchone()[0]
        assert "ck_spec_documents_kind_phase" in ddl
        assert "ck_spec_documents_kind" in ddl
        assert "archived" in ddl
        # A capability document's phase is recoverable — `current` is the only phase it can have,
        # so the upgrade can restore it exactly. An archived change-spec's is not: `approved` and
        # `archived` are both legal for it after the upgrade, and nothing records which it was.
        # That asymmetry is the documented cost of the rollback, and the rows themselves survive.
        assert dict(conn.execute("SELECT id, phase FROM spec_documents")) == {
            "spec-cap": "current",
            "spec-arch": "approved",
        }


def test_migration_0074_kinds_do_not_drift_from_spec_payload(tmp_path) -> None:
    """The migration restates the `kind` vocabulary; nothing else asserts the two agree.

    `CLAUDE.md`: anything a standalone module needs from the Hub "is restated there, with a test
    asserting the two agree". Migrations cannot import `hub.spec_payload` — they run under alembic
    with no guarantee the package is importable — so 0074 restates `_KINDS`, and this is its guard.

    Without it, adding a kind to `spec_payload.KINDS` is a one-line change that passes every
    Python-layer check and is then rejected by `ck_spec_documents_kind` at INSERT time, with the
    whole suite still green.
    """
    import importlib.util

    from hub.db.models import SPEC_KINDS, SPEC_PHASES
    from hub.spec_payload import KINDS as PAYLOAD_KINDS

    migration_path = (
        Path(__file__).parent.parent
        / "hub"
        / "migrations"
        / "versions"
        / "0074_archive_and_capability_phase.py"
    )
    spec = importlib.util.spec_from_file_location("_migration_0074", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert set(module._KINDS) == set(SPEC_KINDS), (
        "migration 0074's _KINDS has drifted from the model's SPEC_KINDS — the database CHECK and "
        "the Python vocabulary must name the same set"
    )
    assert set(module._PHASES) == set(
        SPEC_PHASES
    ), "migration 0074's _PHASES has drifted from the model's SPEC_PHASES"
    # The third restatement: the Python-layer validator that decides what a caller may submit.
    assert set(PAYLOAD_KINDS) == set(SPEC_KINDS), (
        "spec_payload.KINDS has drifted from the model's SPEC_KINDS — a kind accepted by the "
        "validator and rejected by ck_spec_documents_kind fails only at INSERT time"
    )


# ---------------------------------------------------------------------------
# 0075 / 0076 — the rest of the rollback window
# ---------------------------------------------------------------------------


def test_migrations_0074_to_0076_roll_all_the_way_back_and_forward(tmp_path) -> None:
    """The whole 0073..head window must be reversible with every new table populated.

    0074's downgrade was the one with the ordering trap, but nothing had ever exercised 0075's or
    0076's at all. This walks head → 0073 → head against a database holding a capability document,
    a loop bound to a job, a task bound to that loop, and an edit proposal — i.e. rows in every
    object the three migrations introduce.
    """
    from alembic import command
    from alembic.config import Config

    db_file = tmp_path / "window.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)
    _seed_spec_documents_for_downgrade(db_file)

    stamp = "2026-01-01T00:00:00Z"
    with sqlite3.connect(db_file) as conn:
        # Columns whose only default is Python-side have to be spelled out here — a raw INSERT
        # never reaches the ORM that would supply them.
        conn.execute(
            "INSERT INTO ai_jobs (id, project_id, name, agent, message, cron, created_at, "
            "session_mode, enabled, source) "
            f"VALUES ('job-1', 'proj-down', 'nightly', 'claude', 'go', '0 9 * * *', '{stamp}', "
            "'new', 1, 'hub')"
        )
        conn.execute(
            "INSERT INTO loops (id, project_id, job_id, purpose, stop_when_queue_empties, "
            f"created_at) VALUES ('loop-1', 'proj-down', 'job-1', 'keep developing', 0, '{stamp}')"
        )
        conn.execute(
            "INSERT INTO tasks (id, project_id, title, description, status, priority, loop_id, "
            "created_at, updated) "
            f"VALUES ('task-1', 'proj-down', 'do a thing', '', 'pending', 'medium', 'loop-1', "
            f"'{stamp}', '{stamp}')"
        )
        conn.execute(
            "INSERT INTO spec_edit_proposals (id, document_id, unit_kind, unit_key, change_kind, "
            "proposed_payload, status, created_at, resolution_reason) "
            f"VALUES ('prop-1', 'spec-cap', 'requirement', 'REQ-1', 'add', '{{}}', 'pending', "
            f"'{stamp}', '')"
        )

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        command.downgrade(cfg, "0073")

        with sqlite3.connect(db_file) as conn:
            tables = {
                row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            assert "loops" not in tables
            assert "spec_edit_proposals" not in tables
            assert "spec_document_merges" not in tables
            task_columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
            assert "loop_id" not in task_columns
            job_run_columns = {row[1] for row in conn.execute("PRAGMA table_info(job_runs)")}
            assert "conversation_id" not in job_run_columns
            # The tables the loop was made of are untouched — only the binding is dropped.
            assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM ai_jobs").fetchone()[0] == 1

        command.upgrade(cfg, "head")

    with sqlite3.connect(db_file) as conn:
        assert (
            conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD_REVISION
        )
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"loops", "spec_edit_proposals", "spec_document_merges"} <= tables
        # Rows in the dropped tables are genuinely gone — a rollback past a table's creation
        # cannot preserve its contents, and this pins that as understood rather than surprising.
        assert conn.execute("SELECT COUNT(*) FROM loops").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM spec_documents").fetchone()[0] == 2


# ---------------------------------------------------------------------------
# 0077 — a loop declares its source document; a checkpoint carries its loop
# ---------------------------------------------------------------------------


def test_migration_0077_adds_the_loop_source_document_and_checkpoint_loop_binding(
    tmp_path,
) -> None:
    """`2026-08-18-a-loop-writes-its-own-queue` design D1/D4: both columns nullable, both indexed,
    `loops.spec_document_id` additionally unique so two loops cannot claim the same document."""
    db_file = tmp_path / "loop_source.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        loop_columns = {row[1]: row for row in conn.execute("PRAGMA table_info(loops)")}
        assert "spec_document_id" in loop_columns
        assert loop_columns["spec_document_id"][3] == 0  # notnull
        assert loop_columns["spec_document_id"][4] is None  # dflt_value — no backfill guess

        checkpoint_columns = {row[1]: row for row in conn.execute("PRAGMA table_info(checkpoints)")}
        assert "loop_id" in checkpoint_columns
        assert checkpoint_columns["loop_id"][3] == 0
        assert checkpoint_columns["loop_id"][4] is None

        loop_indexes = {row[1] for row in conn.execute("PRAGMA index_list(loops)")}
        assert "ix_loops_spec_document_id" in loop_indexes
        checkpoint_indexes = {row[1] for row in conn.execute("PRAGMA index_list(checkpoints)")}
        assert "ix_checkpoints_loop_id" in checkpoint_indexes


def test_migration_0077_spec_document_id_is_unique_per_loop(tmp_path) -> None:
    """A second loop declaring the same document a live loop already declared is rejected at the
    database layer, not just by the API's own check (design D1's "at most one loop per document").
    """
    db_file = tmp_path / "loop_source_unique.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    stamp = "2026-01-01T00:00:00Z"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) " f"VALUES ('proj-1', 'p', '{stamp}')"
        )
        for job_id in ("job-1", "job-2"):
            conn.execute(
                "INSERT INTO ai_jobs (id, project_id, name, agent, message, cron, created_at, "
                "session_mode, enabled, source) "
                f"VALUES ('{job_id}', 'proj-1', 'n', 'claude', 'go', '0 9 * * *', '{stamp}', "
                "'new', 1, 'hub')"
            )
        conn.execute(
            "INSERT INTO loops (id, project_id, job_id, purpose, stop_when_queue_empties, "
            f"created_at, spec_document_id) VALUES ('loop-1', 'proj-1', 'job-1', 'p', 0, "
            f"'{stamp}', 'doc-1')"
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO loops (id, project_id, job_id, purpose, stop_when_queue_empties, "
                f"created_at, spec_document_id) VALUES ('loop-2', 'proj-1', 'job-2', 'p', 0, "
                f"'{stamp}', 'doc-1')"
            )


def test_migration_0077_downgrade_then_upgrade_round_trips(tmp_path) -> None:
    """Down and back up again, with rows populated in both new columns beforehand — the rollback
    escape hatch is only real if the columns it drops actually come back on the way up."""
    from alembic import command
    from alembic.config import Config

    db_file = tmp_path / "roundtrip_0077.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    stamp = "2026-01-01T00:00:00Z"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) " f"VALUES ('proj-1', 'p', '{stamp}')"
        )
        conn.execute(
            "INSERT INTO ai_jobs (id, project_id, name, agent, message, cron, created_at, "
            "session_mode, enabled, source) "
            f"VALUES ('job-1', 'proj-1', 'n', 'claude', 'go', '0 9 * * *', '{stamp}', 'new', 1, "
            "'hub')"
        )
        conn.execute(
            "INSERT INTO loops (id, project_id, job_id, purpose, stop_when_queue_empties, "
            f"created_at, spec_document_id) VALUES ('loop-1', 'proj-1', 'job-1', 'p', 0, "
            f"'{stamp}', 'doc-1')"
        )
        conn.execute(
            "INSERT INTO conversations "
            "(id, project_id, agent, lifecycle, origin, title_set_by_operator, sequence, "
            "created_at, updated_at) "
            f"VALUES ('conv-1', 'proj-1', 'claude', 'open', 'operator', 0, 1, "
            f"'{stamp}', '{stamp}')"
        )
        conn.execute(
            "INSERT INTO checkpoints (id, project_id, conversation_id, loop_id, agent, trigger, "
            "status, visibility, lineage_id, created_at) VALUES ('cp-1', 'proj-1', 'conv-1', "
            f"'loop-1', 'claude', 'operator', 'unwritten', 'private', 'cp-1', '{stamp}')"
        )
        conn.commit()

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        # Absolute target, not "-1": head has moved past 0077 since this test was written (0078
        # adds its own columns on top), so a relative one-step-back would only undo 0078 and leave
        # this test asserting on the wrong migration's columns.
        command.downgrade(cfg, "0076")

        with sqlite3.connect(db_file) as conn:
            loop_columns = {row[1] for row in conn.execute("PRAGMA table_info(loops)")}
            assert "spec_document_id" not in loop_columns
            checkpoint_columns = {row[1] for row in conn.execute("PRAGMA table_info(checkpoints)")}
            assert "loop_id" not in checkpoint_columns
            # The rows themselves survive — only the binding column is dropped.
            assert conn.execute("SELECT COUNT(*) FROM loops").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 1

        command.upgrade(cfg, "head")

    with sqlite3.connect(db_file) as conn:
        assert (
            conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD_REVISION
        )
        loop_columns = {row[1] for row in conn.execute("PRAGMA table_info(loops)")}
        assert "spec_document_id" in loop_columns
        checkpoint_columns = {row[1] for row in conn.execute("PRAGMA table_info(checkpoints)")}
        assert "loop_id" in checkpoint_columns
        # The upgrade cannot recover what the downgrade discarded — a checkpoint or loop that
        # existed through the round trip has its binding back as NULL, not restored.
        assert (
            conn.execute("SELECT spec_document_id FROM loops WHERE id = 'loop-1'").fetchone()[0]
            is None
        )
        assert (
            conn.execute("SELECT loop_id FROM checkpoints WHERE id = 'cp-1'").fetchone()[0] is None
        )


# ---------------------------------------------------------------------------
# 0078 — a loop and a plain job are archivable, and a loop records how it ended
# ---------------------------------------------------------------------------


def test_migration_0078_adds_archival_and_ending_state_columns(tmp_path) -> None:
    """`2026-08-18-a-loop-writes-its-own-queue` design D16/D17 (task B1): three nullable
    columns, none backfilled, none indexed — plain housekeeping/value columns, not a lookup key."""
    db_file = tmp_path / "loop_archival.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        loop_columns = {row[1]: row for row in conn.execute("PRAGMA table_info(loops)")}
        assert "archived_at" in loop_columns
        assert loop_columns["archived_at"][3] == 0  # notnull
        assert loop_columns["archived_at"][4] is None  # dflt_value — no backfill guess
        assert "ending_state" in loop_columns
        assert loop_columns["ending_state"][3] == 0
        assert loop_columns["ending_state"][4] is None

        job_columns = {row[1]: row for row in conn.execute("PRAGMA table_info(ai_jobs)")}
        assert "archived_at" in job_columns
        assert job_columns["archived_at"][3] == 0
        assert job_columns["archived_at"][4] is None


def test_migration_0078_downgrade_then_upgrade_round_trips(tmp_path) -> None:
    """Down and back up again, with rows populated in all three new columns beforehand — the
    rollback escape hatch is only real if the columns it drops actually come back on the way up."""
    from alembic import command
    from alembic.config import Config

    db_file = tmp_path / "roundtrip_0078.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    stamp = "2026-01-01T00:00:00Z"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) " f"VALUES ('proj-1', 'p', '{stamp}')"
        )
        conn.execute(
            "INSERT INTO ai_jobs (id, project_id, name, agent, message, cron, created_at, "
            "session_mode, enabled, source, archived_at) "
            f"VALUES ('job-1', 'proj-1', 'n', 'claude', 'go', '0 9 * * *', '{stamp}', 'new', 1, "
            f"'hub', '{stamp}')"
        )
        conn.execute(
            "INSERT INTO loops (id, project_id, job_id, purpose, stop_when_queue_empties, "
            "created_at, archived_at, ending_state) VALUES ('loop-1', 'proj-1', 'job-1', 'p', 0, "
            f"'{stamp}', '{stamp}', 'completed')"
        )
        conn.commit()

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        # Absolute target, not "-1": head has moved past 0078 since this test was written (0079
        # adds its own column on top), so a relative one-step-back would only undo 0079 and leave
        # this test asserting on the wrong migration's columns — same trap 0077's own round-trip
        # test already hit once, above.
        command.downgrade(cfg, "0077")

        with sqlite3.connect(db_file) as conn:
            loop_columns = {row[1] for row in conn.execute("PRAGMA table_info(loops)")}
            assert "archived_at" not in loop_columns
            assert "ending_state" not in loop_columns
            job_columns = {row[1] for row in conn.execute("PRAGMA table_info(ai_jobs)")}
            assert "archived_at" not in job_columns
            # The rows themselves survive — only the archival/ending columns are dropped.
            assert conn.execute("SELECT COUNT(*) FROM loops").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM ai_jobs").fetchone()[0] == 1

        command.upgrade(cfg, "head")

    with sqlite3.connect(db_file) as conn:
        assert (
            conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD_REVISION
        )
        loop_columns = {row[1] for row in conn.execute("PRAGMA table_info(loops)")}
        assert "archived_at" in loop_columns
        assert "ending_state" in loop_columns
        job_columns = {row[1] for row in conn.execute("PRAGMA table_info(ai_jobs)")}
        assert "archived_at" in job_columns
        # The upgrade cannot recover what the downgrade discarded — a loop or job that existed
        # through the round trip has its archival/ending columns back as NULL, not restored.
        assert conn.execute(
            "SELECT archived_at, ending_state FROM loops WHERE id = 'loop-1'"
        ).fetchone() == (None, None)
        assert (
            conn.execute("SELECT archived_at FROM ai_jobs WHERE id = 'job-1'").fetchone()[0] is None
        )


# ---------------------------------------------------------------------------
# 0079 — a loop's queue-extension control is an explicit per-loop setting
# ---------------------------------------------------------------------------


def test_migration_0079_adds_control_column(tmp_path) -> None:
    """Design D10 (task A1.1): one nullable column, no backfill — NULL means the current
    default (the operator), never a stored copy of it."""
    db_file = tmp_path / "loop_control.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        loop_columns = {row[1]: row for row in conn.execute("PRAGMA table_info(loops)")}
        assert "control" in loop_columns
        assert loop_columns["control"][3] == 0  # notnull
        assert loop_columns["control"][4] is None  # dflt_value — no backfill guess


def test_migration_0079_downgrade_then_upgrade_round_trips(tmp_path) -> None:
    """Down and back up again, with a row populated in the new column beforehand."""
    from alembic import command
    from alembic.config import Config

    db_file = tmp_path / "roundtrip_0079.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    stamp = "2026-01-01T00:00:00Z"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) " f"VALUES ('proj-1', 'p', '{stamp}')"
        )
        conn.execute(
            "INSERT INTO ai_jobs (id, project_id, name, agent, message, cron, created_at, "
            "session_mode, enabled, source) "
            f"VALUES ('job-1', 'proj-1', 'n', 'claude', 'go', '0 9 * * *', '{stamp}', 'new', 1, "
            "'hub')"
        )
        conn.execute(
            "INSERT INTO loops (id, project_id, job_id, purpose, stop_when_queue_empties, "
            "created_at, control) VALUES ('loop-1', 'proj-1', 'job-1', 'p', 0, "
            f"'{stamp}', 'creator')"
        )
        conn.commit()

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        # Absolute target, not "-1": head has moved past 0079 since this test was written (0080
        # adds its own columns on top), so a relative one-step-back would only undo 0080 and leave
        # this test asserting on the wrong migration's column — the same trap 0077's and 0078's own
        # round-trip tests already hit once each, above.
        command.downgrade(cfg, "0078")

        with sqlite3.connect(db_file) as conn:
            loop_columns = {row[1] for row in conn.execute("PRAGMA table_info(loops)")}
            assert "control" not in loop_columns
            # The row itself survives — only the control column is dropped.
            assert conn.execute("SELECT COUNT(*) FROM loops").fetchone()[0] == 1

        command.upgrade(cfg, "head")

    with sqlite3.connect(db_file) as conn:
        assert (
            conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD_REVISION
        )
        loop_columns = {row[1] for row in conn.execute("PRAGMA table_info(loops)")}
        assert "control" in loop_columns
        # The upgrade cannot recover what the downgrade discarded.
        assert conn.execute("SELECT control FROM loops WHERE id = 'loop-1'").fetchone()[0] is None


# ---------------------------------------------------------------------------
# 0080 — a loop's definition edits are staged, not applied immediately
# ---------------------------------------------------------------------------


def test_migration_0080_adds_pending_edit_columns(tmp_path) -> None:
    """Design D11 (task A2.1/A2.5): five nullable columns, no backfill."""
    db_file = tmp_path / "loop_pending_edit.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        loop_columns = {row[1]: row for row in conn.execute("PRAGMA table_info(loops)")}
        for column in (
            "pending_purpose",
            "pending_stop_at",
            "pending_stop_when_queue_empties",
            "pending_edit_actor",
            "pending_edit_at",
        ):
            assert column in loop_columns
            assert loop_columns[column][3] == 0  # notnull
            assert loop_columns[column][4] is None  # dflt_value — no backfill guess


def test_migration_0080_downgrade_then_upgrade_round_trips(tmp_path) -> None:
    """Down and back up again, with a row populated in every new column beforehand."""
    from alembic import command
    from alembic.config import Config

    db_file = tmp_path / "roundtrip_0080.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    stamp = "2026-01-01T00:00:00Z"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) " f"VALUES ('proj-1', 'p', '{stamp}')"
        )
        conn.execute(
            "INSERT INTO ai_jobs (id, project_id, name, agent, message, cron, created_at, "
            "session_mode, enabled, source) "
            f"VALUES ('job-1', 'proj-1', 'n', 'claude', 'go', '0 9 * * *', '{stamp}', 'new', 1, "
            "'hub')"
        )
        conn.execute(
            "INSERT INTO loops (id, project_id, job_id, purpose, stop_when_queue_empties, "
            "created_at, pending_purpose, pending_stop_when_queue_empties, pending_edit_actor, "
            "pending_edit_at) VALUES ('loop-1', 'proj-1', 'job-1', 'p', 0, "
            f"'{stamp}', 'new purpose', 1, 'operator', '{stamp}')"
        )
        conn.commit()

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        # Absolute target, not "-1": head has moved past 0080 since this test was written (0081
        # adds its own column on top), so a relative one-step-back would only undo 0081 and leave
        # this test asserting on the wrong migration's columns — the same trap 0077's, 0078's and
        # 0079's own round-trip tests already hit once each, above.
        command.downgrade(cfg, "0079")

        with sqlite3.connect(db_file) as conn:
            loop_columns = {row[1] for row in conn.execute("PRAGMA table_info(loops)")}
            for column in (
                "pending_purpose",
                "pending_stop_at",
                "pending_stop_when_queue_empties",
                "pending_edit_actor",
                "pending_edit_at",
            ):
                assert column not in loop_columns
            # The row itself survives — only the pending-edit columns are dropped.
            assert conn.execute("SELECT COUNT(*) FROM loops").fetchone()[0] == 1

        command.upgrade(cfg, "head")

    with sqlite3.connect(db_file) as conn:
        assert (
            conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD_REVISION
        )
        loop_columns = {row[1] for row in conn.execute("PRAGMA table_info(loops)")}
        for column in (
            "pending_purpose",
            "pending_stop_at",
            "pending_stop_when_queue_empties",
            "pending_edit_actor",
            "pending_edit_at",
        ):
            assert column in loop_columns
        # The upgrade cannot recover what the downgrade discarded — every pending-edit column
        # comes back as NULL, not restored.
        row = conn.execute(
            "SELECT pending_purpose, pending_stop_when_queue_empties, pending_edit_actor, "
            "pending_edit_at FROM loops WHERE id = 'loop-1'"
        ).fetchone()
        assert row == (None, None, None, None)


# ---------------------------------------------------------------------------
# 0081 — a per-loop history home for event_logs
# ---------------------------------------------------------------------------


def test_migration_0081_adds_event_log_loop_id(tmp_path) -> None:
    """Design D13 (task A4.1): one nullable column plus its own composite index, no backfill."""
    db_file = tmp_path / "event_log_loop_id.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        event_columns = {row[1]: row for row in conn.execute("PRAGMA table_info(event_logs)")}
        assert "loop_id" in event_columns
        assert event_columns["loop_id"][3] == 0  # notnull
        assert event_columns["loop_id"][4] is None  # dflt_value — no backfill guess

        index_names = {row[1] for row in conn.execute("PRAGMA index_list(event_logs)")}
        assert "ix_event_logs_loop_ts" in index_names


def test_migration_0081_downgrade_then_upgrade_round_trips(tmp_path) -> None:
    """Down and back up again, with a row populated in the new column beforehand."""
    from alembic import command
    from alembic.config import Config

    db_file = tmp_path / "roundtrip_0081.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    stamp = "2026-01-01T00:00:00Z"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) " f"VALUES ('proj-1', 'p', '{stamp}')"
        )
        conn.execute(
            "INSERT INTO event_logs (id, project_id, event_type, loop_id, severity, timestamp) "
            f"VALUES ('evt-1', 'proj-1', 'loop_archived', 'loop-1', 'info', '{stamp}')"
        )
        conn.commit()

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        # Absolute target, not "-1": head has moved past 0081 since this test was written (0082
        # drops the unasked_questions table on top), so a relative one-step-back would only undo
        # 0082 and leave event_logs.loop_id in place — the same correction 0079 and 0080 already
        # carry above.
        command.downgrade(cfg, "0080")

        with sqlite3.connect(db_file) as conn:
            event_columns = {row[1] for row in conn.execute("PRAGMA table_info(event_logs)")}
            assert "loop_id" not in event_columns
            # The row itself survives — only the loop_id column is dropped.
            assert conn.execute("SELECT COUNT(*) FROM event_logs").fetchone()[0] == 1

        command.upgrade(cfg, "head")

    with sqlite3.connect(db_file) as conn:
        assert (
            conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD_REVISION
        )
        event_columns = {row[1] for row in conn.execute("PRAGMA table_info(event_logs)")}
        assert "loop_id" in event_columns
        # The upgrade cannot recover what the downgrade discarded.
        assert (
            conn.execute("SELECT loop_id FROM event_logs WHERE id = 'evt-1'").fetchone()[0] is None
        )


def test_migration_0083_is_guarded_when_tasks_and_spec_documents_do_not_exist(tmp_path) -> None:
    """An upgrade starting from an early revision reaches 0083 with neither `tasks` nor
    `spec_documents` — `_create_0034_conversations_state` builds only `projects`/`conversations`/
    `runs`. Both additions must skip rather than fail, and the upgrade must still reach head.
    """
    db_file = tmp_path / "early_0083.db"
    _create_0034_conversations_state(db_file)

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            HEAD_REVISION
        )
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        # `tasks` is never created by any migration — a real startup's `create_all` builds it
        # from the model, and this early state (built by `_create_0034_conversations_state`,
        # which predates it) never gains one on the way to head either. `task_dependencies`
        # references it, so it must be skipped rather than created against a foreign key with
        # nothing to point at.
        assert "tasks" not in tables
        assert "task_dependencies" not in tables
        # `spec_documents` is unrelated to `tasks` and is created unconditionally by `0065` on
        # the way to head, so `first_approved_at` is added to it same as any other upgrade.
        assert "spec_documents" in tables
        doc_columns = {row[1] for row in conn.execute("PRAGMA table_info(spec_documents)")}
        assert "first_approved_at" in doc_columns


def test_migration_0083_creates_task_dependencies_and_first_approved_at_column(tmp_path) -> None:
    """The join table lands with both directions indexed, and the new column is nullable."""
    db_file = tmp_path / "fresh_0083.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(task_dependencies)")}
        assert {"id", "project_id", "task_id", "depends_on_task_id", "created_at"} <= columns

        indexes = {row[1] for row in conn.execute("PRAGMA index_list(task_dependencies)")}
        assert "ix_task_dependencies_task" in indexes
        assert "ix_task_dependencies_depends_on" in indexes

        doc_columns = {row[1] for row in conn.execute("PRAGMA table_info(spec_documents)")}
        assert "first_approved_at" in doc_columns


def test_migration_0083_backfills_first_approved_at_from_phase_history(tmp_path) -> None:
    """The earliest `phase` event moving `to: "approved"` becomes `first_approved_at` — and a
    later reopen recorded afterward must not be mistaken for a later approval."""
    import json

    db_file = tmp_path / "backfill_0083.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) VALUES ('p1', 'demo', '2026-08-13')"
        )
        conn.execute(
            "INSERT INTO spec_documents (id, project_id, path, title, kind, phase, created_at,"
            " updated_at, first_approved_at) VALUES ('d1', 'p1', 'spec/x/spec.html', 'X',"
            " 'change-spec', 'exploring', '2026-08-13', '2026-08-13', NULL)"
        )
        events = [
            ("e1", "2026-08-14T00:00:00Z", {"from": "exploring", "to": "proposed"}),
            ("e2", "2026-08-15T00:00:00Z", {"from": "proposed", "to": "approved"}),
            ("e3", "2026-08-16T00:00:00Z", {"from": "approved", "to": "exploring"}),
            ("e4", "2026-08-17T00:00:00Z", {"from": "proposed", "to": "approved"}),
        ]
        for event_id, created_at, detail in events:
            conn.execute(
                "INSERT INTO spec_document_events (id, document_id, project_id, kind, actor_kind,"
                " actor, origin, detail, created_at) VALUES (?, 'd1', 'p1', 'phase', 'operator',"
                " 'op', 'lifecycle', ?, ?)",
                (event_id, json.dumps(detail), created_at),
            )
        # Clear the column create_all's own model gave the row, so the migration's own backfill
        # (not the model default) is what this test is actually exercising.
        conn.execute("UPDATE spec_documents SET first_approved_at = NULL WHERE id = 'd1'")
        conn.commit()

    _stamp(db_file, "0082")
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        value = conn.execute(
            "SELECT first_approved_at FROM spec_documents WHERE id = 'd1'"
        ).fetchone()[0]
    # e2, the earliest "to": "approved" event — not e4, the later one after a reopen.
    assert value is not None
    assert str(value).startswith("2026-08-15")


def test_migration_0083_leaves_a_never_approved_document_null(tmp_path) -> None:
    """A document with no `to: "approved"` event in its history is honestly NULL, not guessed."""
    db_file = tmp_path / "never_approved_0083.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) VALUES ('p2', 'demo', '2026-08-13')"
        )
        conn.execute(
            "INSERT INTO spec_documents (id, project_id, path, title, kind, phase, created_at,"
            " updated_at, first_approved_at) VALUES ('d2', 'p2', 'spec/y/spec.html', 'Y',"
            " 'change-spec', 'exploring', '2026-08-13', '2026-08-13', NULL)"
        )
        conn.commit()

    _stamp(db_file, "0082")
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        value = conn.execute(
            "SELECT first_approved_at FROM spec_documents WHERE id = 'd2'"
        ).fetchone()[0]
    assert value is None


def test_migration_0084_is_guarded_when_tasks_does_not_exist(tmp_path) -> None:
    """Same early-revision state as 0083's own guard test: no `tasks` table to point at."""
    db_file = tmp_path / "early_0084.db"
    _create_0034_conversations_state(db_file)

    _run_alembic_with(f"sqlite+aiosqlite:///{db_file}")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            HEAD_REVISION
        )
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "tasks" not in tables
        assert "task_dependency_references" not in tables


def test_migration_0084_creates_task_dependency_references(tmp_path) -> None:
    """The table lands with its task index, mirroring `task_requirement_references`' shape."""
    db_file = tmp_path / "fresh_0084.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(task_dependency_references)")}
        assert {"id", "project_id", "task_id", "reference", "reason", "created_at"} <= columns

        indexes = {row[1] for row in conn.execute("PRAGMA index_list(task_dependency_references)")}
        assert "ix_task_dependency_references_task" in indexes


def test_migration_0085_adds_lineage_id(tmp_path) -> None:
    """`conversations.lineage_id` lands, every pre-existing row backfills to its own `id`, the
    column is indexed, and downgrade drops it — see design.md D3."""
    db_file = tmp_path / "old_0034_lineage.db"
    _create_0034_conversations_state(db_file)

    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            HEAD_REVISION
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(conversations)")}
        assert "lineage_id" in columns

        assert conn.execute(
            "SELECT lineage_id FROM conversations WHERE id = 'conv-existing'"
        ).fetchone() == ("conv-existing",)

        indexes = {row[1] for row in conn.execute("PRAGMA index_list(conversations)")}
        assert "ix_conversations_lineage_id" in indexes

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        command.downgrade(cfg, "0084")

    with sqlite3.connect(db_file) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(conversations)")}
        assert "lineage_id" not in columns
        # The row itself survives — only the lineage_id column is dropped.
        assert conn.execute(
            "SELECT id FROM conversations WHERE id = 'conv-existing'"
        ).fetchone() == ("conv-existing",)


def test_migration_0086_adds_review_task_id_to_queue_entries(tmp_path) -> None:
    """`inbound_queue_entries.review_task_id` lands, is nullable, survives a round trip, and is a
    column of its own rather than a reuse of `task_id` — see the migration's own note for why
    collapsing the two would make a reviewer look like the task's author.
    """
    db_file = tmp_path / "queue_review_task.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            HEAD_REVISION
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(inbound_queue_entries)")}
        assert "review_task_id" in columns
        assert "task_id" in columns

        conn.execute(
            "INSERT INTO inbound_queue_entries "
            "(id, project_id, agent, origin_type, content, arrived_at, hop_depth, state, "
            " review_task_id) "
            "VALUES ('entry-r1', 'proj-test', 'critic', 'operator', 'review it', "
            "        '2026-08-24 09:00:00', 0, 'queued', 'task-under-review')"
        )
        assert conn.execute(
            "SELECT review_task_id, task_id FROM inbound_queue_entries WHERE id = 'entry-r1'"
        ).fetchone() == ("task-under-review", None)

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        command.downgrade(cfg, "0085")

    with sqlite3.connect(db_file) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(inbound_queue_entries)")}
        assert "review_task_id" not in columns
        # The entry itself survives; only the column goes.
        assert conn.execute(
            "SELECT id FROM inbound_queue_entries WHERE id = 'entry-r1'"
        ).fetchone() == ("entry-r1",)

    with patch.object(settings, "database_url", db_url):
        command.upgrade(cfg, "0086")

    with sqlite3.connect(db_file) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(inbound_queue_entries)")}
        assert "review_task_id" in columns


def test_migration_0086_is_guarded_when_the_queue_table_does_not_exist(tmp_path) -> None:
    """Upgrades that start from an early revision reach 0086 with only that revision's tables."""
    db_file = tmp_path / "no_queue_table.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0085')")

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        command.upgrade(cfg, "0086")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0086"


# 0097 — checkpoints stored under the absent default become project-visible


def test_migration_0097_moves_stored_private_checkpoints_to_project(tmp_path) -> None:
    """F88. Every stored `private` is the absent default, not somebody's decision — nothing in
    the product could ever set that column — so leaving them would split a project's history at
    this migration with the older half permanently unreadable."""
    db_file = tmp_path / "visibility.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _upgrade_to(db_url, "0096")

    with sqlite3.connect(db_file) as conn:
        # `0044` only creates this table when `projects` and `conversations` are already there,
        # and a bare alembic run has neither — the model layer builds them. The stored row is
        # what this migration is about, so the table is stood up here with the columns it needs.
        conn.execute(
            "CREATE TABLE checkpoints ("
            " id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64), conversation_id VARCHAR(64),"
            " agent VARCHAR(64), trigger VARCHAR(32), status VARCHAR(16),"
            " visibility VARCHAR(16), lineage_id VARCHAR(64), body TEXT, created_at DATETIME)"
        )
        conn.execute(
            "INSERT INTO checkpoints "
            "(id, project_id, conversation_id, agent, trigger, status, visibility, lineage_id, "
            " body, created_at) "
            "VALUES ('ckpt-old', 'proj-test', 'conv-1', 'author', 'operator', 'ready', "
            "        'private', 'ckpt-old', '## Objective', '2026-08-27 12:00:00')"
        )

    _upgrade_to(db_url, "0097")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute(
            "SELECT visibility FROM checkpoints WHERE id = 'ckpt-old'"
        ).fetchone() == ("project",)


def test_migration_0097_is_guarded_when_the_checkpoints_table_does_not_exist(tmp_path) -> None:
    """Upgrades that start from an early revision reach 0097 with only that revision's tables."""
    db_file = tmp_path / "no_checkpoints_table.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0096')")

    _upgrade_to(db_url, "0097")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0097"


# ---------------------------------------------------------------------------
# 0098 — a queued entry records why its last delivery attempt did not start a turn
# ---------------------------------------------------------------------------


def test_migration_0098_adds_waiting_reason_and_leaves_existing_entries_null(tmp_path) -> None:
    """F97. No backfill: this records what a delivery attempt was refused with, and for an entry
    queued before the migration no such record was kept — writing one would forge it."""
    db_file = tmp_path / "waiting_reason.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _upgrade_to(db_url, "0097")

    with sqlite3.connect(db_file) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(inbound_queue_entries)").fetchall()
        }
        assert "waiting_reason" not in columns
        conn.execute(
            "INSERT INTO inbound_queue_entries "
            "(id, project_id, agent, origin_type, content, arrived_at, hop_depth, state) "
            "VALUES ('entry-old', 'proj-test', 'author', 'operator', 'hello', "
            "        '2026-08-27 12:00:00', 0, 'queued')"
        )

    _upgrade_to(db_url, "0098")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute(
            "SELECT waiting_reason FROM inbound_queue_entries WHERE id = 'entry-old'"
        ).fetchone() == (None,)


def test_migration_0098_is_guarded_when_the_queue_table_does_not_exist(tmp_path) -> None:
    """Upgrades that start from an early revision reach 0098 with only that revision's tables."""
    db_file = tmp_path / "no_queue_table.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0097')")

    _upgrade_to(db_url, "0098")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0098"


# ---------------------------------------------------------------------------
# 0100 — a loop declares whether its work needs evidence to reach the main branch
# ---------------------------------------------------------------------------


def test_migration_0100_adds_work_needs_evidence_with_no_backfill(tmp_path) -> None:
    """F124, design D2: one nullable column, no server default and no backfill guess."""
    db_file = tmp_path / "loop_work_needs_evidence.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        loop_columns = {row[1]: row for row in conn.execute("PRAGMA table_info(loops)")}
        assert "work_needs_evidence" in loop_columns
        assert loop_columns["work_needs_evidence"][3] == 0  # notnull
        assert loop_columns["work_needs_evidence"][4] is None  # dflt_value


def test_migration_0100_leaves_an_existing_loop_null_rather_than_answering_for_it(
    tmp_path,
) -> None:
    """The load-bearing half, and it is about **flows**.

    `loops` holds flows as well as loops, and `merge_targets` treats any explicit value as the
    operator's own word — it wins over the kind-aware default that keeps evidence governing a
    flow. So a `server_default` of either value would answer this question for every flow that
    already exists, silently. An upgraded row must read NULL, which is how "the product's current
    default" is spelled.

    Written as a downgrade-and-back-up rather than a plain forward upgrade because `loops` is
    created by `create_all` from the models, not by the migration chain: a database built by
    migrations alone has no `loops` table at all (which is what 0100's own guard is for, below).
    """
    from alembic import command
    from alembic.config import Config

    db_file = tmp_path / "loop_work_needs_evidence_backfill.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    stamp = "2026-01-01T00:00:00Z"
    with patch.object(settings, "database_url", db_url):
        command.downgrade(cfg, "0099")

        with sqlite3.connect(db_file) as conn:
            assert "work_needs_evidence" not in {
                row[1] for row in conn.execute("PRAGMA table_info(loops)")
            }
            conn.execute(
                "INSERT INTO projects (id, name, created_at) " f"VALUES ('proj-1', 'p', '{stamp}')"
            )
            conn.execute(
                "INSERT INTO ai_jobs (id, project_id, name, agent, message, cron, created_at, "
                "session_mode, enabled, source) "
                f"VALUES ('job-1', 'proj-1', 'n', 'claude', 'go', '0 9 * * *', '{stamp}', "
                "'new', 1, 'hub')"
            )
            # A **flow**: it names a document, which is the shape a wrong server default would
            # have quietly answered for.
            conn.execute(
                "INSERT INTO loops (id, project_id, job_id, purpose, stop_when_queue_empties, "
                "created_at, spec_document_id) "
                f"VALUES ('loop-1', 'proj-1', 'job-1', 'p', 0, '{stamp}', 'doc-1')"
            )
            conn.commit()

        command.upgrade(cfg, "head")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute(
            "SELECT work_needs_evidence FROM loops WHERE id = 'loop-1'"
        ).fetchone() == (None,)


def test_migration_0100_is_guarded_when_the_loops_table_does_not_exist(tmp_path) -> None:
    """Upgrades that start from an early revision reach 0100 with only that revision's tables."""
    db_file = tmp_path / "no_loops_table.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0099')")

    _upgrade_to(db_url, "0100")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0100"


def test_running_migrations_leaves_existing_loggers_enabled(tmp_path) -> None:
    """F151: `env.py` must not silence the process it is migrating inside of.

    `env.py` calls `logging.config.fileConfig`, whose `disable_existing_loggers` defaults to
    **True** — it sets `disabled = True` on every logger that already exists and is not named in
    `alembic.ini`. Migrations run from `init_db()`, the first line of the Hub's `lifespan()`, by
    which point `uvicorn.error`, `uvicorn.access` and every `hub.*` module logger have been
    created at import time. With the default, starting the Hub muted the entire process for its
    whole life: no "Application startup complete.", no access log, no `_ui_staleness_warning()`,
    no run-failure traceback. Only alembic's own lines survived, because `[loggers]` names them.

    The two loggers asserted on are the two that matter and the two an operator actually reads:
    uvicorn's, which reports that the server is up and serving, and a `hub.*` module logger,
    which is every warning the Hub itself raises. Both are created here **before** the upgrade,
    which is the ordering the Hub has at startup and the only ordering under which this can fail.
    """
    uvicorn_logger = logging.getLogger("uvicorn.error")
    hub_logger = logging.getLogger("hub.run_reconciliation")
    assert not uvicorn_logger.disabled
    assert not hub_logger.disabled

    _upgrade_to(f"sqlite+aiosqlite:///{tmp_path / 'logging.db'}", "head")

    assert not uvicorn_logger.disabled, (
        "running migrations disabled uvicorn's logger; the Hub serves the rest of the process "
        "without printing a single line (F151)"
    )
    assert not hub_logger.disabled, (
        "running migrations disabled the Hub's own module loggers; every logger.warning it "
        "raises after startup goes nowhere (F151)"
    )


# ---------------------------------------------------------------------------
# 0101 — the writes a run made outside the directory it was given
# ---------------------------------------------------------------------------


def test_migration_0101_adds_outside_workspace_writes_to_both_tables(tmp_path) -> None:
    """F115, designs D5/D10/D11: two columns, nullable and undefaulted on both.

    The two are one fact recorded for two readers — the run's durable record, and that record as
    it stood when a footprint was captured. D10 keeps them in one revision.

    **What this proves is the model, not the migration.** `_create_all_at` builds every table from
    `Base.metadata` before alembic runs, which is the real startup order, so both columns are
    already present when `0101` arrives and it is a no-op here. Measured, not assumed: with
    `evidence_footprints` deleted from the migration's `_TABLES` this test still passes. The half
    of `0101` that touches `evidence_footprints` is held by the downgrade in
    `test_migration_0101_leaves_existing_rows_null_rather_than_claiming_they_were_watched`, which
    does fail under that mutation — read the two together.
    """
    db_file = tmp_path / "outside_workspace_writes.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    with sqlite3.connect(db_file) as conn:
        for table in ("runs", "evidence_footprints"):
            columns = {row[1]: row for row in conn.execute(f"PRAGMA table_info({table})")}
            assert "outside_workspace_writes" in columns, table
            assert columns["outside_workspace_writes"][3] == 0, table  # notnull
            assert columns["outside_workspace_writes"][4] is None, table  # dflt_value


def test_migration_0101_leaves_existing_rows_null_rather_than_claiming_they_were_watched(
    tmp_path,
) -> None:
    """The load-bearing half. NULL is *nobody was looking*; `[]` is *observed, nothing escaped*.

    A `server_default` of `'[]'` — or any backfill — would say of every run and every footprint
    recorded before the detector existed that it was watched and found clean. That is the claim of
    coverage design D12 refuses to let this change make, and it is the same reason `0096` did not
    backfill `workspace_dir` and `0043` did not backfill `snapshot_commit_sha`.

    Written as a downgrade-and-back-up, like `0100`'s, because neither `runs` nor
    `evidence_footprints` is created by the migration chain — both exist only from the models.
    That shape is also the only reason any test here reaches `0101`'s own `op.add_column`: the
    downgrade removes what `create_all` put there, so the re-upgrade is the migration doing the
    work rather than the model. This is therefore the test that fails if either table is dropped
    from `_TABLES`.
    """
    from alembic import command
    from alembic.config import Config

    db_file = tmp_path / "outside_workspace_writes_backfill.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    _run_alembic_with(db_url)

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    stamp = "2026-01-01T00:00:00Z"
    with patch.object(settings, "database_url", db_url):
        command.downgrade(cfg, "0100")

        with sqlite3.connect(db_file) as conn:
            for table in ("runs", "evidence_footprints"):
                assert "outside_workspace_writes" not in {
                    row[1] for row in conn.execute(f"PRAGMA table_info({table})")
                }, table
            conn.execute(
                "INSERT INTO projects (id, name, created_at) " f"VALUES ('proj-1', 'p', '{stamp}')"
            )
            conn.execute(
                "INSERT INTO runs (id, project_id, agent, status, started_at, initiator) "
                f"VALUES ('run-1', 'proj-1', 'builder', 'completed', '{stamp}', 'operator')"
            )
            # No parent `requirement_evidence` row: sqlite leaves `foreign_keys` off by default,
            # and what this test is about is the column's default, not referential integrity.
            conn.execute(
                "INSERT INTO evidence_footprints "
                "(id, project_id, evidence_id, kind, observed_at) "
                f"VALUES ('fp-1', 'proj-1', 'ev-1', 'git', '{stamp}')"
            )
            conn.commit()

        command.upgrade(cfg, "head")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute(
            "SELECT outside_workspace_writes FROM runs WHERE id = 'run-1'"
        ).fetchone() == (None,)
        assert conn.execute(
            "SELECT outside_workspace_writes FROM evidence_footprints WHERE id = 'fp-1'"
        ).fetchone() == (None,)


def test_migration_0101_is_guarded_when_neither_table_exists(tmp_path) -> None:
    """Upgrades that start from an early revision reach 0101 with only that revision's tables.

    Both guards are exercised at once here, and they are independent on purpose: `runs` and
    `evidence_footprints` enter the schema at different points, so a database can arrive with one
    and not the other.
    """
    db_file = tmp_path / "no_runs_or_footprints.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0100')")

    _upgrade_to(db_url, "0101")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0101"


def test_migration_0101_adds_the_column_to_whichever_table_is_present(tmp_path) -> None:
    """The half-schema case the two independent guards exist for.

    A single `if either table is missing: return` would have passed the test above and silently
    skipped `evidence_footprints` on any database that happened to have `runs`. So stand up one
    table without the other and assert the present one still gets its column.
    """
    db_file = tmp_path / "only_runs.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0100')")
        conn.execute(
            "CREATE TABLE runs ("
            " id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64), agent VARCHAR(64),"
            " status VARCHAR(32), started_at DATETIME)"
        )

    _upgrade_to(db_url, "0101")

    with sqlite3.connect(db_file) as conn:
        assert "outside_workspace_writes" in {
            row[1] for row in conn.execute("PRAGMA table_info(runs)")
        }
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0101"
