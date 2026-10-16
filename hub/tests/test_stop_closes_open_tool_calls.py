"""A run's end closes the tool calls it left open (F666, `stop-closes-the-tool-card-it-interrupted`).

Work PC, 2026-10-12, run `run-e183cc3e1acd`: Copilot ran `Start-Sleep -Seconds 240`, the operator
pressed Stop, and the run recorded `thinking`, `tool_use`, `status` -- no `tool_result`, so the card
read "awaiting result" for ever. ACP gives the close to the client. These tests drive the real
executors through the trigger route and read rows back through the outputs route, in the order it
returns them (ascending `timestamp`, `sequence`, `id`), never re-sorted.
"""

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub.runner_events import (
    diagnostic_event,
    error_event,
    thinking_event,
    tool_result_event,
    tool_use_event,
)
from tests.test_a_refused_turn_holds_the_queue import _copilot_agent, _copilot_installed  # noqa
from tests.test_agent_trigger import (
    _await_background_run,
    _bind_codex_app_server_runner,
    _fake_run_turn,
    _wait_for_active_pty,
    _wait_released,
)
from tests.test_failed_run_returns_input import _schedule_after_the_first

BASE = "/api/v1/projects/proj-test"
CALL = "toolu_01Ky1xyEL7aTrBkrR3fyKsZX"


def _shell_call(call_id=CALL):
    """The `tool_use` the work-PC run recorded (`agent_outputs` seq 2)."""
    return tool_use_event(
        tool="shell",
        category="command",
        input_data={"command": "Start-Sleep -Seconds 240; echo done"},
        call_id=call_id,
        summary="Sleep 240 seconds then print done",
    )


def _copilot_turn(events, *, status, error=None):
    async def _run(**kwargs):
        await kwargs["on_session"]("sess-f666")
        for event in events:
            await kwargs["on_event"](event)
        from hub.copilot_acp import TurnOutcome

        return TurnOutcome(session_id="sess-f666", status=status, error=error)

    return AsyncMock(side_effect=_run)


async def _rows(app, auth_headers, agent, run_id):
    response = await app.get(f"{BASE}/agents/{agent}/output?limit=1000", headers=auth_headers)
    assert response.status_code == 200, response.text
    return [row for row in response.json() if row["run_id"] == run_id]


async def _copilot_run(app, auth_headers, bind_runner, agent, fake):
    await _copilot_agent(app, auth_headers, bind_runner, agent)
    with (
        patch("hub.copilot_acp.run_turn", fake),
        patch("hub.turn_scheduler.schedule_agent", _schedule_after_the_first()),
    ):
        trigger = await app.post(
            f"{BASE}/agent/trigger",
            json={"agent": agent, "message": "run the sleep", "session_mode": "new"},
            headers=auth_headers,
        )
        assert trigger.status_code == 200, trigger.text
        run_id = trigger.json()["run_id"]
        await _await_background_run()
    return run_id, await _rows(app, auth_headers, agent, run_id)


def _closing(row, call_id=CALL, tool="shell"):
    assert row["kind"] == "tool_result"
    payload = row["payload"]
    assert payload["call_id"] == call_id
    assert payload["tool"] == tool
    assert payload["status"] == "interrupted"
    assert payload["is_error"] is False
    assert payload["version"] == 1
    assert row["content"] == f"{tool} interrupted"


@pytest.mark.asyncio
async def test_copilot_stopped_mid_call_closes_the_call(
    app, auth_headers, bind_runner, _copilot_installed  # noqa: F811
):
    fake = _copilot_turn([thinking_event("planning"), _shell_call()], status="interrupted")
    run_id, rows = await _copilot_run(app, auth_headers, bind_runner, "f666-stop", fake)

    assert [r["kind"] for r in rows] == ["thinking", "tool_use", "tool_result", "status"]
    _closing(rows[2])
    assert rows[3]["content"] == "Run stopped (exit 1)."


@pytest.mark.asyncio
async def test_copilot_failed_mid_call_closes_the_call(
    app, auth_headers, bind_runner, _copilot_installed  # noqa: F811
):
    fake = _copilot_turn([_shell_call()], status="failed", error="timed out")
    run_id, rows = await _copilot_run(app, auth_headers, bind_runner, "f666-fail", fake)

    assert [r["kind"] for r in rows] == ["tool_use", "tool_result", "status"]
    _closing(rows[1])
    assert rows[2]["content"] == "Run failed (exit 1)."


@pytest.mark.asyncio
async def test_rows_the_runner_wrote_after_the_call_come_before_the_closing_row(
    app, auth_headers, bind_runner, _copilot_installed  # noqa: F811
):
    notice = diagnostic_event(stream="copilot", severity="info", summary="Created file a.txt")
    fake = _copilot_turn([_shell_call(), notice], status="interrupted")
    _, rows = await _copilot_run(app, auth_headers, bind_runner, "f666-notice", fake)
    assert [r["kind"] for r in rows] == ["tool_use", "diagnostic", "tool_result", "status"]
    _closing(rows[2])

    error = error_event(code="session_error", message="the session went away")
    fake = _copilot_turn([_shell_call("toolu_err"), error], status="failed", error="gone")
    _, rows = await _copilot_run(app, auth_headers, bind_runner, "f666-error", fake)
    assert [r["kind"] for r in rows] == ["tool_use", "error", "tool_result", "status"]
    _closing(rows[2], call_id="toolu_err")


