"""A Copilot agent is triggered through the same door as every other runner
(`a-copilot-agent-runs-over-acp` task 7.2, design D1, D4 (c), D7, D18).

Every test enters through `POST /agent/trigger`, never the executor: three gates outside the
transport refused `copilot` (`SUPPORTED_RUNNERS`, `build_command`, `MCP_INJECTABLE_RUNNERS`), and a
test that started below them would pass while the route still answered 501 (design, Risks).
`copilot_acp.run_turn` is replaced by a fake that drives the executor's callbacks the way a real
turn does.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub.conversations import get_conversation_by_id
from hub.copilot_acp import TurnOutcome
from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Run
from hub.runner_events import text_event

from ._background_runs import await_background_runs


@pytest.fixture(autouse=True)
def _copilot_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    exe = tmp_path / "copilot.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr("hub.copilot_probe.resolve_copilot_executable", lambda override: exe)
    return tmp_path


def _fake_turn(*, session_id="sess-1", missing=None, status="completed"):
    async def _run(**kwargs):
        if missing is not None:
            await kwargs["on_session_missing"](missing)
        await kwargs["on_session"](session_id)
        await kwargs["on_event"](text_event("hello from copilot"))
        return TurnOutcome(session_id=session_id, status=status)

    return AsyncMock(side_effect=_run)


async def _copilot_agent(app, auth_headers, bind_runner, name="cop-1", **config):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "copilot", **config}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(name, cli="copilot")


async def _trigger(app, auth_headers, agent="cop-1", **body):
    return await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": agent, "message": "hi", **body},
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_a_copilot_turn_reaches_run_turn_with_the_mcp_server_and_its_context(
    app, auth_headers, bind_runner, _copilot_installed
):
    await _copilot_agent(app, auth_headers, bind_runner)
    fake = _fake_turn()
    with patch("hub.api.v1.agent_trigger.copilot_run_turn", fake):
        response = await _trigger(app, auth_headers, session_mode="new")
        assert response.status_code == 200, response.text
        await await_background_runs()

    fake.assert_called_once()
    kwargs = fake.call_args.kwargs
    # MCP_INJECTABLE_RUNNERS admits copilot, or the Hub's server would never be injected.
    assert kwargs["mcp_command"] is not None
    assert kwargs["agent"] == "cop-1"
    assert "### Your workspace" in kwargs["per_turn_context"]
    assert "## Your tools" in kwargs["tool_surface_context"]
    assert "### Your workspace" not in (kwargs["stable_context"] or "")
    # The operator's message is the prompt, not the context (D5).
    assert kwargs["prompt"].endswith("hi")
    home = _copilot_installed / ".agentweave" / "hub" / "copilot-home" / "projects" / "proj-test"
    assert kwargs["env"]["COPILOT_HOME"] == str(home / "cop-1")
    assert (home / "cop-1" / "agents" / "cop-1.agent.md").exists()
    assert (home / "cop-1" / "agentweave-mcp.json").exists()

    async with async_session_factory() as db:
        run = (await db.execute(select(Run).where(Run.agent == "cop-1"))).scalars().one()
        conversation = await get_conversation_by_id(db, run.conversation_id)
    assert (run.status, run.session_id) == ("completed", "sess-1")
    assert conversation.provider_session_id == "sess-1"


@pytest.mark.asyncio
async def test_a_missing_saved_session_is_rebound_to_the_new_one(app, auth_headers, bind_runner):
    """D7: `session/load` answered -32002, so the stored id named nothing; the new session takes
    its place, the stated exception to the first-writer rule."""
    await _copilot_agent(app, auth_headers, bind_runner)
    with patch("hub.api.v1.agent_trigger.copilot_run_turn", _fake_turn(session_id="sess-1")):
        first = await _trigger(app, auth_headers, session_mode="new")
        assert first.status_code == 200, first.text
        await await_background_runs()
    conversation_id = first.json()["conversation_id"]

    resumed = _fake_turn(session_id="sess-2", missing="sess-1")
    with patch("hub.api.v1.agent_trigger.copilot_run_turn", resumed):
        second = await _trigger(app, auth_headers, conversation_id=conversation_id)
        assert second.status_code == 200, second.text
        await await_background_runs()

    assert resumed.call_args.kwargs["resume_session_id"] == "sess-1"
    async with async_session_factory() as db:
        conversation = await get_conversation_by_id(db, conversation_id)
        runs = (
            (await db.execute(select(Run).where(Run.conversation_id == conversation_id)))
            .scalars()
            .all()
        )
    assert conversation.provider_session_id == "sess-2"
    assert sorted(run.session_id for run in runs) == ["sess-1", "sess-2"]
    assert all(run.status == "completed" for run in runs)


@pytest.mark.asyncio
async def test_an_unwritable_home_holds_the_input_without_counting_an_attempt(
    app, auth_headers, bind_runner, monkeypatch
):
    """D4 (c), R3: the refusal is `agent_wide`, so the route answers 200 queued with the sentence
    and the scheduler counts nothing against the operator's message."""
    await _copilot_agent(app, auth_headers, bind_runner)

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("hub.copilot_home.ensure_copilot_home", _boom)
    fake = _fake_turn()
    with patch("hub.api.v1.agent_trigger.copilot_run_turn", fake):
        response = await _trigger(app, auth_headers, session_mode="new")
        await await_background_runs()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert "Could not write cop-1's Copilot home" in body["waiting_reason"]
    fake.assert_not_called()
    async with async_session_factory() as db:
        entries = (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == "cop-1")))
            .scalars()
            .all()
        )
    assert entries and all(entry.state == "queued" for entry in entries)
    assert all(entry.delivery_attempts == 0 for entry in entries)


