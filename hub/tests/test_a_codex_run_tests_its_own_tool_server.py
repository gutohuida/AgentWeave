"""F1191 -- a Codex run tests the Hub's tool server before its first prompt.

Found in WSL on PyPI 2.2.0: a new Codex agent's first run had no grounds for MCP
(`a-run-reaches-the-hub-without-mcp` D1), so it was told `aw-tool`. Its shell runs under
`workspace-write`, which on Linux has no network, so every call returned `unreachable`. The run
recorded `harness_mcp_status=connected` and `plane_surface=shim`: the MCP tools were working and
nobody told it. It was a review turn, it recorded no verdict, and the task sat `under_review`.

Codex starts the servers it is given inside `thread/start`/`thread/resume` and reports each one's
status before `turn/start` (measured against Codex 0.167.1, 2026-11-16). So the run tests itself,
as Copilot's does (D9). It is told `mcp` only on its own `ready`; `failed`, no report in time, or
no server given at all tells it the call command, as before. That keeps the requirement
`a-run-is-told-the-access-path-it-actually-has`: the run's own test is the grounds.

Held at both seams: the real `run_turn` against a scripted app-server, and the real
`POST /agent/trigger` driving the real `run_turn`, read back from the `Run` row.
"""

from unittest.mock import patch

import pytest

from hub import codex_appserver
from hub.codex_appserver import NEW_THREAD_CONTEXT_HEAD, RESUMED_CONTEXT_HEAD, run_turn
from hub.runner_adapters.codex import CodexAppServerTransport, CodexExecTransport
from tests.test_agent_trigger import _await_background_run
from tests.test_codex_appserver_run_turn import (
    THREAD_START_RESULT,
    TURN_START_RESULT,
    _collector,
    _FakeSession,
    _patch_spawn,
)

SURFACES = {
    "mcp": {"notice": "NOTICE-MCP", "context": "CONTEXT-MCP"},
    "shim": {"notice": "NOTICE-SHIM", "context": "CONTEXT-SHIM"},
}
COMPLETED = {"method": "turn/completed", "params": {"turn": {"status": "completed"}}}


def _startup(status, name="agentweave", error=None):
    return {
        "method": "mcpServer/startupStatus/updated",
        "params": {"name": name, "status": status, "error": error},
    }


def _fake(notifications, *, resume=False):
    return _FakeSession(
        responses={
            "initialize": {},
            "thread/resume" if resume else "thread/start": THREAD_START_RESULT,
            "turn/start": TURN_START_RESULT,
        },
        notifications=list(notifications),
    )


async def _drive(
    monkeypatch,
    notifications,
    *,
    resume=False,
    mcp_command=("python", "mcp_server.py"),
    should_interrupt=None,
):
    fake = _fake(notifications, resume=resume)
    _patch_spawn(monkeypatch, fake)
    told, statuses, events = [], [], []

    async def render(surface, tested, quote):
        told.append((surface, tested, quote))
        return []

    async def on_mcp_status(value):
        statuses.append(value)

    outcome = await run_turn(
        cli="codex",
        cwd="/workspace",
        env=None,
        prompt="PROMPT",
        model=None,
        resume_thread_id="thread-old" if resume else None,
        yolo=False,
        mcp_command=list(mcp_command) if mcp_command else None,
        on_event=_collector(events),
        on_mcp_status=on_mcp_status,
        should_interrupt=should_interrupt,
        developer_instructions="CONTEXT-BEFORE-THE-TEST",
        surfaces=SURFACES,
        render_surface=render,
        mcp_wait_seconds=0.05,
    )
    return fake, outcome, told, statuses, events


def _request(fake, method):
    return next(params for sent, params in fake.sent_requests if sent == method)


def _input_texts(fake):
    return [block["text"] for block in _request(fake, "turn/start")["input"]]


async def test_a_run_whose_server_is_ready_is_told_mcp(monkeypatch):
    """The F1191 case: the harness started the server, so the first prompt says so."""
    fake, outcome, told, statuses, _ = await _drive(
        monkeypatch, [_startup("starting"), _startup("ready"), COMPLETED]
    )

    assert told == [("mcp", True, None)]
    context, prompt = _input_texts(fake)
    assert prompt == "NOTICE-MCP\n\nPROMPT"
    assert context == f"{NEW_THREAD_CONTEXT_HEAD}\n\nCONTEXT-MCP"
    # Developer instructions go on `thread/start`, before the test can be read: none are sent.
    assert "developerInstructions" not in _request(fake, "thread/start")
    # The deciding report is still recorded, once, by the turn loop.
    assert statuses == ["connected"]
    assert outcome.status == "completed"


