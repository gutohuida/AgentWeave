"""Integration tests for the rewritten POST /api/v1/agent/trigger (task 3.5).

`PtySession.spawn` is mocked throughout — these tests exercise the endpoint's request
handling, pre-flight checks, and background execution/recording loop, not the real CLIs
(those are covered live — see tasks.md's task 3.5 entry — and by test_runner_parsing.py's
fixtures, which use real captured output).
"""

import asyncio
import json
import time
from unittest.mock import MagicMock, patch

import pytest

import hub.api.v1.agent_trigger as agent_trigger
from hub.sse import sse_manager


async def _await_background_run():
    """Wait for whatever background run task(s) the last trigger call started."""
    tasks = list(agent_trigger._background_runs)
    for task in tasks:
        await task


async def _wait_for_active_pty(run_id, timeout=2.0):
    """Poll until `_execute_run` has registered *run_id*'s PtySession.

    The stop endpoint can only reach a run's process via `agent_trigger._active_ptys`,
    which the background task populates asynchronously after `trigger_agent`'s HTTP
    response has already returned (unlike the Run row's "running" status, which is
    committed synchronously in the request handler itself) — so a test calling stop
    right after trigger must wait for this, not assume it's already there.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if run_id in agent_trigger._active_ptys:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} never registered an active pty")


def _fake_pty(lines, exit_code=0, pid=4242):
    """Build a mock PtySession.spawn() replacement streaming `lines` then EOF."""
    session = MagicMock()
    session.pid = pid
    session.read.side_effect = [*lines, ""]
    session.wait.return_value = exit_code
    return MagicMock(return_value=session)


@pytest.mark.asyncio
async def test_manual_runner_is_rejected_with_409(app, auth_headers):
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"offline-agent": {"runner": "manual"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    resp = await app.post(
        "/api/v1/agent/trigger",
        json={"agent": "offline-agent", "message": "hi", "session_mode": "new"},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "manual" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_resume_without_session_id_is_rejected(app, auth_headers):
    resp = await app.post(
        "/api/v1/agent/trigger",
        json={"agent": "claude", "message": "hi", "session_mode": "resume"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "session_id" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_session_mode_is_rejected(app, auth_headers):
    resp = await app.post(
        "/api/v1/agent/trigger",
        json={"agent": "claude", "message": "hi", "session_mode": "sideways"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_successful_trigger_returns_run_id_and_spawns(app, auth_headers):
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"trigger-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    fake_spawn = _fake_pty(
        [
            '{"type":"system","subtype":"init","session_id":"sess-live-1"}\n',
            '{"type":"assistant","message":{"content":[{"type":"text","text":"Hi there"}]},'
            '"session_id":"sess-live-1"}\n',
            '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-live-1"}\n',
        ]
    )
    # Nested, not parenthesized multi-context `with`: this suite's linter targets
    # Python 3.8 (see test_hub_commands.py's identical comment) — parenthesized
    # multi-context managers are 3.9+ only.
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/agent/trigger",
                json={"agent": "trigger-claude", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["status"] == "running"
            assert data["run_id"].startswith("run-")
            run_id = data["run_id"]

            await _await_background_run()

    output_resp = await app.get("/api/v1/agents/trigger-claude/output", headers=auth_headers)
    assert output_resp.status_code == 200
    rows = output_resp.json()
    assert any(row["content"] == "Hi there" for row in rows)
    assert any(row["run_id"] == run_id for row in rows)


@pytest.mark.asyncio
async def test_second_trigger_while_first_is_running_is_rejected(app, auth_headers):
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"busy-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    # A spawn whose read() never returns EOF on its own — simulates a run still in
    # progress when the second trigger request arrives.
    # Genuinely blocks .read() in the executor thread until released — a MagicMock
    # returning "" immediately completes the background task before the second request
    # even runs (it's all one event loop, no real process), which would make this test
    # flaky/meaningless. A real block is the only way to deterministically catch the Run
    # row still in "running" state when the second request's concurrency guard reads it.
    import threading

    release = threading.Event()

    def _blocking_read(size=4096):
        release.wait()
        return ""

    hanging_session = MagicMock()
    hanging_session.pid = 999
    hanging_session.read.side_effect = _blocking_read
    hanging_session.wait.return_value = 0

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=hanging_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            try:
                first = await app.post(
                    "/api/v1/agent/trigger",
                    json={"agent": "busy-claude", "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert first.status_code == 200

                second = await app.post(
                    "/api/v1/agent/trigger",
                    json={"agent": "busy-claude", "message": "again", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert second.status_code == 409
                assert "already has a run in progress" in second.json()["detail"]
            finally:
                release.set()
                await _await_background_run()


@pytest.mark.asyncio
async def test_spawn_failure_marks_run_failed(app, auth_headers):
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"missing-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn",
        MagicMock(side_effect=FileNotFoundError("claude was not found in PATH")),
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/agent/trigger",
                json={"agent": "missing-claude", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            # The pre-flight probe (mocked to report present) accepts the request; the
            # actual spawn failure happens in the background task and is reflected on the
            # Run row, not the HTTP response — matches "spawn directly, return an
            # identifier" (the identifier's outcome is observable via the run record, not
            # blocking the response).
            assert resp.status_code == 200
            run_id = resp.json()["run_id"]

            await _await_background_run()

    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.status == "failed"
        assert "not found in PATH" in run.error


def _drain(queue):
    """Collect every SSE event currently queued as (event_type, parsed_data)."""
    events = []
    while True:
        try:
            item = queue.get_nowait()
        except Exception:  # asyncio.QueueEmpty
            break
        events.append((item.event, json.loads(item.data)))
    return events


@pytest.mark.asyncio
async def test_successful_run_broadcasts_started_and_completed_lifecycle_events(app, auth_headers):
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"lifecycle-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    project_id = (await app.get("/api/v1/status", headers=auth_headers)).json()["project_id"]
    queue = sse_manager.subscribe(project_id)

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"sess-lc-1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/agent/trigger",
                json={"agent": "lifecycle-claude", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            run_id = resp.json()["run_id"]
            await _await_background_run()

    events = _drain(queue)
    started = [d for t, d in events if t == "run_started"]
    completed = [d for t, d in events if t == "run_completed"]
    assert len(started) == 1
    assert started[0]["agent"] == "lifecycle-claude"
    assert started[0]["run_id"] == run_id
    assert started[0]["runner"] == "claude"
    assert len(completed) == 1
    assert completed[0]["exit_code"] == 0
    assert completed[0]["session_id"] == "sess-lc-1"
    assert not [d for t, d in events if t == "run_failed"]

    from hub.db.engine import async_session_factory
    from hub.db.models import EventLog

    async with async_session_factory() as db:
        from sqlalchemy import select

        rows = (
            (
                await db.execute(
                    select(EventLog).where(
                        EventLog.project_id == project_id, EventLog.agent == "lifecycle-claude"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert any(r.event_type == "run_started" for r in rows)
    assert any(r.event_type == "run_completed" for r in rows)


@pytest.mark.asyncio
async def test_nonzero_exit_broadcasts_run_failed_not_run_completed(app, auth_headers):
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"failing-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    project_id = (await app.get("/api/v1/status", headers=auth_headers)).json()["project_id"]
    queue = sse_manager.subscribe(project_id)

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"error","is_error":true,"session_id":"sess-fail-1"}\n'],
        exit_code=1,
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/agent/trigger",
                json={"agent": "failing-claude", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            await _await_background_run()

    events = _drain(queue)
    failed = [d for t, d in events if t == "run_failed"]
    assert len(failed) == 1
    assert failed[0]["exit_code"] == 1
    assert not [d for t, d in events if t == "run_completed"]


@pytest.mark.asyncio
async def test_spawn_failure_broadcasts_run_failed_event(app, auth_headers):
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"missing-claude-2": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    project_id = (await app.get("/api/v1/status", headers=auth_headers)).json()["project_id"]
    queue = sse_manager.subscribe(project_id)

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn",
        MagicMock(side_effect=FileNotFoundError("claude was not found in PATH")),
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/agent/trigger",
                json={"agent": "missing-claude-2", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            await _await_background_run()

    events = _drain(queue)
    failed = [d for t, d in events if t == "run_failed"]
    assert len(failed) == 1
    assert "not found in PATH" in failed[0]["error"]
    assert not [d for t, d in events if t == "run_started"]


def _stoppable_pty(pid=555, exit_code=15):
    """A fake PtySession whose `.read()` blocks until `.terminate()` is called.

    Mirrors `test_second_trigger_while_first_is_running_is_rejected`'s blocking-read
    pattern, but here `.terminate()` itself is what releases the block — simulating a
    stop request actually reaching and killing the real process. `exit_code` defaults
    non-zero (a forced kill rarely exits 0) specifically to prove the stop endpoint's
    "stopped" classification wins over the exit-code-based "failed" classification.
    """
    import threading

    released = threading.Event()

    def _blocking_read(size=4096):
        released.wait()
        return ""

    def _terminate(force=False):
        released.set()

    session = MagicMock()
    session.pid = pid
    session.read.side_effect = _blocking_read
    session.terminate.side_effect = _terminate
    session.wait.return_value = exit_code
    return session


@pytest.mark.asyncio
async def test_stop_endpoint_marks_run_stopped_and_broadcasts_run_stopped(app, auth_headers):
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"stoppable-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    project_id = (await app.get("/api/v1/status", headers=auth_headers)).json()["project_id"]
    queue = sse_manager.subscribe(project_id)

    fake_session = _stoppable_pty()
    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            trigger = await app.post(
                "/api/v1/agent/trigger",
                json={"agent": "stoppable-claude", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert trigger.status_code == 200
            run_id = trigger.json()["run_id"]

            await _wait_for_active_pty(run_id)

            stop = await app.post("/api/v1/agent/stoppable-claude/stop", headers=auth_headers)
            assert stop.status_code == 200
            assert stop.json()["run_id"] == run_id
            assert stop.json()["status"] == "stopping"

            await _await_background_run()

    fake_session.terminate.assert_called_once_with(force=True)

    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.status == "stopped"
        assert run.exit_code == 15

    events = _drain(queue)
    stopped = [d for t, d in events if t == "run_stopped"]
    assert len(stopped) == 1
    assert stopped[0]["run_id"] == run_id
    assert not [d for t, d in events if t in ("run_completed", "run_failed")]


@pytest.mark.asyncio
async def test_stop_with_no_run_in_progress_returns_404(app, auth_headers):
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"idle-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    resp = await app.post("/api/v1/agent/idle-claude/stop", headers=auth_headers)
    assert resp.status_code == 404
    assert "no run in progress" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_shutdown_terminates_all_active_runs(app, auth_headers):
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"shutdown-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    import threading

    released = threading.Event()

    def _blocking_read(size=4096):
        released.wait()
        return ""

    fake_session = MagicMock()
    fake_session.pid = 7777
    fake_session.read.side_effect = _blocking_read
    fake_session.wait.return_value = 0

    terminated_pids = []

    def _fake_terminate_process_tree(pid, force=True):
        terminated_pids.append(pid)
        released.set()

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with patch(
                "hub.api.v1.agent_trigger.terminate_process_tree",
                side_effect=_fake_terminate_process_tree,
            ):
                trigger = await app.post(
                    "/api/v1/agent/trigger",
                    json={"agent": "shutdown-claude", "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert trigger.status_code == 200

                await _wait_for_active_pty(trigger.json()["run_id"])

                count = await agent_trigger.terminate_all_active_runs()
                assert count == 1
                assert terminated_pids == [7777]

                await _await_background_run()

    assert trigger.json()["run_id"] not in agent_trigger._active_ptys


@pytest.mark.asyncio
async def test_terminate_all_active_runs_with_nothing_running_returns_zero(app, auth_headers):
    count = await agent_trigger.terminate_all_active_runs()
    assert count == 0
