"""A Copilot agent's home is written when it is created and when its binding changes
(`a-copilot-agent-runs-over-acp` task 4.3, design D4 (a)/(b)).

Both writes come after the commit, and **any** exception is logged rather than raised: the row
exists, so a 500 would lie about it and the operator's retry would be refused "already exists".
Every Copilot spawn re-ensures the home anyway (D4 (c)).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hub.sse import sse_manager


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        "hub.api.v1.agents.probe_agent",
        lambda name, config: {
            "runner": config["runner"],
            "present": True,
            "authorized": True,
            "runnable": True,
            "reason": None,
        },
    )
    return tmp_path


async def _runner_id(app, auth_headers, cli):
    runners = (await app.get("/api/v1/projects/proj-test/runners", headers=auth_headers)).json()
    return next(r["id"] for r in runners if r["cli"] == cli)


def _agent_file(home: Path, agent: str) -> Path:
    return (
        home
        / ".agentweave"
        / "hub"
        / "copilot-home"
        / "projects"
        / "proj-test"
        / agent
        / "agents"
        / f"{agent}.agent.md"
    )


async def _create(app, auth_headers, name, runner_id, **extra):
    return await app.post(
        "/api/v1/projects/proj-test/agents",
        json={"name": name, "runner_id": runner_id, **extra},
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_creating_a_copilot_agent_writes_its_agent_file(app, auth_headers, _home):
    charters = (await app.get("/api/v1/projects/proj-test/charters", headers=auth_headers)).json()
    response = await _create(
        app,
        auth_headers,
        "cop-1",
        await _runner_id(app, auth_headers, "copilot"),
        charter_id=charters[0]["id"],
    )
    assert response.status_code == 201, response.text
    text = _agent_file(_home, "cop-1").read_text(encoding="utf-8")
    assert "AgentWeave agent cop-1" in text
    assert f"## Charter: {charters[0]['name']}" in text
    # Per-turn material stays out of the file.
    assert "### Your workspace" not in text


@pytest.mark.asyncio
async def test_a_claude_agent_gets_no_copilot_home(app, auth_headers, _home):
    response = await _create(
        app, auth_headers, "cl-1", await _runner_id(app, auth_headers, "claude")
    )
    assert response.status_code == 201, response.text
    assert not (_home / ".agentweave" / "hub" / "copilot-home").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [OSError("disk full"), RuntimeError("render failed")])
async def test_a_failing_home_write_still_creates_and_announces_the_agent(
    app, auth_headers, monkeypatch, error
):
    def _boom(*args, **kwargs):
        raise error

    monkeypatch.setattr("hub.copilot_home.ensure_copilot_home", _boom)
    queue = sse_manager.subscribe("proj-test")
    try:
        response = await _create(
            app, auth_headers, "cop-2", await _runner_id(app, auth_headers, "copilot")
        )
        assert response.status_code == 201, response.text
        event = await queue.get()
        assert event.event == "agent_created"
    finally:
        sse_manager.unsubscribe("proj-test", queue)


@pytest.mark.asyncio
async def test_binding_a_copilot_runner_by_patch_writes_the_file(app, auth_headers, _home):
    created = await _create(
        app, auth_headers, "mover", await _runner_id(app, auth_headers, "claude")
    )
    assert created.status_code == 201, created.text
    assert not _agent_file(_home, "mover").exists()

    response = await app.patch(
        "/api/v1/projects/proj-test/agents/mover",
        json={"runner_id": await _runner_id(app, auth_headers, "copilot")},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert _agent_file(_home, "mover").exists()


@pytest.mark.asyncio
async def test_a_failing_home_write_on_patch_still_answers_200(app, auth_headers, monkeypatch):
    created = await _create(
        app, auth_headers, "mover2", await _runner_id(app, auth_headers, "claude")
    )
    assert created.status_code == 201, created.text

    def _boom(*args, **kwargs):
        raise RuntimeError("no")

    monkeypatch.setattr("hub.copilot_home.ensure_copilot_home", _boom)
    response = await app.patch(
        "/api/v1/projects/proj-test/agents/mover2",
        json={"runner_id": await _runner_id(app, auth_headers, "copilot")},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["runner_id"] == await _runner_id(app, auth_headers, "copilot")
