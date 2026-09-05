"""F287 vs F292: does `await db.refresh(row)` leave a lock that `drop_all` would wait on?

The question this answers is *not* whether the refresh is redundant (F287 established that by
reading three lines). It is the masking question the day playbook's D-6 carve-out demands before
touching it: F292 is an intermittent `database is locked` at the hub suite's *setup*, i.e. at the
`drop_all` in `hub/tests/conftest.py`'s `app` fixture, and if the refresh is part of what holds
that lock then deleting it would make F292 stop reproducing without anyone having explained it.

The suite's conditions are reproduced exactly: file-backed sqlite+aiosqlite, WAL,
`busy_timeout=30000` on the session connections (conftest.py:110-111), `expire_on_commit=False`
(engine.py:39), and the fixture's own sequence -- a session left un-closed by a previous test,
then `engine.dispose()`, then `drop_all`/`create_all` on a fresh connection.

Run: py -3.11 scripts/drive/f287_does_the_refresh_hold_a_lock.py
"""

import asyncio
import shutil
import sys
import tempfile
import time
from pathlib import Path

from sqlalchemy import Column, Integer, String, event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Row(Base):
    __tablename__ = "probe_row"
    id = Column(Integer, primary_key=True)
    content = Column(String)


def _make_engine(url: str):
    eng = create_async_engine(url, echo=False, connect_args={"check_same_thread": False})

    @event.listens_for(eng.sync_engine, "connect")
    def _pragmas(dbapi_connection, _record):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()

    return eng


async def scenario(tmp: Path, *, refresh: bool, ddl_busy_timeout_ms: int):
    """One leaked session, with or without the refresh, then the fixture's reset sequence."""
    db = tmp / f"probe-{'refresh' if refresh else 'norefresh'}.db"
    engine = _make_engine(f"sqlite+aiosqlite:///{db.as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # The leak: a session a background task opened and never closed, having just done
    # exactly what `record_agent_output` does.
    leaked = factory()
    row = Row(content="hello")
    leaked.add(row)
    await leaked.commit()
    if refresh:
        await leaked.refresh(row)

    raw_in_txn = None
    conn_obj = leaked.sync_session.connection() if leaked.in_transaction() else None
    if conn_obj is not None:
        raw = conn_obj.connection.dbapi_connection
        raw_in_txn = getattr(raw, "in_transaction", "n/a")

    facts = {
        "session.in_transaction()": leaked.in_transaction(),
        "pool.checkedout()": engine.pool.checkedout(),
        "sqlite3.Connection.in_transaction": raw_in_txn,
    }

    # The fixture's sequence, verbatim in shape: dispose, then DDL on a new connection.
    await engine.dispose()
    facts["pool.checkedout() after dispose"] = engine.pool.checkedout()

    ddl_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db.as_posix()}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(ddl_engine.sync_engine, "connect")
    def _ddl_pragmas(dbapi_connection, _record):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute(f"PRAGMA busy_timeout={ddl_busy_timeout_ms}")
        cur.close()

    started = time.monotonic()
    try:
        async with ddl_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        facts["drop_all+create_all"] = "OK"
    except Exception as exc:  # noqa: BLE001
        facts["drop_all+create_all"] = f"{type(exc).__name__}: {exc}"
    facts["ddl seconds"] = round(time.monotonic() - started, 3)

    await ddl_engine.dispose()
    with_ = leaked
    await with_.close()
    await engine.dispose()
    return facts


async def scenario_open_write(tmp: Path, ddl_busy_timeout_ms: int):
    """Control: a leaked session that wrote and did NOT commit -- an open WAL write lock."""
    db = tmp / "probe-openwrite.db"
    engine = _make_engine(f"sqlite+aiosqlite:///{db.as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    leaked = factory()
    leaked.add(Row(content="uncommitted"))
    await leaked.flush()  # INSERT issued, no COMMIT

    await engine.dispose()
    ddl_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db.as_posix()}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(ddl_engine.sync_engine, "connect")
    def _ddl_pragmas(dbapi_connection, _record):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute(f"PRAGMA busy_timeout={ddl_busy_timeout_ms}")
        cur.close()

    facts = {}
    started = time.monotonic()
    try:
        async with ddl_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        facts["drop_all"] = "OK"
    except Exception as exc:  # noqa: BLE001
        facts["drop_all"] = f"{type(exc).__name__}: {exc}"
    facts["ddl seconds"] = round(time.monotonic() - started, 3)
    await ddl_engine.dispose()
    await leaked.rollback()
    await leaked.close()
    await engine.dispose()
    return facts


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="f287-probe-"))
    try:
        for refresh in (True, False):
            facts = await scenario(tmp, refresh=refresh, ddl_busy_timeout_ms=1000)
            print(f"\n--- leaked session, refresh={refresh} ---")
            for k, v in facts.items():
                print(f"  {k}: {v}")
        facts = await scenario_open_write(tmp, ddl_busy_timeout_ms=1000)
        print("\n--- control: leaked session with an UNCOMMITTED write ---")
        for k, v in facts.items():
            print(f"  {k}: {v}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    print(sys.version)
    asyncio.run(main())
