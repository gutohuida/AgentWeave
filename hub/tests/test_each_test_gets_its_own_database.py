"""F292: a connection a previous test left holding the database cannot lock the next test out.

F292 errored 1 CI run in 4-5 at the *setup* of a test, `database is locked` on the schema reset's
`BEGIN IMMEDIATE`, and the ledger measured the holder as already present when the reset begins: a
connection with an uncommitted write that `dispose()` cannot reach. Nine instruments never named
the task that owns it. `conftest.py` now gives every `app` test its own database file, so the
holder is holding a file nobody opens again.

The holder here is a raw `sqlite3` connection with a write open on the file the current test was
given. That is the shape the ledger reproduced in isolation on 2026-09-06 (a session holding an
uncommitted write fails the reset "byte for byte the error CI reports, at the same statement"). It
does not reproduce F292 from the suite, which nobody has managed locally; it asserts the reset no
longer shares a file with anything earlier.

Mutation-checked 2026-09-21, two ways. Removing `_move_to_a_fresh_database_file()` from the `app`
fixture fails `test_the_next_app_test_is_on_a_different_file`. Removing it from the sequence in
`test_a_held_write_...` fails that test with `database is locked` on `BEGIN IMMEDIATE` after the
30-second busy timeout -- CI's F292 signature, statement included.
"""

import sqlite3
from pathlib import Path

import pytest

import tests.conftest as suite
from hub.db.engine import engine
from hub.db.models import Base

_SEEN_FILES: list[str] = []


@pytest.mark.asyncio
async def test_each_app_test_opens_a_file_no_earlier_test_opened(app):
    _SEEN_FILES.append(suite._current_test_db_file)
    assert Path(suite._current_test_db_file).parent == Path(suite._TEST_DB_DIR)
    assert Path(suite._current_test_db_file).exists()


@pytest.mark.asyncio
async def test_the_next_app_test_is_on_a_different_file(app):
    assert _SEEN_FILES, "the test above must run first, in file order"
    assert suite._current_test_db_file != _SEEN_FILES[-1]


@pytest.mark.asyncio
async def test_a_held_write_on_the_previous_file_does_not_block_the_next_reset(app):
    holder = sqlite3.connect(suite._current_test_db_file, timeout=0)
    try:
        holder.execute("BEGIN IMMEDIATE")
        holder.execute("CREATE TABLE f292_holder (x)")

        # Exactly the `app` fixture's own sequence, with the holder still open.
        await suite._REAL_ENGINE.dispose()
        suite._move_to_a_fresh_database_file()
        async with engine.begin() as connection:
            await connection.exec_driver_sql("BEGIN IMMEDIATE")
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await suite.seed_test_project()
    finally:
        holder.rollback()
        holder.close()
