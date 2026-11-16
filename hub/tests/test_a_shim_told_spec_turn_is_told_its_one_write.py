"""F1161 -- a spec turn told the call command is not told it has no file-write tool.

Found live on 2026-11-11 driving Codex: an agent's first run is told `aw-tool` (no earlier run
proved MCP), and `aw-tool` needs its arguments written to a file under `.agentweave/calls/`. The
spec turn keeps exactly that write (D16: `_is_hub_own_call`; Codex's read-only thread asks and the
Hub accepts). But the prompt said both "write the tool's arguments ... with your file-writing tool"
and "You have no file-write tool this turn". The agent believed the second, never tried the write,
and ended the turn without submitting the document it was opened on.

Held at the notice itself and at the prompt the real `POST /agent/trigger` composes, each with the
MCP-told control, which keeps the plain sentence.
"""

from unittest.mock import patch

import pytest

from hub import codex_appserver
from hub.launchability import spec_turn_notice
from tests.test_agent_trigger import _await_background_run
from tests.test_codex_appserver_run_turn import (
    THREAD_START_RESULT,
    TURN_START_RESULT,
    _FakeSession,
    _patch_spawn,
)

NO_WRITE = "You have no file-write tool this turn."
DOCUMENT = "spec/changes/f1161-shim-told/spec.json"


@pytest.mark.parametrize("phase", ["exploring", "proposed", "approved"])
def test_a_shim_told_spec_turn_is_told_its_one_write(phase):
    notice = spec_turn_notice(phase, access_path="shim")

    assert NO_WRITE not in notice
    assert "`.agentweave/calls/`" in notice
    # A read-only sandbox is not a reason to skip it: the write asks, and that one is granted.
    assert "read-only" in notice
    assert "approval" in notice
    assert "create_task" in notice


@pytest.mark.parametrize("phase", ["exploring", "approved"])
def test_an_mcp_told_spec_turn_keeps_the_plain_sentence(phase):
    """The control: an MCP-told turn needs no file, so it is told it has no write at all."""
    assert NO_WRITE in spec_turn_notice(phase, access_path="mcp")
    assert NO_WRITE in spec_turn_notice(phase)


@pytest.mark.parametrize("ready", [False, True])
async def test_the_composed_prompt_of_a_codex_spec_turn_does_not_contradict_itself(
    app, auth_headers, bind_runner, monkeypatch, ready
):
    """Through the real `run_turn`: a Codex run tests the Hub's server before its first prompt
    (F1191), so its notices are composed after that test. With no report it is told the call
    command and keeps its one write; with `ready` it is told the MCP tools and the plain sentence.
    """
    agent = f"spec-codex-{'ready' if ready else 'silent'}"
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(agent, cli="codex")
    created = await app.post(
        "/api/v1/projects/proj-test/project/documents",
        json={"path": DOCUMENT, "title": "F1161"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text

    startup = {
        "method": "mcpServer/startupStatus/updated",
        "params": {"name": "agentweave", "status": "ready"},
    }
    completed = {"method": "turn/completed", "params": {"turn": {"status": "completed"}}}
    fake = _FakeSession(
        responses={
            "initialize": {},
            "thread/start": THREAD_START_RESULT,
            "turn/start": TURN_START_RESULT,
        },
        notifications=[startup, completed] if ready else [completed],
    )
    _patch_spawn(monkeypatch, fake)
    monkeypatch.setattr(codex_appserver, "MCP_STARTUP_WAIT_SECONDS", 0.05)
    with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/codex"):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={
                "agent": agent,
                "message": "write the spec",
                "session_mode": "new",
                "spec_document": DOCUMENT,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        await _await_background_run()

    turn_start = next(params for method, params in fake.sent_requests if method == "turn/start")
    prompt = turn_start["input"][-1]["text"]
    assert "SPECIFICATION TURN" in prompt
    if ready:
        assert "the `agentweave` MCP tools are available" in prompt
        assert NO_WRITE in prompt
        assert ".agentweave/calls/" not in prompt
    else:
        # The premise of F1161: told the call command, and told it keeps the write it needs.
        assert "`aw-tool`" in prompt
        assert ".agentweave/calls/" in prompt
        assert NO_WRITE not in prompt
