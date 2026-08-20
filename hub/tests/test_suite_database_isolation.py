"""The suite must never be able to drop tables in a database that holds real data.

On 2026-08-20 an operator's live Hub database was destroyed by a test run: every
application table dropped, the recreate interrupted partway, and pytest exited green.
The route was `conftest.py`'s `os.environ.setdefault("DATABASE_URL", ...)`, which yields
to an inherited value, combined with the `app` fixture's `Base.metadata.drop_all`. The
Hub exports DATABASE_URL into its own environment and spawned agents inherited it, so
the process most likely to run this suite was the one aimed at live data.

These tests pin both halves of the fix: the engine this suite binds is in-memory, and
the guard that asserts it actually refuses a file database rather than warning about one.
"""

import re
from pathlib import Path

import pytest

from hub.db.engine import engine
from tests.conftest import TEST_DATABASE_URL, assert_engine_is_disposable


def test_suite_engine_is_in_memory():
    """The engine every fixture drops tables on holds no durable data."""
    assert ":memory:" in str(engine.url)


def test_guard_refuses_a_file_database(monkeypatch):
    """A file-backed engine must raise, not warn — the cost of proceeding is unrecoverable.

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
    """The in-memory URL the suite configures passes the same guard."""
    from tests import conftest

    class _MemoryEngine:
        url = TEST_DATABASE_URL

    monkeypatch.setattr(conftest, "engine", _MemoryEngine())
    assert assert_engine_is_disposable() is None


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
