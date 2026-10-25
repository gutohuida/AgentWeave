"""The Hub opens SQLite in WAL with full sync, and still opens when WAL is refused.

`the-database-stays-fast-as-history-grows`, requirements `wal-on`, `wal-fallback` and `durable`.
These build their own engine the way the Hub builds its own (`engine.make_engine`), because the
suite's engine runs `synchronous=OFF` (`conftest._test_only_sqlite_pragmas`) and so cannot show
production's settings.
"""

from __future__ import annotations

import logging
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

from sqlalchemy import event, text

from hub.db import engine as engine_module
from hub.db import sqlite_pragmas


def _url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


def _refuse_wal(sync_engine) -> None:  # noqa: ANN001
    """Open every connection `nolock=1`, for which SQLite keeps its rollback journal (measured)."""

    @event.listens_for(sync_engine, "do_connect")
    def _nolock(dialect, record, cargs, cparams):  # noqa: ANN001
        cargs[0] = Path(cargs[0]).resolve().as_uri() + "?nolock=1"
        cparams["uri"] = True


async def _pragmas(conn) -> dict:  # noqa: ANN001
    return {
        name: (await conn.execute(text(f"PRAGMA {name}"))).scalar()
        for name in ("journal_mode", "synchronous", "journal_size_limit")
    }


async def test_every_pooled_connection_runs_wal_full_sync_and_a_wal_bound(tmp_path) -> None:
    eng = engine_module.make_engine(_url(tmp_path / "hub.db"))
    try:
        conns = [await eng.connect() for _ in range(3)]  # three distinct pooled connections at once
        try:
            readings = [await _pragmas(c) for c in conns]
        finally:
            for c in conns:
                await c.close()
    finally:
        await eng.dispose()
    assert (
        readings
        == [
            {
                "journal_mode": "wal",
                "synchronous": 2,
                "journal_size_limit": sqlite_pragmas.JOURNAL_SIZE_LIMIT_BYTES,
            }
        ]
        * 3
    )


def test_the_hubs_own_engine_carries_the_pragmas() -> None:
    assert event.contains(engine_module.engine.sync_engine, "connect", sqlite_pragmas._on_connect)


async def test_a_rollback_journal_database_runs_wal_once_the_hub_opens_it(tmp_path) -> None:
    path = tmp_path / "old.db"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE t (x)")
    c.execute("INSERT INTO t VALUES (1)")
    c.commit()
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    c.close()
    eng = engine_module.make_engine(_url(path))
    try:
        async with eng.connect() as conn:
            assert (await conn.execute(text("SELECT count(*) FROM t"))).scalar() == 1
    finally:
        await eng.dispose()
    c = sqlite3.connect(path)
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    c.close()


def test_the_migration_engine_opens_in_wal(tmp_path) -> None:
    """`migrations/env.py` builds its own engine; `alembic upgrade head` alone converts the file."""
    from alembic import command
    from alembic.config import Config

    path = tmp_path / "migrated.db"
    sqlite3.connect(path).close()
    cfg = Config(str(Path(engine_module.__file__).parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _url(path))
    from hub.config import settings

    original = settings.database_url
    settings.database_url = _url(path)
    try:
        command.upgrade(cfg, "head")
    finally:
        settings.database_url = original
    c = sqlite3.connect(path)
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    c.close()


async def test_a_refused_wal_still_serves_and_the_startup_line_names_the_journal(tmp_path) -> None:
    eng = engine_module.make_engine(_url(tmp_path / "share.db"))
    _refuse_wal(eng.sync_engine)
    try:
        async with eng.begin() as conn:
            await conn.execute(text("CREATE TABLE t (x)"))
            await conn.execute(text("INSERT INTO t VALUES (1)"))
        async with eng.connect() as conn:
            assert (await conn.execute(text("SELECT count(*) FROM t"))).scalar() == 1
            reading = await _pragmas(conn)
        line = await engine_module.describe_journal(eng)
    finally:
        await eng.dispose()
    assert reading["journal_mode"] == "delete"
    assert reading["synchronous"] == 2
    assert "journal mode delete" in line
    assert "WAL could not be set" in line


async def test_the_startup_line_names_wal_when_wal_is_set(tmp_path) -> None:
    eng = engine_module.make_engine(_url(tmp_path / "local.db"))
    try:
        line = await engine_module.describe_journal(eng)
    finally:
        await eng.dispose()
    assert "journal mode wal" in line
    assert "could not" not in line


async def test_lifespan_logs_the_journal_line(monkeypatch, caplog) -> None:
    """The line is emitted at WARNING from `lifespan` (the root logger is WARN after alembic)."""
    from hub import main

    async def _describe(eng=None) -> str:  # noqa: ANN001
        return "Hub database: journal mode delete (WAL could not be set)"

    monkeypatch.setattr(main, "describe_journal", _describe)
    with caplog.at_level(logging.WARNING, logger="hub.main"):
        await main.log_journal_mode()
    assert any("journal mode delete" in r.getMessage() for r in caplog.records)


_WRITER = textwrap.dedent("""
    import asyncio, os, sys
    sys.path.insert(0, {hub!r})
    from sqlalchemy import text
    from hub.db.engine import make_engine

    async def main():
        eng = make_engine({url!r})
        async with eng.begin() as conn:
            await conn.execute(text("CREATE TABLE IF NOT EXISTS tasks_t (id TEXT PRIMARY KEY)"))
        async with eng.begin() as conn:
            await conn.execute(text("INSERT INTO tasks_t VALUES ('survives')"))
        print("committed", flush=True)
        os._exit(9)  # no dispose, no checkpoint, no shutdown: the process just ends

    asyncio.run(main())
    """)


def test_a_committed_write_survives_the_process_being_killed(tmp_path) -> None:
    path = tmp_path / "durable.db"
    hub_dir = str(Path(engine_module.__file__).resolve().parents[2])
    proc = subprocess.run(
        [sys.executable, "-c", _WRITER.format(hub=hub_dir, url=_url(path))],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "committed" in proc.stdout, proc.stderr[-2000:]
    assert proc.returncode == 9
    assert Path(
        str(path) + "-wal"
    ).exists(), "the commit should still be in the WAL, uncheckpointed"
    c = sqlite3.connect(path)
    assert c.execute("SELECT id FROM tasks_t").fetchall() == [("survives",)]
    c.close()


def test_the_pragmas_are_sqlite_only() -> None:
    class _Dialect:
        name = "postgresql"

    class _Engine:
        dialect = _Dialect()

    sqlite_pragmas.install(_Engine())  # type: ignore[arg-type]  # no listener, no error


def test_apply_pragmas_survives_a_raising_wal_request() -> None:
    calls = []

    class _Cursor:
        def execute(self, sql):  # noqa: ANN001
            calls.append(sql)
            if "journal_mode" in sql:
                raise sqlite3.OperationalError("database is locked")

        def fetchone(self):
            return None

        def close(self):
            pass

    class _Conn:
        def cursor(self):
            return _Cursor()

    assert sqlite_pragmas.apply_pragmas(_Conn()) is None
    assert "PRAGMA synchronous=FULL" in calls
