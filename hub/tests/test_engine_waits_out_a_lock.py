"""F517 -- the Hub's engine waits out another writer's lock, as its migration engine already does.

Production SQLite runs a rollback journal with the driver's 5s busy timeout; the suite's pragma
listener (`conftest.py`) raises its own connections to WAL and 30s, so no test of the module engine
can see the production setting. These build a fresh engine from the same connect arguments the Hub
uses, on a file of their own, where no listener reaches.
"""

import sqlite3
import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hub.db import engine as engine_module


def _url(path) -> str:  # noqa: ANN001
    return f"sqlite+aiosqlite:///{path.as_posix()}"


@pytest.mark.asyncio
async def test_the_hubs_connections_wait_thirty_seconds_on_a_lock(tmp_path):
    url = _url(tmp_path / "hub.db")
    engine = create_async_engine(url, connect_args=engine_module.connect_args_for(url))
    try:
        async with engine.connect() as connection:
            waited = (await connection.execute(text("PRAGMA busy_timeout"))).scalar()
    finally:
        await engine.dispose()
    assert waited == 30000


def test_a_database_that_is_not_sqlite_gets_no_sqlite_arguments():
    assert engine_module.connect_args_for("postgresql+asyncpg://h/db") == {}


@pytest.mark.asyncio
async def test_a_write_waits_for_a_lock_held_longer_than_the_drivers_default(tmp_path):
    """The shape F517 met: another writer holds the file past 5s; the write lands after it."""
    path = tmp_path / "hub.db"
    with sqlite3.connect(path) as setup:
        setup.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, pid INTEGER)")
        setup.execute("INSERT INTO runs VALUES ('run-1', NULL)")

    held = threading.Event()

    def _hold_the_write_lock():
        holder = sqlite3.connect(path, isolation_level=None)
        holder.execute("BEGIN IMMEDIATE")
        held.set()
        time.sleep(6.0)
        holder.execute("COMMIT")
        holder.close()

    thread = threading.Thread(target=_hold_the_write_lock)
    thread.start()
    assert held.wait(5)

    url = _url(path)
    engine = create_async_engine(url, connect_args=engine_module.connect_args_for(url))
    try:
        async with engine.begin() as connection:
            await connection.execute(text("UPDATE runs SET pid = 4242 WHERE id = 'run-1'"))
    finally:
        await engine.dispose()
        thread.join()

    with sqlite3.connect(path) as check:
        assert check.execute("SELECT pid FROM runs").fetchone() == (4242,)
