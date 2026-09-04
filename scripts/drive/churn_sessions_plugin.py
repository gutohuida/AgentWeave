"""F285's in-suite reproduction: churn short-lived AsyncSessions while a test runs.

Not part of the suite. Loaded explicitly, and only to make a race deterministic:

    CHURN_DELAY=0.3 PYTHONPATH=scripts/drive py -3.11 -m pytest \
      hub/tests/test_a_turn_says_how_it_ended.py -p churn_sessions_plugin \
      -k stopped_run_persists

Each `async with async_session_factory() as s:` block returns its connection to the pool on exit,
and the pool resets a returned connection with ROLLBACK. Under the Hub suite's in-memory engine
that pool is a StaticPool — one DBAPI connection shared by every session — so the rollback lands on
whatever transaction a background run task has open. Churning sessions therefore produces on demand
the interleave CI hits by luck, and the run's `record_agent_output` dies at
`hub/hub/output_recording.py:94` with `InvalidRequestError: Could not refresh instance
'<AgentOutput ...>'` — the exact error the `hub-test` job reports.

`CHURN_DELAY` is when the churn starts, in seconds after the test body begins, and it matters. Too
early and the churn erases the fixtures' own seeding (the project row, the runner row) and the test
dies before it reaches the run. `0.3` lands on the run's output write on this machine; `0.25`,
`0.35` and `0.4` land earlier and fail the test on `assert 'running' == 'stopped'` instead, because
the churn also erased the stop path's status write. It is a race either way, so sweep the value
rather than trusting one.

The fixture depends on `app` so it cannot start before the database exists.
"""

import asyncio
import os

import pytest_asyncio
from sqlalchemy import select

START_DELAY = float(os.environ.get("CHURN_DELAY", "0.4"))


@pytest_asyncio.fixture(autouse=True)
async def _churn_sessions(app):
    from hub.db.engine import async_session_factory

    stop = asyncio.Event()

    async def _churn():
        await asyncio.sleep(START_DELAY)
        while not stop.is_set():
            async with async_session_factory() as session:
                await session.execute(select(1))
            await asyncio.sleep(0.002)

    task = asyncio.ensure_future(_churn())
    try:
        yield
    finally:
        stop.set()
        await asyncio.sleep(0)
        task.cancel()
