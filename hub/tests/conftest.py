"""Shared test fixtures for AgentWeave Hub."""

import asyncio
import atexit
import contextlib
import os
import shutil
import sys
import tempfile
import warnings
import weakref
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Use a FILE-BACKED SQLite database for tests, in a directory this process makes and owns.
#
# It was `:memory:` until 2026-09-04, and that is what F285 was: SQLAlchemy's aiosqlite
# dialect picks the pool from the URL, and an in-memory URL gets a **StaticPool**, which
# hands *the same DBAPI connection* to every checkout with no in-use tracking. So every
# AsyncSession in the suite — a background run task's, and every HTTP request's
# `get_session` dependency — shared one connection and therefore one transaction, and
# returning a connection to the pool resets it, which means ROLLBACK. An HTTP request
# finishing was a rollback issued on the transaction a background task had open. Three
# tests failed on it in every CI run from 2026-09-03 to 2026-09-04, and the same defect
# made every concurrent-path test in the suite non-deterministic rather than just those.
#
# A file URL gets an `AsyncAdaptedQueuePool` — one connection per session, which is what
# production has always used (`hub/hub/config.py` defaults to a file and native mode sets
# DATABASE_URL to one). The two rejected alternatives were measured, not reasoned:
# `NullPool` on `:memory:` gives every session its own *empty* database, and a
# shared-cache memory URI is destroyed when its last connection closes. Both fail with
# `no such table`.
#
# The directory is per-process and removed at the end of the session, so concurrent runs
# cannot collide and a developer's TEMP does not accumulate a database per run. The
# `atexit` registration is only a backstop for a process that dies before
# `pytest_sessionfinish`; the ordered teardown that actually works is at the bottom of
# this file, because on Windows the directory cannot be removed until the engine has let
# go of the file.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="aw-hub-tests-")
atexit.register(shutil.rmtree, _TEST_DB_DIR, True)
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{(Path(_TEST_DB_DIR) / 'hub-test.db').as_posix()}"

# These are assignments, not `setdefault`. An inherited DATABASE_URL used to win here,
# and the `app` fixture below drops every table before each test — so running this suite
# from any shell that had one exported destroyed that database and still exited green.
# That is not a hypothetical shell: `_hub_native_start` (src/agentweave/cli.py) exports
# DATABASE_URL into the Hub's own environment, spawned agents inherited it, and this
# repository's instructions tell an agent to run `pytest hub/tests/`. So the environment
# most likely to run the suite was the one pointed at live operator data.

_inherited_database_url = os.environ.get("DATABASE_URL")
if _inherited_database_url and _inherited_database_url != TEST_DATABASE_URL:
    warnings.warn(
        f"Ignoring inherited DATABASE_URL={_inherited_database_url!r}. The Hub suite "
        f"always runs on {TEST_DATABASE_URL} because its fixtures drop every table.",
        stacklevel=1,
    )

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["AW_BOOTSTRAP_API_KEY"] = TEST_API_KEY = "aw_live_testkey_abcdefgh"

# The project nearly every test addresses. It used to arrive as a side effect of
# `init_db`, which created a project when AW_BOOTSTRAP_PROJECT_ID was set — the same
# mechanism that put a "Default Project" in front of operators who had an older .env.
# Startup now creates no project at all, so the suite makes its own.
TEST_PROJECT_ID = "proj-test"
TEST_PROJECT_NAME = "Test Project"

from sqlalchemy import event  # noqa: E402

from hub.db.engine import async_session_factory, engine, init_db  # noqa: E402
from hub.db.models import ApiKey, Base, Project  # noqa: E402
from hub.main import create_app  # noqa: E402 — env must be set first
from hub.project_workspace import (  # noqa: E402
    # A module-level constant holding the unpatched original, not a function alias.
    resolve_project_workspace as _REAL_RESOLVE_PROJECT_WORKSPACE,  # noqa: N812
)


