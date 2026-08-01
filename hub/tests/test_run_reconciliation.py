"""Tests for Hub-start crash reconciliation (task 3.8, design.md Decision 8).

`hub.run_reconciliation.reconcile_interrupted_runs()` is called directly rather than through
the FastAPI lifespan — `conftest.py`'s `app` fixture uses `ASGITransport`, which does not
trigger `lifespan()` (see its own comment), so these tests exercise the function itself, the
same way a real Hub restart would invoke it from `main.py`.
"""

import json
import os

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Run
from hub.inbound_queue import deliver_entries_with_run, new_entry, queued_entries
from hub.run_reconciliation import reconcile_interrupted_runs
from hub.sse import sse_manager


def _drain(queue):
    events = []
    while True:
        try:
            item = queue.get_nowait()
        except Exception:  # asyncio.QueueEmpty
            break
        events.append((item.event, json.loads(item.data)))
    return events


@pytest.mark.asyncio
async def test_run_with_no_pid_becomes_interrupted(app, auth_headers):
    # A Hub crash between "Run row created" and "pid assigned" (agent_trigger.py sets
    # run.pid only after PtySession.spawn() succeeds) leaves pid=None — there is nothing
    # to check liveness of, so this must always be reconciled.
    async with async_session_factory() as db:
        entry = new_entry(
            project_id="proj-test",
            agent="recon-nopid",
            origin_type="operator",
            content="recover me",
            hop_depth=0,
        )
        db.add(entry)
        await db.commit()
        await deliver_entries_with_run(
            db,
            project_id="proj-test",
            agent="recon-nopid",
            entry_ids=[entry.id],
            run=Run(
                id="run-recon-nopid",
                project_id="proj-test",
                agent="recon-nopid",
                status="running",
                pid=None,
                turn_depth=0,
            ),
        )

    queue = sse_manager.subscribe("proj-test")

    reconciled = await reconcile_interrupted_runs()
    assert reconciled >= 1

    async with async_session_factory() as db:
        run = await db.get(Run, "run-recon-nopid")
        assert run.status == "interrupted"
        assert run.ended_at is not None
        waiting = await queued_entries(db, "proj-test", "recon-nopid")
        assert [row.content for row in waiting] == ["recover me"]

    events = _drain(queue)
    interrupted = [
        d for t, d in events if t == "run_interrupted" and d["run_id"] == "run-recon-nopid"
    ]
    assert len(interrupted) == 1
    assert interrupted[0]["agent"] == "recon-nopid"


@pytest.mark.asyncio
async def test_run_with_dead_pid_becomes_interrupted(app, auth_headers):
    # A pid this large will not correspond to any real process on any platform this suite
    # runs on — `pid_alive()`'s own OS-level correctness is covered separately in
    # test_pty_runner.py::TestPidAlive using a real spawned-and-reaped process; this test
    # only needs "some pid that is not alive" to exercise the reconciliation query/branch.
    async with async_session_factory() as db:
        db.add(
            Run(
                id="run-recon-deadpid",
                project_id="proj-test",
                agent="recon-deadpid",
                status="running",
                pid=2_147_483_647,
            )
        )
        await db.commit()

    await reconcile_interrupted_runs()

    async with async_session_factory() as db:
        run = await db.get(Run, "run-recon-deadpid")
        assert run.status == "interrupted"


@pytest.mark.asyncio
async def test_run_with_live_pid_is_left_running(app, auth_headers):
    # The test process's own pid is guaranteed alive for the duration of this test.
    async with async_session_factory() as db:
        db.add(
            Run(
                id="run-recon-alive",
                project_id="proj-test",
                agent="recon-alive",
                status="running",
                pid=os.getpid(),
            )
        )
        await db.commit()

    await reconcile_interrupted_runs()

    async with async_session_factory() as db:
        run = await db.get(Run, "run-recon-alive")
        assert run.status == "running"
        assert run.ended_at is None


@pytest.mark.asyncio
async def test_reconciling_twice_is_idempotent(app, auth_headers):
    # Not "reconciled == 0" on a fresh DB: this shared test DB persists across the whole
    # pytest session (see conftest.py), and other test modules deliberately leave orphaned
    # "running" Run rows behind (e.g. test_agents.py's direct-spawn-status test) — a first
    # call here may legitimately reconcile leftovers from earlier tests. What must hold
    # regardless of what ran before this test is idempotency: once a pass has reconciled
    # everything it can see, an immediate second pass finds nothing left to do.
    await reconcile_interrupted_runs()
    second_pass = await reconcile_interrupted_runs()
    assert second_pass == 0