@pytest.mark.asyncio
async def test_a_missing_executable_holds_the_input_with_the_probes_sentence(
    app, auth_headers, bind_runner, monkeypatch
):
    await _copilot_agent(app, auth_headers, bind_runner)
    from hub.copilot_probe import CopilotExecutableNotFound

    def _missing(override):
        raise CopilotExecutableNotFound("GitHub Copilot CLI was not found: install it.")

    monkeypatch.setattr("hub.copilot_probe.resolve_copilot_executable", _missing)
    fake = _fake_turn()
    with patch("hub.api.v1.agent_trigger.copilot_run_turn", fake):
        response = await _trigger(app, auth_headers, session_mode="new")
        await await_background_runs()

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"
    assert "GitHub Copilot CLI was not found" in response.json()["waiting_reason"]
    fake.assert_not_called()


@pytest.mark.asyncio
async def test_an_env_var_that_would_widen_approvals_is_removed_and_said(
    app, auth_headers, bind_runner
):
    """D3: `COPILOT_ALLOW_ALL` named in the agent's own `env_vars` never reaches the spawn, and
    the run's timeline says it was removed."""
    await _copilot_agent(app, auth_headers, bind_runner, env_vars={"COPILOT_ALLOW_ALL": "true"})
    fake = _fake_turn()
    with patch("hub.api.v1.agent_trigger.copilot_run_turn", fake):
        response = await _trigger(app, auth_headers, session_mode="new")
        assert response.status_code == 200, response.text
        await await_background_runs()

    env = fake.call_args.kwargs["env"]
    assert "COPILOT_ALLOW_ALL" not in {key.upper() for key in env}
    async with async_session_factory() as db:
        from hub.db.models import AgentOutput

        rows = (
            (await db.execute(select(AgentOutput).where(AgentOutput.agent == "cop-1")))
            .scalars()
            .all()
        )
    removed = [
        row
        for row in rows
        if (row.payload or {}).get("code") == ("copilot.permission_override_removed")
    ]
    assert removed and "COPILOT_ALLOW_ALL" in removed[0].content