@event.listens_for(engine.sync_engine, "connect")
def _test_only_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ANN001
    """Trade durability this database will never need for the speed of the one it replaced.

    Moving off `:memory:` to fix F285 put every `drop_all` + `create_all` — roughly 90
    tables, once per test, for 1,500+ tests — onto the filesystem, and measured on this
    machine that was about 2.5x the whole suite's wall clock. Almost all of it is fsync:
    SQLite defaults to `synchronous=FULL` and a rollback journal written to disk, both of
    which exist to survive power loss.

    This database is deleted when the process exits. It has nothing to survive for, so
    the syncs stop. What is *not* traded away is the thing the move was for: each session
    still gets its own connection from a real pool, which is what F285 was about. These
    pragmas are per-connection and set only here, in the suite — production keeps
    SQLite's defaults.

    WAL rather than the faster `journal_mode=MEMORY`, deliberately. Under a rollback
    journal a writer holds an exclusive lock across its commit and readers block on it,
    so the sessions this change exists to let run concurrently would contend for the file
    and some would surface `database is locked` after the busy timeout (30s here, raised
    from SQLite's 5s default because a schema reset waits on whatever a previous test left
    open). Trading F285's
    shared-connection rollback for a fresh `SQLITE_BUSY` flake class would be no fix at
    all. WAL lets readers proceed against the last committed snapshot while one writer
    appends, which is the concurrency the suite actually exercises.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA synchronous=OFF")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


# The real engine, bound once. `test_suite_database_isolation.py` monkeypatches this module's
# `engine` name with a stand-in to exercise the guard without binding to a file, and the teardown
# fixture below must dispose the actual engine rather than whatever the name points at mid-test.
# Same convention, and same reason, as `_REAL_RESOLVE_PROJECT_WORKSPACE` above.
_REAL_ENGINE = engine

#: How many cancel-and-gather passes the teardown below will make before it gives up. Three is the
#: product's own bound (`inbound_queue.DELIVERY_ATTEMPT_LIMIT`) on how long a failing entry can keep
#: re-scheduling its agent; the rest is headroom for several agents chaining at once.
_MAX_BACKGROUND_SETTLE_PASSES = 10


# ---------------------------------------------------------------------------
# F292 diagnostic - name the connection that holds the file at the schema reset.
#
# DIAGNOSTIC ONLY. Nothing below changes what any fixture *does*; it records who
# checked out each pooled connection and prints that record only when the schema
# reset actually fails. A green run is as quiet as it was before.
#
# Why the obvious diagnostic is not enough. F292 asked for "the pool's checked-out
# count immediately before the `drop_all`", and that number is *structurally blind*
# to the leak it is looking for - measured 2026-09-05, not reasoned:
# `AsyncEngine.dispose()` does not merely empty the pool, it **replaces** it, and the
# fresh pool's counters start at zero while a connection checked out from the old
# pool is still open and still holding the file. So a leaked writer is invisible to
# `pool.checkedout()` at exactly the line that wants to see it. Hence a registry of
# our own, fed by engine-level `checkout`/`checkin` events, which survive the
# replacement (SQLAlchemy re-applies engine-level pool listeners to the new pool, and
# the old pool keeps its own - so a connection checked out before the dispose still
# dispatches its checkin afterwards; both halves measured).
#
# What the registry answers that the count cannot: *which test* checked the surviving
# connection out. The failure lands at the setup of the next test, which is never the
# one that caused it - all three CI failures recorded in F292 blame a victim.
_CHECKED_OUT: "dict[int, tuple[str, tuple[str, ...], weakref.ref]]" = {}

#: The nodeid of the test currently running, stamped onto every checkout. Set from
#: `pytest_runtest_logstart` rather than from a fixture, so that fixture ordering
#: cannot mis-attribute a checkout made during setup.
_CURRENT_TEST = "<no test running>"

#: Frames from outside this repository are noise in a checkout origin.
_REPO_MARKER = f"{os.sep}hub{os.sep}"


def pytest_runtest_logstart(nodeid, location):  # noqa: ANN001, ANN201
    global _CURRENT_TEST
    _CURRENT_TEST = nodeid


def _current_task_label() -> str:
    """The asyncio task this checkout happened under, or why there is not one.

    F292's standing hypothesis is *"a fire-and-forget `asyncio` task created during the
    previous test"*. A task's name and the qualified name of its coroutine are what
    distinguish that from a checkout made on the test's own path, and neither is
    recoverable from a stack once the task is gone - so it is recorded here.
    """
    try:
        task = asyncio.current_task()
    except RuntimeError:  # pragma: no cover - diagnostic only
        return "<no running loop>"
    if task is None:  # pragma: no cover - diagnostic only
        return "<no task>"
    coroutine = task.get_coro()
    return f"{task.get_name()} running {getattr(coroutine, '__qualname__', '?')}"


def _checkout_origin():
    """A few frames of this checkout's caller, from this repository only.

    Deliberately a raw frame walk rather than `traceback.extract_stack`: the latter
    resolves source text through `linecache` for every frame, and this runs on every
    checkout in a 3,900-test suite. Filenames, line numbers and function names are
    what identify the caller; the source line is not needed.

    The greenlet hop is not optional, and the first version of this function did not
    have it: SQLAlchemy runs the synchronous half of every async call inside a greenlet
    (`util._concurrency_py3k.greenlet_spawn`), and a greenlet's frame chain **ends at
    its own entry point**. Walking `f_back` from a pool event therefore reaches the
    pool and stops, with the code that opened the session on the *parent* greenlet's
    stack and unreachable. Measured on a forced reproduction: without the hop the only
    frame this returned was the listener's own, which names nothing.
    """
    roots = [sys._getframe(2)]  # skip this function and the event listener that called it
    try:
        import greenlet

        current = greenlet.getcurrent()
        hops = 0
        while current is not None and hops < 5:
            current = current.parent
            hops += 1
            if current is not None and current.gr_frame is not None:
                roots.append(current.gr_frame)
    except Exception:  # pragma: no cover - diagnostic only
        pass

    frames = []
    for root in roots:
        frame = root
        depth = 0
        while frame is not None and depth < 80 and len(frames) < 6:
            filename = frame.f_code.co_filename
            if _REPO_MARKER in filename and "site-packages" not in filename:
                frames.append(f"{Path(filename).name}:{frame.f_lineno} {frame.f_code.co_name}")
            frame = frame.f_back
            depth += 1
    return tuple(frames)


@event.listens_for(engine.sync_engine, "checkout")
def _f292_record_checkout(dbapi_connection, connection_record, connection_proxy):  # noqa: ANN001
    _CHECKED_OUT[id(connection_record)] = (
        f"{_CURRENT_TEST} [task: {_current_task_label()}]",
        _checkout_origin(),
        weakref.ref(connection_record),
    )


@event.listens_for(engine.sync_engine, "checkin")
def _f292_record_checkin(dbapi_connection, connection_record):  # noqa: ANN001
    _CHECKED_OUT.pop(id(connection_record), None)


@event.listens_for(engine.sync_engine, "close")
def _f292_record_close(dbapi_connection, connection_record):  # noqa: ANN001
    _CHECKED_OUT.pop(id(connection_record), None)


def _in_transaction(connection_record) -> str:  # noqa: ANN001
    """Whether this record's connection has an open transaction, or why we cannot say.

    `aiosqlite.Connection.in_transaction` is a plain attribute read forwarding to the
    underlying `sqlite3.Connection`; it schedules nothing on the connection's worker
    thread or its event loop, so it is safe to read here even when the loop that
    created the connection is gone (measured 2026-09-05). Every failure mode is
    swallowed into the returned string - a diagnostic must not be able to replace the
    error it is diagnosing.
    """
    try:
        dbapi_connection = connection_record.dbapi_connection
        if dbapi_connection is None:
            return "closed"
        return "IN TRANSACTION" if dbapi_connection._connection.in_transaction else "idle"
    except Exception as exc:  # pragma: no cover - diagnostic only
        return f"unknown ({type(exc).__name__})"


def _f292_snapshot(stage: str) -> str:
    """One line of pool state, plus one line per connection this process still holds out."""
    lines = [f"  [{stage}] pool.status()={_REAL_ENGINE.sync_engine.pool.status()!r}"]
    if not _CHECKED_OUT:
        lines.append(f"  [{stage}] registry: no connection checked out")
        return "\n".join(lines)
    for nodeid, origin, record_ref in list(_CHECKED_OUT.values()):
        record = record_ref()
        state = "collected" if record is None else _in_transaction(record)
        lines.append(f"  [{stage}] held by {nodeid} -> {state}")
        for frame_line in origin:
            lines.append(f"  [{stage}]     at {frame_line}")
    return "\n".join(lines)


def _f292_report(*snapshots: str) -> str:
    return (
        "\n"
        + "=" * 78
        + "\nF292 DIAGNOSTIC: the schema reset failed. Who was holding the database:\n"
        + "\n".join(snapshots)
        + "\n(`pool.status()` after the dispose counts a *new* pool and cannot see a "
        "connection\nchecked out from the old one; the registry lines can. See F292 in "
        "scripts/drive/FINDINGS.md.)\n" + "=" * 78 + "\n"
    )


@pytest_asyncio.fixture(autouse=True)
async def _no_connection_outlives_its_event_loop():
    """Return every pooled connection at the end of each test, before its loop is gone.

    The other half of the F285 fix, and the half that is not obvious. A StaticPool held
    exactly one connection forever, so nothing was ever *reused across* tests — the bug
    was that everything shared it *within* one. Moving to a real pool fixed the sharing
    and introduced the reuse: `pytest-asyncio` builds a fresh event loop per test, an
    aiosqlite connection's futures belong to the loop that created them, and a pooled
    connection checked out by the next test is bound to a loop that no longer exists.

    Measured, before this fixture existed: 62 failures across 11 files, 57 of them
    `RuntimeError: await wasn't used with future` or `ValueError: The future belongs to
    a different loop`. None of them was a product defect; all of them were one
    connection outliving one event loop.

    `dispose()` here rather than `NullPool` on the engine, because the engine is built in
    product code (`hub/db/engine.py`) from the URL alone and takes no pool argument from
    a test. Disposing between tests keeps pooling *inside* a test — which is where the
    concurrency this change exists to support actually happens — and gives each test a
    pool with nothing carried over.
    """
    yield

    # Settle in-flight background runs BEFORE disposing, and the order is the whole point.
    # `_background_runs` is a module-level set in `agent_trigger`, so it outlives a test, and
    # `_await_background_run()` (test_agent_trigger.py:44) awaits *everything* in it rather
    # than only this test's tasks. Disposing the engine underneath a run still in flight takes
    # away the connection it needs to finish, so it never completes, never reaches the
    # `set.discard()` done-callback, and stays in the set — and the next test to call that
    # helper awaits a task belonging to an event loop that no longer exists.
    #
    # That is one failure (`test_the_timeline_reports_what_a_run_wrote_outside_its_workspace`),
    # it was caused by the dispose above rather than found by it, and cancelling first is what
    # makes the two safe together. A test that already cancelled its own runs leaves an empty
    # set and finds this a no-op.
    #
    # Cancelling is no longer terminal, which is why this settles to a fixed point instead of
    # doing one pass. Since F286 a run whose tail raises — cancellation included — hands its
    # input back and releases the queue, and that release can legitimately schedule the same
    # agent again (`turn_scheduler.redrain_queued_agents` -> `trigger_agent_directly`), which
    # registers a *new* task in this very set while the `gather` above it is still running. The
    # single pass ended in `_background_runs.clear()`, so that successor was dropped from the
    # set rather than settled: it stayed pending on an event loop that closed moments later, and
    # every subsequent test in the process died in this fixture on `task.cancel()` with
    # `RuntimeError: Event loop is closed`. Measured 2026-09-05 on `test_inbound_queue.py`
    # (`test_queue_status_probes_the_bound_runner_not_the_agent_name` leaks the task; the error
    # surfaces on the test *after* it), 10 errors across three files in one chunk.
    #
    # So: discard only what this pass actually settled, and loop while the set refills. The
    # chain is bounded in the product by `DELIVERY_ATTEMPT_LIMIT` (3) — an entry that keeps
    # failing is withdrawn rather than redelivered — so a handful of passes is a real fixed
    # point and not a hopeful one. The cap is a backstop against a future unbounded respawn,
    # and it fails loudly: a leak that poisons later tests is worth an error on the test that
    # leaked rather than a confusing one on the next.
    import hub.api.v1.agent_trigger as _agent_trigger

    for _ in range(_MAX_BACKGROUND_SETTLE_PASSES):
        leftover = list(_agent_trigger._background_runs)
        if not leftover:
            break
        for task in leftover:
            task.cancel()
        await asyncio.gather(*leftover, return_exceptions=True)
        # Not `clear()`: a successor scheduled during the `gather` is in the set by now, and
        # this pass has not settled it. The `set.discard()` done-callbacks fire via `call_soon`
        # and may not have run yet, so the settled tasks are removed here explicitly.
        _agent_trigger._background_runs.difference_update(leftover)
    else:
        still_running = list(_agent_trigger._background_runs)
        _agent_trigger._background_runs.clear()
        raise AssertionError(
            f"background runs did not settle in {_MAX_BACKGROUND_SETTLE_PASSES} passes; "
            f"{len(still_running)} still registered: {still_running!r}"
        )

    await _REAL_ENGINE.dispose()


def assert_engine_is_disposable() -> None:
    """Refuse to drop tables on any database this process did not create for itself.

    The backstop for the assignment above: the environment is only one way the engine
    can end up bound to real data (an edited conftest, a `.env` discovered from the
    working directory, a future embedder). Whatever the route, the cost of being wrong
    is a destroyed database that no test failure reports — so the check lives next to
    the destruction, not only next to the configuration.

    This used to require `":memory:" in url`, which was safe for the reason that made
    F285 possible: an in-memory database cannot be anybody's data. A file can be, so the
    guard now has to be positive rather than incidental — the database must live inside
    the temporary directory `_TEST_DB_DIR` that this process created moments ago. No
    operator database can be in there, and unlike the old check this one also rejects a
    file that merely *looks* like a test database.
    """
    # `make_url` rather than `engine.url.database`: the guard's own tests substitute a stand-in
    # engine whose `url` is a plain string, deliberately, so that checking the guard does not
    # require binding a real engine to a file. Parsing a string covers both.
    from sqlalchemy.engine import make_url

    url = str(engine.url)
    try:
        database = make_url(url).database
    except Exception:  # pragma: no cover - an unparseable URL is certainly not ours
        database = None
    inside_owned_tempdir = False
    if database:
        try:
            inside_owned_tempdir = Path(database).resolve().parent == Path(_TEST_DB_DIR).resolve()
        except OSError:  # pragma: no cover - an unresolvable path is simply not ours
            inside_owned_tempdir = False
    if not inside_owned_tempdir:
        raise RuntimeError(
            f"Refusing to run the Hub suite against {url!r}: its fixtures drop every "
            f"table, and this database is not the one this process created under "
            f"{_TEST_DB_DIR!r}. Unset DATABASE_URL and run again."
        )


assert_engine_is_disposable()


async def seed_test_project() -> None:
    """Create `proj-test` and its API key, before the seeders that iterate projects.

    Ordering is load-bearing: `init_db` seeds default runners and charters for every
    project it finds, so a project created afterwards would come up with neither.
    """
    async with async_session_factory() as session:
        session.add(Project(id=TEST_PROJECT_ID, name=TEST_PROJECT_NAME))
        session.add(
            ApiKey(id=TEST_API_KEY, project_id=TEST_PROJECT_ID, label="bootstrap", revoked=False)
        )
        await session.commit()


@pytest_asyncio.fixture
async def app(monkeypatch):
    application = create_app()

    # `init_db` runs `alembic upgrade head` for a file database and skips it for
    # `:memory:` — so moving this suite off `:memory:` for F285 would otherwise have
    # started applying ~90 migrations on every one of the 1,500+ tests that use this
    # fixture, against a schema `create_all` had just built. That is minutes of wall
    # clock per run and a swallowed WARNING per test, in exchange for nothing: the
    # suite's schema comes from `create_all`, which is what it has always come from.
    #
    # Patched here, per test, rather than on the module: `test_migrations.py` imports
    # `_run_alembic_upgrade` inside the one test that must see the real thing
    # (`test_init_db_runs_alembic_for_file_db`), and that test does not take this
    # fixture. A module-level swap would have silently turned it into a no-op assertion.
    import hub.db.engine as _engine_module

    async def _skip_alembic() -> None:
        return None

    monkeypatch.setattr(_engine_module, "_run_alembic_upgrade", _skip_alembic)

    # Empty the pool before the schema reset, not only after the test.
    #
    # `drop_all` is a schema change, and SQLite will not make one while another connection
    # holds the database open — in WAL that surfaces as `OperationalError: database is
    # locked` once the busy timeout expires, which is how CI failed at the *setup* of
    # `test_a_wedged_review_is_restaffed_to_a_real_reviewer` on Linux (run 33913450471,
    # 3957 passed, this the only error). The teardown fixture disposes after each test, but
    # a test that leaves a live `JobScheduler` — which that file does — can still be holding
    # a checked-out connection when the next test starts. Disposing here makes the reset
    # depend on this fixture rather than on the previous test having tidied up.
    #
    # This is contention the suite did not have on `:memory:`, where there were no file
    # locks at all. It is the cost of the pool that fixes F285, and it is paid here.
    _f292_before_dispose = _f292_snapshot("before dispose")
    await _REAL_ENGINE.dispose()
    _f292_before_drop = _f292_snapshot("before drop_all")

    # ASGITransport does not trigger the FastAPI lifespan, so we run init_db
    # (create_all + the instance operator credential) explicitly before each test.
    assert_engine_is_disposable()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
    except Exception:
        # The F292 diagnostic above, printed only on the failure path. pytest shows
        # captured stderr under "Captured stderr setup" for an ERROR at setup, which is
        # exactly where this failure lands.
        sys.stderr.write(
            _f292_report(_f292_before_dispose, _f292_before_drop, _f292_snapshot("at failure"))
        )
        raise
    await seed_test_project()
    await init_db()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer aw_live_testkey_abcdefgh"}


@pytest.fixture(autouse=True)
def _no_real_mcp_probe(monkeypatch):
    """Every agent trigger calls launchability.resolve_access_path, which (for
    claude/claude_proxy/native/codex) shells out to ``<cli> mcp list`` to check whether
    the agentweave MCP server is actually registered. The suite must not depend on a real
    CLI being installed/authenticated on the machine running it — default the probe to
    "not registered" (deterministic, no subprocess) so every test gets the "cli" access
    path unless it explicitly overrides this fixture's patch.
    """
    import hub.launchability as launchability

    monkeypatch.setattr(launchability, "probe_mcp_registered", lambda cli: False)


@pytest.fixture
def bind_runner(app, auth_headers):
    """Returns an async helper: `await bind_runner(agent_name, cli="claude")`.

    Creates a Runner and binds it to *agent_name*. Since runner-agent-charter-separation
    phase 1.3, `trigger_agent_directly` refuses to spawn an agent with no bound Runner —
    the old session/sync `agents.<name>.runner` string no longer selects which CLI/model
    to launch, only `Agent.runner_id` does. Any test that expects a real spawn (or to
    reach spawn-adjacent pre-flight checks) must bind one first, after the agent row
    exists (self-registered or session-synced).
    """

    async def _bind(agent_name, cli="claude", model=None):
        payload = {"name": f"{agent_name}-runner", "cli": cli}
        if model:
            payload["model"] = model
        created = await app.post(
            "/api/v1/projects/proj-test/runners", json=payload, headers=auth_headers
        )
        assert created.status_code == 201, created.text
        runner_id = created.json()["id"]
        bound = await app.patch(
            f"/api/v1/projects/proj-test/agents/{agent_name}",
            json={"runner_id": runner_id},
            headers=auth_headers,
        )
        assert bound.status_code == 200, bound.text
        return runner_id

    return _bind


@pytest.fixture
def drain_conversation():
    """Returns an async helper: `await drain_conversation(conversation_id)`.

    Marks a conversation's queued inbound entries delivered, standing in for a turn that
    actually consumed them. Archiving refuses while a conversation holds undelivered entries,
    so any test about what happens *after* archiving has to get past that guard first — and
    faking the state is honest here in a way that faking the guard would not be.
    """
    from sqlalchemy import update

    from hub.db.models import InboundQueueEntry

    async def _drain(conversation_id):
        async with async_session_factory() as session:
            await session.execute(
                update(InboundQueueEntry)
                .where(InboundQueueEntry.conversation_id == conversation_id)
                .values(state="delivered")
            )
            await session.commit()

    return _drain


@pytest.fixture(autouse=True)
def _no_real_worktree_provision(monkeypatch):
    """Every agent trigger calls worktrees.resolve_agent_workspace, which (for a
    writing agent) shells out to real `git worktree` commands against `Path.cwd()` —
    during this suite that's wherever `pytest` was invoked from, i.e. a real checkout,
    not a disposable fixture. Default to "no isolation" (return repo_root unchanged) so
    the suite never mutates real git state; `test_worktrees.py` and the dedicated
    integration tests in `test_agent_trigger.py`/`test_session_sync.py` restore the real
    function explicitly (via `monkeypatch.setattr`) against a `tmp_path` git repo instead.
    """
    import hub.worktrees as worktrees

    monkeypatch.setattr(
        worktrees, "resolve_agent_workspace", lambda repo_root, agent, config: repo_root
    )
    # A review turn resolves its workspace through `ensure_review_checkout` instead, which shells
    # out to `git worktree add --detach` — same hazard, same default. `test_review_checkout.py`
    # restores the real function against a `tmp_path` repository.
    monkeypatch.setattr(
        worktrees, "ensure_review_checkout", lambda repo_root, agent, sha: repo_root
    )
    # And a task-bound turn resolves through `ensure_task_worktree` — same hazard again. Stubbed
    # at that function rather than at `resolve_turn_workspace` deliberately: the resolver is what
    # decides *which* scheme a turn gets, so a test that restores the real
    # `resolve_agent_workspace` above still sees the real precedence, and only the git commands are
    # defaulted away. `test_turn_workspace.py` restores this against a `tmp_path` repository.
    monkeypatch.setattr(
        worktrees,
        "ensure_task_worktree",
        lambda repo_root, task_id, base, prerequisites=(): repo_root,
    )


@pytest.fixture(autouse=True)
def _default_project_workspace(monkeypatch, tmp_path):
    """Every agent-trigger, worktree, workspace-path, and session-sync endpoint now
    calls `project_workspace.resolve_project_workspace(session, project_id)` to root
    its filesystem operations in the project's real registered directory instead of
    the Hub process's `Path.cwd()`. The suite's bootstrap project (`proj-test`) is
    deliberately left unbound in the database by `init_db()` — `test_project_lifecycle.py`'s
    legacy-binding tests exercise binding it themselves via `ProjectLifecycleService`
    directly, bypassing this fixture entirely — so resolving it for real here would either
    break those tests or require every other test in the suite to explicitly register a
    directory just to trigger an agent.

    Default to resolving *any* project_id to this test's own disposable `tmp_path`,
    mirroring `_no_real_worktree_provision`'s "stub away the real thing by default"
    convention above. Tests exercising real, distinct project directories (worktrees,
    workspace paths, context materialization, session-sync worktree release) use the
    `bind_project_workspace` fixture below, which registers a real directory and
    restores the real resolver for that one test.
    """
    import hub.project_workspace as project_workspace

    async def _fake_resolve(session, project_id, *, hub_data_directory=None):
        del session, hub_data_directory
        return project_workspace.ProjectWorkspace(
            project_id=project_id, root=tmp_path, path_key=f"test:{project_id}"
        )

    monkeypatch.setattr(project_workspace, "resolve_project_workspace", _fake_resolve)


@pytest.fixture
def bind_project_workspace(monkeypatch):
    """Returns an async helper: `await bind_project_workspace(directory)`.

    Registers *directory* as the single unbound legacy project's (`proj-test`) real
    working directory through the same lifecycle path a genuine `agentweave` bare
    invocation uses, then restores the real `resolve_project_workspace` for the rest
    of this test — undoing `_default_project_workspace`'s fake above. Use this in place
    of the old `monkeypatch.chdir(repo)` pattern for any test whose real git repository
    must be what the Hub resolves as its project root.
    """
    import hub.project_workspace as project_workspace_module
    from hub.project_lifecycle import ProjectLifecycleService

    async def _bind(directory):
        async with async_session_factory() as session:
            project = await ProjectLifecycleService(session).open_existing(directory)
        monkeypatch.setattr(
            project_workspace_module, "resolve_project_workspace", _REAL_RESOLVE_PROJECT_WORKSPACE
        )
        return project

    return _bind


def pytest_sessionfinish(session, exitstatus):  # noqa: ANN001
    """Release the engine's connections, then delete the database this run created.

    Order matters on Windows: the temporary directory cannot be removed while the pool
    still holds the file open, and WAL adds `-wal` and `-shm` beside it. Disposing first
    is what makes the removal actually happen rather than fail silently into the
    `atexit` backstop registered at the top of this file.
    """
    # Teardown must never fail a green run, so every failure mode here is swallowed:
    # the `atexit` backstop and the operating system both clean up after us.
    with contextlib.suppress(Exception):
        asyncio.run(engine.dispose())
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)
