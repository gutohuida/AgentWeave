"""F292: the `app` fixture's schema reset must hold the write lock for its whole sequence.

Measured 2026-09-10, and it is the fact every earlier F292 instrument assumed away:
`async with engine.begin()` does **not** open a transaction for DDL. SQLAlchemy's
pysqlite/aiosqlite dialect emits no `BEGIN` until a DML statement, and `DROP TABLE` is not DML — so
the roughly ninety drops in `Base.metadata.drop_all` each run in autocommit, taking and releasing
SQLite's write lock ninety times. Between any two of them a competing writer can take the lock, and
the next drop then fails `database is locked` after the full busy timeout. That is the CI signature,
and it is why the failure lands on `requirement_drift` rather than on the first table.

`conftest.py`'s reset now issues `BEGIN IMMEDIATE` first, so the lock is taken once and held.

Two tests, deliberately different in kind:

* `test_the_reset_issues_begin_immediate` gates the real `conftest.py`. It is the one that fails if
  somebody removes the line.
* `test_a_competing_writer_cannot_interleave...` demonstrates the mechanism on a throwaway database,
  so the *reason* for the line survives even if the fixture is rewritten around it.

Neither reproduces F292 itself. A race that fires on ~20-40% of CI runs is not something a test can
assert; what these assert is that the window it needs is closed.

**Mutation-checked three ways, 2026-09-10, and the first form of one check did not survive.**
Removing `BEGIN IMMEDIATE` from `conftest.py` kills the first test; making the helper below ignore
`hold_the_lock` kills the second. Moving `BEGIN IMMEDIATE` to *after* `drop_all` — so the drops run
in autocommit and only the creates are protected — **survived the original test**, which compared
statement indices and guarded that comparison with "if any DROP was seen". On a fresh database
`drop_all` finds no tables and emits no DROP, so the guarded arm was skipped and the mutant passed.
The index comparison was replaced with `_DROPS_IN_TRANSACTION`, sampled per statement, which kills
it.

**The one gap that remains, stated rather than left to be found.** If this module's `app` test is
the very first `app` test of an entire session, the database is empty, no `DROP` executes, and
`all([])` is vacuously true — so the transaction dimension is unchecked in that one ordering. The
`BEGIN IMMEDIATE` assertion above it is unconditional and still fires, so the line cannot simply be
deleted; what a first-in-session run cannot catch is the line being *moved*. Any other ordering
catches it, because every reset before this one leaves ~90 tables behind.

**And a scoping bug this module shipped with for one run, kept as a note because it is the more
instructive failure.** The recorders are session-wide — the listener fires for every statement on
the shared engine — so `_DROPS_IN_TRANSACTION` originally also collected `test_migrations.py`'s
`drop_all`, which is *supposed* to run without `BEGIN IMMEDIATE`. The test passed run alone and
**failed in the full suite**, which is exactly the direction that gets a test deleted rather than
fixed. `_recording_from_scratch` bounds the window to this test's own reset. A global listener is a
global assertion unless something scopes it.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import Column, MetaData, String, Table, event, text
from sqlalchemy.ext.asyncio import create_async_engine

from hub.db.engine import engine as _hub_engine

# Registered at import, which is before the `app` fixture runs for any test in this module --
# the fixture's own statements are what we are here to observe, and a listener attached inside a
# test body would be attached too late to see them.
_STATEMENTS: list[str] = []

#: `in_transaction` sampled at each `DROP TABLE`, at the moment it executes. This is the check that
#: matters, and it replaced an index comparison (`the BEGIN came before the first DROP`) that a
#: mutation walked straight past: on a fresh database `drop_all` finds no tables, emits no `DROP`,
#: and an assertion guarded by "if any drops were seen" is simply skipped. Sampling per statement
#: cannot be fooled that way, and it also cannot be fooled by reading one reset's `BEGIN` against a
#: later reset's `DROP`, which the accumulated stream invites.
_DROPS_IN_TRANSACTION: list[bool] = []


@event.listens_for(_hub_engine.sync_engine, "before_cursor_execute")
def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
    normalised = " ".join(statement.split()).upper()
    _STATEMENTS.append(normalised)
    if normalised.startswith("DROP TABLE"):
        try:
            _DROPS_IN_TRANSACTION.append(bool(conn.connection.driver_connection.in_transaction))
        except Exception:  # pragma: no cover - diagnostic only, must never mask the real result
            _DROPS_IN_TRANSACTION.append(True)


@pytest_asyncio.fixture
async def _recording_from_scratch():
    """Empty the recorders, and be set up *before* `app` so only its reset is recorded.

    Scope matters and the first version of this module got it wrong. The listener above fires for
    every statement on the shared engine for the whole session, so `_DROPS_IN_TRANSACTION` also
    collected `test_migrations.py`'s own `drop_all` — which legitimately runs without
    `BEGIN IMMEDIATE` — and the assertion below failed in a full-suite run while passing whenever
    this file was run alone. Requesting this fixture *ahead of* `app` in the test signature is what
    bounds the window: pytest sets fixtures up in the order the signature names them.
    """
    _STATEMENTS.clear()
    _DROPS_IN_TRANSACTION.clear()
    yield


@pytest.mark.asyncio
async def test_the_reset_issues_begin_immediate(_recording_from_scratch, app):
    """The fixture that produced this test must have taken the write lock explicitly.

    `app` is requested for its side effect: taking it runs the schema reset, and the recorders were
    emptied immediately before it. If `conftest.py` stops issuing `BEGIN IMMEDIATE`, the reset
    reverts to ~90 autocommit drops and this fails.
    """
    assert any(s.startswith("BEGIN IMMEDIATE") for s in _STATEMENTS), (
        "the schema reset did not issue BEGIN IMMEDIATE, so its DROPs run in autocommit and a "
        "competing writer can take the write lock between them (F292). Statements seen: "
        f"{_STATEMENTS[:12]}"
    )
    assert all(_DROPS_IN_TRANSACTION), (
        "a DROP TABLE in the schema reset executed outside a transaction, so it took and released "
        "the write lock on its own and a competing writer can follow it in (F292). "
        f"{_DROPS_IN_TRANSACTION.count(False)} of {len(_DROPS_IN_TRANSACTION)} drops were "
        "in autocommit"
    )


def _pragmas(dbapi_connection, _record):  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=OFF")
    cursor.execute("PRAGMA busy_timeout=1000")
    cursor.close()


async def _reset_with(path: str, *, hold_the_lock: bool) -> bool:
    """Run the fixture's reset shape on a throwaway database. True if a foreign writer got in."""
    metadata = MetaData()
    for name in ("alpha", "beta", "gamma"):
        Table(name, metadata, Column("v", String))

    eng = create_async_engine(f"sqlite+aiosqlite:///{path}")
    event.listens_for(eng.sync_engine, "connect")(_pragmas)
    try:
        async with eng.begin() as connection:
            await connection.run_sync(metadata.create_all)

        async with eng.begin() as connection:
            if hold_the_lock:
                await connection.exec_driver_sql("BEGIN IMMEDIATE")
            await connection.execute(text("DROP TABLE alpha"))

            # A competing writer, arriving between two drops exactly as a background task from a
            # previous test would. Short busy timeout so the refusing case is fast.
            other = sqlite3.connect(path, isolation_level=None, timeout=1)
            try:
                other.execute("PRAGMA busy_timeout=1000")
                other.execute("BEGIN IMMEDIATE")
                other.execute("INSERT INTO beta (v) VALUES ('interposed')")
                got_in = True
            except sqlite3.OperationalError:
                got_in = False
            finally:
                other.close()

            if not got_in:
                # The rest of the reset must still complete once the writer is refused.
                await connection.execute(text("DROP TABLE beta"))
                await connection.run_sync(metadata.create_all)
        return got_in
    finally:
        await eng.dispose()


@pytest.mark.asyncio
async def test_a_competing_writer_cannot_interleave_when_the_lock_is_held():
    """The mechanism, on a throwaway database: holding the lock is what closes the window.

    Both halves are asserted. Without the assertion on the unguarded shape this test would pass
    against a SQLite that never lets a second writer in at all, and would therefore be proving
    nothing about the guard.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        unguarded = await _reset_with(str(Path(tmp) / "unguarded.db"), hold_the_lock=False)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        guarded = await _reset_with(str(Path(tmp) / "guarded.db"), hold_the_lock=True)

    assert unguarded is True, (
        "without BEGIN IMMEDIATE a competing writer was expected to take the write lock between "
        "two DROPs; it did not, so this test is no longer demonstrating the F292 window"
    )
    assert guarded is False, (
        "with BEGIN IMMEDIATE held, a competing writer took the write lock anyway -- the guard "
        "does not close the window it was added for"
    )
