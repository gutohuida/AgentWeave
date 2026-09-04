"""The suite must never be able to drop tables in a database that holds real data.

On 2026-08-20 an operator's live Hub database was destroyed by a test run: every
application table dropped, the recreate interrupted partway, and pytest exited green.
The route was `conftest.py`'s `os.environ.setdefault("DATABASE_URL", ...)`, which yields
to an inherited value, combined with the `app` fixture's `Base.metadata.drop_all`. The
Hub exports DATABASE_URL into its own environment and spawned agents inherited it, so
the process most likely to run this suite was the one aimed at live data.

These tests pin both halves of the fix: the engine this suite binds is one this process
created for itself, and the guard that asserts it actually refuses any other database
rather than warning about one.

The first half was `":memory:" in url` until 2026-09-04. That was safe for an incidental
reason — an in-memory database cannot be anybody's data — and the same URL was the cause
of F285, because SQLAlchemy gives an in-memory URL a StaticPool: one DBAPI connection
shared by every session, so one session closing rolled back another's open transaction.
The suite is now file-backed inside a per-process temporary directory, which restores a
real connection pool and makes the safety property explicit rather than incidental.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool

from hub.db.engine import engine
from tests.conftest import _TEST_DB_DIR, TEST_DATABASE_URL, assert_engine_is_disposable


def test_suite_engine_is_a_database_this_process_created():
    """The engine every fixture drops tables on cannot be one that holds real data."""
    database = engine.url.database
    assert database is not None
    assert Path(database).resolve().parent == Path(_TEST_DB_DIR).resolve()


def test_suite_engine_does_not_share_one_connection_across_sessions():
    """F285: a StaticPool hands the same connection to every session, so any session
    closing issues a ROLLBACK on whatever another session has open.

    This is the assertion that would have caught F285 before CI did. It is about the
    pool rather than the URL because the pool is the thing that broke: the URL only
    selects it. An in-memory URL gets a StaticPool; a file URL gets a real pool.
    """
    assert not isinstance(engine.pool, StaticPool), (
        "The suite's engine shares one connection across every session (F285). "
        "Concurrent-path tests become non-deterministic and a finishing request can "
        "roll back a background run's transaction."
    )


def test_guard_refuses_an_operator_database(monkeypatch):
    """An engine bound outside this process's own temp directory must raise, not warn —
    the cost of proceeding is unrecoverable.

    Patches the name the guard reads rather than rebuilding the real engine, so the
    check is exercised without this test itself binding to a file.
    """
    from tests import conftest

    class _FileEngine:
        url = "sqlite+aiosqlite:///C:/Users/someone/.agentweave/hub/data/agentweave.db"

    monkeypatch.setattr(conftest, "engine", _FileEngine())

    with pytest.raises(RuntimeError, match="Refusing to run the Hub suite"):
        assert_engine_is_disposable()


def test_guard_accepts_the_suite_url(monkeypatch):
    """The URL the suite configures passes the same guard."""
    from tests import conftest

    class _SuiteEngine:
        url = TEST_DATABASE_URL

    monkeypatch.setattr(conftest, "engine", _SuiteEngine())
    assert assert_engine_is_disposable() is None


def test_guard_refuses_a_file_that_merely_looks_like_a_test_database(monkeypatch):
    """The guard is a positive check, not a name match.

    The old `":memory:" in url` test could not distinguish databases at all — every file
    was refused. Now that files are accepted, "is it inside the directory this process
    made" has to do that work, so a plausible-looking test database somewhere else must
    still be refused.
    """
    from tests import conftest

    class _DecoyEngine:
        url = "sqlite+aiosqlite:///C:/Users/someone/hub-test.db"

    monkeypatch.setattr(conftest, "engine", _DecoyEngine())

    with pytest.raises(RuntimeError, match="Refusing to run the Hub suite"):
        assert_engine_is_disposable()


def test_conftest_assigns_database_url_rather_than_defaulting_to_it():
    """`setdefault` is what let an inherited DATABASE_URL through — it must not come back.

    A source-level assertion, deliberately: the behaviour it protects cannot be observed
    from inside a session whose conftest has already been imported and its environment
    already set.
    """
    source = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")
    assert 'os.environ["DATABASE_URL"] = TEST_DATABASE_URL' in source
    assert not re.search(r"setdefault\(\s*[\"']DATABASE_URL", source)


def test_spawned_runs_do_not_inherit_the_hub_database_url():
    """The other half of the fix, asserted where the stripping is written.

    `test_agent_trigger.py` proves it end to end through a real spawn; this states the
    requirement in the file that explains why it exists, so deleting the pop is caught
    even if the trigger test is refactored.
    """
    source = (Path(__file__).parents[1] / "hub" / "api" / "v1" / "agent_trigger.py").read_text(
        encoding="utf-8"
    )
    for variable in ("DATABASE_URL", "AW_BOOTSTRAP_API_KEY", "AW_TICKET_SECRET"):
        assert f'env.pop("{variable}", None)' in source
