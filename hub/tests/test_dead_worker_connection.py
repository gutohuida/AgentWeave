"""The dead-worker connection guard — `hub/hub/db/engine.py`, finding F295.

aiosqlite runs every statement for a connection on one dedicated worker thread. When
that thread ends, the connection is not slow and not merely errored: it accepts work,
never answers, and cannot even be closed, because closing is itself work for the thread
that ended. The guard is two pool listeners — `checkout` detects and raises
`DisconnectionError`, `close` neutralises so the resulting close returns.

**Every wait in this file is bounded.** The failure mode of a broken guard is a hang, and
an unbounded hang in CI is exactly what `F292` costs hours to. `_BOUND` is generous
enough that a slow machine never trips it and short enough that a real regression is a
failure rather than a stuck job.

**The worker is killed for real, never by monkeypatching `is_alive`.** `_kill_worker`
below is the mechanism aiosqlite itself hits when an event loop closes under a live
connection: a future belonging to a closed loop is handed to the worker, the worker
fails to report the result on that loop, fails again reporting *that* the same way, and
its `while True` ends (aiosqlite 0.22.1, `core.py:48-75`). Faking the thread's deadness
would prove the listener reads a boolean, not that the recovery works.

**Measured, and worth knowing before you read a red CI as a flake.** When the `close`
listener (task 1.5) regresses, `test_a_connection_whose_worker_thread_ended_is_never_...`
fails on its bounded wait as designed — and the *teardown* then hangs, because
`conftest.py`'s per-test `dispose()` is itself one of the closes that cannot return on a
dead-worker connection. `asyncio.wait_for` bounds this file's own awaits; nothing here
can bound a fixture's. So a regression of 1.5 costs a named failure followed by a stuck
job, which is the honest price of covering it at all and the reason 3.3 ships no variant
with that listener removed.

One interaction worth knowing when reading a failure here: `conftest.py` registers its
own `checkout`/`checkin`/`close` listeners on this same engine object for the F292
census, and the guard's listeners register first (at module import). So the guard's
`DisconnectionError` fires *before* `_f292_record_checkout`, and the census never
records the connections the guard discards. That is expected, not a fault.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.exc import InvalidRequestError

from hub.db.engine import (
    _neutralise_dead_worker_on_close,
    _refuse_dead_worker_connection,
    engine,
)

# Killing the worker leaves an unhandled exception in a thread, by construction — that is
# the very mechanism under test. Pytest reports it as a warning against whichever test is
# running; silence it here so a deliberate kill does not read as suite noise.
pytestmark = pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")

#: Every wait in this file. Seconds.
_BOUND = 15.0

#: What `conftest.py`'s test-only `connect` listener sets. Asserted rather than assumed,
#: so that changing it there fails here with a reason instead of silently weakening 3.7.
_TEST_BUSY_TIMEOUT_MS = 30000


def _kill_worker(dbapi_connection):  # noqa: ANN001, ANN202
    """End a pooled connection's aiosqlite worker thread the way a closed loop does.

    Returns the inner `aiosqlite.Connection`, with its thread confirmed dead.
    """
    inner = dbapi_connection._connection
    dead_loop = asyncio.new_event_loop()
    future = dead_loop.create_future()
    dead_loop.close()
    inner._tx.put((future, lambda: None))
    inner._thread.join(timeout=_BOUND)
    assert not inner._thread.is_alive(), (
        "the worker thread outlived the kill; the mechanism this file depends on has "
        "changed and every assertion below is now vacuous"
    )
    return inner


@contextlib.contextmanager
def _pool_events():
    """Record which connection each checkout handed out, and every new connection.

    Registered after the guard, so a checkout the guard refuses is never recorded — the
    list holds only connections that were actually handed to a caller.
    """
    checkouts: list = []
    connects: list = []

    def _on_checkout(dbapi_connection, connection_record, connection_proxy):  # noqa: ANN001
        checkouts.append(dbapi_connection)

    def _on_connect(dbapi_connection, connection_record):  # noqa: ANN001
        connects.append(dbapi_connection)

    event.listen(engine.sync_engine, "checkout", _on_checkout)
    event.listen(engine.sync_engine, "connect", _on_connect)
    try:
        yield checkouts, connects
    finally:
        event.remove(engine.sync_engine, "checkout", _on_checkout)
        event.remove(engine.sync_engine, "connect", _on_connect)


async def _scalar(statement: str):  # noqa: ANN202
    async with engine.connect() as conn:
        return (await conn.execute(text(statement))).scalar()


@pytest_asyncio.fixture(autouse=True)
async def _an_empty_pool():
    """Start with nothing pooled, so the connection killed below is the one reused next.

    Without this, a connection left by an earlier test could be handed out ahead of the
    victim and the guard would never be reached — the test would pass while asserting
    nothing.
    """
    await engine.dispose()
    yield


async def test_both_guard_listeners_are_registered_on_this_engine():
    """The decorators, not the functions — pins that the guard is actually wired up.

    The behavioural tests below reach the guard through the engine, so removing either
    `@event.listens_for` breaks them too; this one names which registration went missing
    and fails in milliseconds rather than on a bounded wait.
    """
    assert event.contains(engine.sync_engine, "checkout", _refuse_dead_worker_connection)
    assert event.contains(engine.sync_engine, "close", _neutralise_dead_worker_on_close)


async def test_a_connection_whose_worker_thread_ended_is_never_handed_out_again(caplog):
    """3.1 and 3.2: kill the worker for real, then assert the *recovery*, not the raise.

    A statement issued after the kill has to come back with a value from a new
    connection. Asserting only that the checkout raised would leave the case this
    finding is about — a caller that waits forever — untested.
    """
    with _pool_events() as (checkouts, connects):
        assert await asyncio.wait_for(_scalar("select 1"), timeout=_BOUND) == 1
        victim = checkouts[-1]
        connects_before = len(connects)

        inner = _kill_worker(victim)

        with caplog.at_level(logging.WARNING, logger="hub.db.engine"):
            recovered = await asyncio.wait_for(_scalar("select 2"), timeout=_BOUND)

    assert recovered == 2, "the statement after the kill did not return a real value"
    assert checkouts[-1] is not victim, "the dead connection was handed out again"
    assert len(connects) == connects_before + 1, "no replacement connection was opened"
    assert inner._thread.is_alive() is False

    guard_warnings = [record for record in caplog.records if record.name == "hub.db.engine"]
    assert len(guard_warnings) == 1, f"expected exactly one discard warning, got {guard_warnings}"
    message = guard_warnings[0].getMessage()
    assert "F295" in message
    assert "driver worker thread had ended" in message


async def test_the_discarded_connection_is_neutralised_and_not_merely_dropped():
    """3.3, as far as it can be pinned without leaving a hanging variant in the suite.

    The observable of the `close` listener (task 1.5) is that the discarded connection
    comes out of the recovery *neutralised* — `_running` false and `_connection` cleared
    — which is what makes every later close of it return instead of waiting on the ended
    thread. Removing that listener does not make this assertion false, it makes the
    recovery hang; that direction is confirmed out of band by a probe that removes the
    listener under `try`/`finally`, because an in-suite hanging variant is exactly what
    this file refuses to ship. See the night log for the measurement.
    """
    with _pool_events() as (checkouts, _connects):
        await asyncio.wait_for(_scalar("select 1"), timeout=_BOUND)
        victim = checkouts[-1]

        inner = _kill_worker(victim)
        assert inner._running is True
        assert inner._connection is not None

        await asyncio.wait_for(_scalar("select 1"), timeout=_BOUND)

    assert inner._running is False, "the discarded connection would still accept work"
    assert inner._connection is None, "closing the discarded connection could still wait"


async def test_a_healthy_checkout_is_untouched(caplog):
    """3.4: the guard is a predicate on a rare state, not a cost on every checkout."""
    with _pool_events() as (checkouts, connects):
        with caplog.at_level(logging.WARNING, logger="hub.db.engine"):
            assert await asyncio.wait_for(_scalar("select 1"), timeout=_BOUND) == 1
            first = checkouts[-1]
            connects_after_first = len(connects)
            assert await asyncio.wait_for(_scalar("select 1"), timeout=_BOUND) == 1

    assert checkouts[-1] is first, "a healthy pooled connection was not reused"
    assert len(connects) == connects_after_first, "a healthy checkout opened a connection"
    assert [record for record in caplog.records if record.name == "hub.db.engine"] == []


async def test_the_replacement_connection_is_configured_and_not_bare():
    """3.7: the forced reconnect re-fires the engine's `connect` listeners.

    Worth a test because the failure would be silent. A guard that recovers onto a
    connection carrying SQLite's 5s default busy timeout, where every other connection in
    the suite carries 30s, does not read as a bug — it reads as a new flake class.
    """
    with _pool_events() as (checkouts, connects):
        baseline = await asyncio.wait_for(_scalar("PRAGMA busy_timeout"), timeout=_BOUND)
        assert baseline == _TEST_BUSY_TIMEOUT_MS, (
            "conftest's connect listener no longer sets the busy timeout this test reads "
            "as its evidence of configuration"
        )
        victim = checkouts[-1]
        connects_before = len(connects)

        _kill_worker(victim)

        replacement = await asyncio.wait_for(_scalar("PRAGMA busy_timeout"), timeout=_BOUND)

    assert len(connects) == connects_before + 1, "no replacement connection was opened"
    assert replacement == _TEST_BUSY_TIMEOUT_MS, (
        "the replacement connection came back bare — the engine's connect listeners did "
        "not re-fire for it"
    )


async def test_dispose_returns_when_a_pooled_connection_has_a_dead_worker():
    """3.10: the test that would have caught R1's and R2's siting mistake.

    Both earlier rounds put the neutralisation *inline in the checkout listener*, which
    covers exactly one of the paths that close such a connection. `dispose()` is another
    one, it is reached at shutdown by `hub/hub/main.py`'s teardown, and the connection it
    has to close was never checked out — so no checkout listener, however careful, ever
    sees it. With the neutralisation on the `close` pool event instead, this returns.

    **The `wait_for` here does not actually bound this await, and that is measured.**
    With 1.5 reverted, `asyncio.wait_for(engine.dispose(), timeout=15)` never raises: the
    dispose reaches aiosqlite through SQLAlchemy's greenlet bridge and the cancellation
    does not land, so the run hangs rather than failing (`probe_310_wait_for_bound.py`,
    2026-09-09 — no return in 60s against a 5s bound; with 1.5 in place, 0.00s). The
    `wait_for` stays because it costs nothing and bounds every *other* way this could go
    wrong; what it cannot do is turn a 1.5 regression into a named failure. That price is
    the same one the module docstring above records, and it is the reason this file
    ships no variant with the listener removed. The pool-identity assertion is what stops
    a `dispose()` that silently did nothing from passing.
    """
    with _pool_events() as (checkouts, _connects):
        await asyncio.wait_for(_scalar("select 1"), timeout=_BOUND)
        victim = checkouts[-1]

    # Idle in the pool, not checked out: `_scalar`'s `async with` returned it above.
    inner = _kill_worker(victim)
    pool_before = engine.pool

    await asyncio.wait_for(engine.dispose(), timeout=_BOUND)

    assert (
        engine.pool is not pool_before
    ), "dispose() returned without replacing the pool — it cannot have disposed anything"
    assert inner._running is False, "the pooled connection was not neutralised on its close"
    assert inner._connection is None


async def test_the_exhausted_retry_path_raises_instead_of_hanging():
    """3.11: every replacement born dead — the caller gets an error, not a wait.

    **This covers a state that cannot occur in the Hub today, deliberately.** A
    replacement connection is always `__connect()`-fresh, so its worker is alive; the
    only way to reach the exhausted-retry branch is to break every new connection on
    purpose, which is what the `connect` listener below does. Do not delete this as dead
    weight, and do not read it as evidence that the state occurs — it exists because the
    branch's *failure* mode would be a caller waiting forever, and a bounded wait is the
    only way to say out loud that it is not.

    SQLAlchemy 2.0.50 retries a `DisconnectionError` from a checkout listener twice
    (`pool/base.py`, `_ConnectionFairy._checkout`) and then raises
    `InvalidRequestError("This connection is closed")`. The listener registers after
    `conftest`'s `connect` listener, so the busy-timeout PRAGMA still runs on a live
    worker and only then is the worker killed.
    """
    killed: list = []

    def _kill_every_new_connection(dbapi_connection, connection_record):  # noqa: ANN001
        killed.append(_kill_worker(dbapi_connection))

    event.listen(engine.sync_engine, "connect", _kill_every_new_connection)
    try:
        with pytest.raises(InvalidRequestError):
            await asyncio.wait_for(_scalar("select 1"), timeout=_BOUND)
    finally:
        event.remove(engine.sync_engine, "connect", _kill_every_new_connection)
        await asyncio.wait_for(engine.dispose(), timeout=_BOUND)

    assert len(killed) >= 2, (
        "the checkout was refused without a single reconnection attempt; the retry path "
        "this test exists for was never entered"
    )