async def test_a_run_whose_server_failed_is_told_the_call_command(monkeypatch):
    fake, _, told, statuses, events = await _drive(
        monkeypatch, [_startup("failed", error="connection closed"), COMPLETED]
    )

    # The harness's own report, not the wait's `absent`: the turn loop records `failed`.
    assert told == [("shim", None, None)]
    assert _input_texts(fake)[1] == "NOTICE-SHIM\n\nPROMPT"
    assert statuses == ["failed"]
    (event,) = events
    # Worded for what it was told: it still reaches every operation through `aw-tool`.
    assert "aw-tool" in event.content
    assert "no AgentWeave tools" not in event.content


async def test_a_report_that_never_comes_tells_the_call_command_as_before(monkeypatch):
    """No report inside the wait: told the call command, and the wait's `absent` is recorded.
    What the wait read meanwhile (here the turn's end) is kept for the turn loop."""
    fake, outcome, told, statuses, _ = await _drive(monkeypatch, [COMPLETED])

    assert told == [("shim", False, None)]
    assert _input_texts(fake) == [
        f"{NEW_THREAD_CONTEXT_HEAD}\n\nCONTEXT-SHIM",
        "NOTICE-SHIM\n\nPROMPT",
    ]
    assert statuses == []
    assert outcome.status == "completed"


async def test_a_resumed_thread_tests_itself_too(monkeypatch):
    """Measured: `thread/resume` restarts the servers and reports them, so every turn tests."""
    fake, _, told, _, _ = await _drive(monkeypatch, [_startup("ready"), COMPLETED], resume=True)

    assert told == [("mcp", True, None)]
    context, prompt = _input_texts(fake)
    assert context == f"{RESUMED_CONTEXT_HEAD}\n\nCONTEXT-MCP"
    assert prompt == "NOTICE-MCP\n\nPROMPT"


async def test_what_arrives_during_the_wait_still_reaches_the_timeline(monkeypatch):
    item = {
        "method": "item/completed",
        "params": {"item": {"type": "agentMessage", "text": "early", "phase": "commentary"}},
    }
    _, _, told, _, events = await _drive(
        monkeypatch, [item, _startup("ready", name="other"), _startup("ready"), COMPLETED]
    )

    assert told == [("mcp", True, None)]
    assert [e.content for e in events] == ["early"]


async def test_a_run_given_no_server_is_told_the_call_command_without_waiting(monkeypatch):
    fake, _, told, statuses, _ = await _drive(monkeypatch, [COMPLETED], mcp_command=None)

    assert told == [("shim", None, None)]
    assert _input_texts(fake)[1] == "NOTICE-SHIM\n\nPROMPT"
    assert statuses == []


async def test_a_run_stopped_during_the_wait_is_told_nothing_and_starts_no_turn(monkeypatch):
    fake, outcome, told, _, _ = await _drive(
        monkeypatch, [_startup("ready"), COMPLETED], should_interrupt=lambda: True
    )

    assert outcome.status == "interrupted"
    assert told == []
    assert "turn/start" not in [method for method, _ in fake.sent_requests]
    assert fake.closed_with_force is True


def test_the_app_server_transport_tests_first_and_exec_does_not():
    """`codex exec` has no moment between starting its servers and reading its prompt."""
    assert CodexAppServerTransport.tests_mcp_before_first_prompt is True
    assert CodexExecTransport.tests_mcp_before_first_prompt is False


@pytest.mark.parametrize(
    "startup, plane, status, told_mcp",
    [
        ([_startup("ready")], "mcp", "connected", True),
        ([], "shim", "absent", False),
    ],
)
async def test_a_new_codex_agents_first_run_is_told_what_its_own_test_found(
    app, auth_headers, bind_runner, monkeypatch, startup, plane, status, told_mcp
):
    """The trigger seam: a brand-new agent, no earlier run, no `hub_client` -- D1 has no grounds.
    Through the real `run_turn`, its own `ready` is the grounds; without it, as before."""
    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    agent = f"fresh-codex-{plane}"
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(agent, cli="codex")

    fake = _fake([*startup, COMPLETED])
    _patch_spawn(monkeypatch, fake)
    monkeypatch.setattr(codex_appserver, "MCP_STARTUP_WAIT_SECONDS", 0.05, raising=False)
    with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/codex"):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": agent, "message": "review this", "session_mode": "new"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        run_id = response.json()["run_id"]
        await _await_background_run()

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert (run.plane_surface, run.harness_mcp_status) == (plane, status)

    context, prompt = _input_texts(fake)
    assert prompt.endswith("review this")
    assert ("the `agentweave` MCP tools are available" in prompt) is told_mcp
    assert ("aw-tool create_task .agentweave/calls/1.json" in prompt) is not told_mcp
    # One decision for the notice and the context: the tool section is in the same idiom.
    assert ("aw-tool" in context) is not told_mcp
    # The notice is said once, after the test, not also before it.
    assert prompt.count("[AgentWeave] Tool access:") == 1