@pytest.mark.asyncio
async def test_a_call_the_provider_closed_is_not_closed_twice(
    app, auth_headers, bind_runner, _copilot_installed  # noqa: F811
):
    """Control. ACP allows a terminal update after `session/cancel` and before the answer."""
    own = tool_result_event(tool="shell", output="done", call_id=CALL, summary="shell completed")
    fake = _copilot_turn([_shell_call(), own], status="interrupted")
    _, rows = await _copilot_run(app, auth_headers, bind_runner, "f666-closed", fake)

    results = [r for r in rows if r["kind"] == "tool_result"]
    assert len(results) == 1
    assert "status" not in results[0]["payload"]
    assert results[0]["payload"]["output"] == "done"


@pytest.mark.asyncio
async def test_a_completed_run_is_not_closed(
    app, auth_headers, bind_runner, _copilot_installed  # noqa: F811
):
    """Control (wpc7-c, recommended): an open call in a completed run is a mapper defect to see."""
    fake = _copilot_turn([_shell_call()], status="completed")
    _, rows = await _copilot_run(app, auth_headers, bind_runner, "f666-done", fake)
    assert [r["kind"] for r in rows if r["kind"] == "tool_result"] == []


@pytest.mark.asyncio
async def test_a_call_without_an_identifier_gets_no_invented_result(
    app, auth_headers, bind_runner, _copilot_installed  # noqa: F811
):
    fake = _copilot_turn([_shell_call(call_id=None)], status="interrupted")
    _, rows = await _copilot_run(app, auth_headers, bind_runner, "f666-noid", fake)
    assert [r["kind"] for r in rows] == ["tool_use", "status"]


@pytest.mark.asyncio
async def test_a_closing_write_that_raises_does_not_change_how_the_run_ended(
    app, auth_headers, bind_runner, _copilot_installed  # noqa: F811
):
    from hub.db.engine import async_session_factory
    from hub.db.models import Run
    from hub.output_recording import record_agent_output as real

    async def _refuse_closing_rows(db, *args, **kwargs):
        if (kwargs.get("payload") or {}).get("status") == "interrupted":
            raise RuntimeError("disk on fire")
        return await real(db, *args, **kwargs)

    fake = _copilot_turn([_shell_call()], status="interrupted")
    with patch("hub.api.v1.agent_trigger.record_agent_output", _refuse_closing_rows):
        run_id, rows = await _copilot_run(app, auth_headers, bind_runner, "f666-raise", fake)

    async with async_session_factory() as db:
        assert (await db.get(Run, run_id)).status == "stopped"
    assert [r["kind"] for r in rows] == ["tool_use", "status"]
    assert rows[-1]["content"] == "Run stopped (exit 1)."


@pytest.mark.asyncio
async def test_a_codex_app_server_run_stopped_mid_command_closes_it(app, auth_headers):
    """The only interrupt sequence captured for Codex (`test_codex_appserver_run_turn.py`): the
    item starts and `turn/completed` arrives with no `item/completed` for it."""
    agent = "f666-codex"
    await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {agent: {"runner": "codex"}}}},
        headers=auth_headers,
    )
    await _bind_codex_app_server_runner(app, auth_headers)(agent)
    call = tool_use_event(
        tool="commandExecution",
        category="command",
        input_data={"command": "sleep 240"},
        call_id="item-1",
    )
    fake = _fake_run_turn(thread_id="thread-f666", status="interrupted", events=[call])
    with (
        patch("hub.codex_appserver.run_turn", fake),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/codex"),
    ):
        trigger = await app.post(
            f"{BASE}/agent/trigger",
            json={"agent": agent, "message": "hi", "session_mode": "new"},
            headers=auth_headers,
        )
        run_id = trigger.json()["run_id"]
        await _await_background_run()

    rows = await _rows(app, auth_headers, agent, run_id)
    assert [r["kind"] for r in rows] == ["tool_use", "tool_result", "status"]
    _closing(rows[1], call_id="item-1", tool="commandExecution")


def _pty_stopped_mid_call(line: str, exit_code: int = 15):
    """A Claude process that prints *line*, then blocks until it is terminated (Stop)."""
    released = threading.Event()
    printed = []

    def _read(size=4096):
        if not printed:
            printed.append(True)
            return line
        _wait_released(released)
        return ""

    session = MagicMock()
    session.pid = 556
    session.read.side_effect = _read
    session.terminate.side_effect = lambda force=False: released.set()
    session.wait.return_value = exit_code
    return session


@pytest.mark.asyncio
async def test_a_claude_run_stopped_mid_call_closes_it(app, auth_headers, bind_runner):
    agent = "f666-claude"
    await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {agent: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner(agent, cli="claude")
    line = (
        '{"type":"assistant","session_id":"sess-f666-claude","message":{"content":['
        '{"type":"tool_use","id":"toolu_claude","name":"Bash","input":{"command":"sleep 240"}}'
        "]}}\n"
    )
    session = _pty_stopped_mid_call(line)
    with (
        patch("hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=session)),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"),
    ):
        trigger = await app.post(
            f"{BASE}/agent/trigger",
            json={"agent": agent, "message": "hi", "session_mode": "new"},
            headers=auth_headers,
        )
        run_id = trigger.json()["run_id"]
        await _wait_for_active_pty(run_id)
        for _ in range(200):
            if any(r["kind"] == "tool_use" for r in await _rows(app, auth_headers, agent, run_id)):
                break
            import asyncio

            await asyncio.sleep(0.02)
        stop = await app.post(f"{BASE}/agent/{agent}/stop", headers=auth_headers)
        assert stop.status_code == 200
        await _await_background_run()

    rows = await _rows(app, auth_headers, agent, run_id)
    kinds = [r["kind"] for r in rows]
    assert kinds[-3:] == ["tool_use", "tool_result", "status"], kinds
    _closing(rows[-2], call_id="toolu_claude", tool="Bash")
    assert rows[-1]["content"] == "Run stopped (exit 15)."
