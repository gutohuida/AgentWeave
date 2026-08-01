"""Integration tests for the rewritten POST /api/v1/agent/trigger (task 3.5).

`PtySession.spawn` is mocked throughout — these tests exercise the endpoint's request
handling, pre-flight checks, and background execution/recording loop, not the real CLIs
(those are covered live — see tasks.md's task 3.5 entry — and by test_runner_parsing.py's
fixtures, which use real captured output).
"""

from unittest.mock import MagicMock, patch

import pytest

import hub.api.v1.agent_trigger as agent_trigger


async def _await_background_run():
    """Wait for whatever background run task(s) the last trigger call started."""
    tasks = list(agent_trigger._background_runs)
    for task in tasks:
        await task


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
