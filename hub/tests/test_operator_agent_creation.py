import json

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Agent, Charter, Project, Runner
from hub.sse import sse_manager


async def _seed_foreign_records():
    async with async_session_factory() as session:
        project = Project(id="proj-other", name="Other", directory_state="unbound")
        runner = Runner(id="runner-other", project_id=project.id, name="Other", cli="codex")
        charter = Charter(id="charter-other", project_id=project.id, name="Other", content="Other")
        session.add_all([project, runner, charter])
        await session.commit()


@pytest.mark.asyncio
async def test_operator_creates_bound_agent_without_eager_worktree(app, auth_headers, monkeypatch):
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
    monkeypatch.setattr(
        "hub.api.v1.agents.worktrees.resolve_agent_workspace",
        lambda *args, **kwargs: pytest.fail("creation must not provision a worktree"),
    )
    runners = (await app.get("/api/v1/projects/proj-test/runners", headers=auth_headers)).json()
    charters = (await app.get("/api/v1/projects/proj-test/charters", headers=auth_headers)).json()
    queue = sse_manager.subscribe("proj-test")
    try:
        response = await app.post(
            "/api/v1/projects/proj-test/agents",
            json={
                "name": "ui-codex",
                "runner_id": runners[1]["id"],
                "charter_id": charters[0]["id"],
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body == {
            "id": body["id"],
            "name": "ui-codex",
            "runner_id": runners[1]["id"],
            "charter_id": charters[0]["id"],
            "color_index": 0,
            "contact_mode": "watchdog-spawn",
            "self_registered": False,
        }
        event = await queue.get()
        assert event.event == "agent_created"
        assert json.loads(event.data)["agent"] == "ui-codex"
        async with async_session_factory() as session:
            row = await session.get(Agent, body["id"])
            assert row is not None and row.self_registered is False
    finally:
        sse_manager.unsubscribe("proj-test", queue)


@pytest.mark.asyncio
async def test_operator_agent_name_and_duplicate_validation(app, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "hub.api.v1.agents.probe_agent",
        lambda *_: {"runnable": True, "reason": None},
    )
    runner = (await app.get("/api/v1/projects/proj-test/runners", headers=auth_headers)).json()[0]
    invalid = await app.post(
        "/api/v1/projects/proj-test/agents",
        json={"name": "../escape", "runner_id": runner["id"]},
        headers=auth_headers,
    )
    assert invalid.status_code == 422
    first = await app.post(
        "/api/v1/projects/proj-test/agents",
        json={"name": "duplicate", "runner_id": runner["id"]},
        headers=auth_headers,
    )
    second = await app.post(
        "/api/v1/projects/proj-test/agents",
        json={"name": "duplicate", "runner_id": runner["id"]},
        headers=auth_headers,
    )
    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_operator_agent_requires_same_project_launchable_bindings(
    app, auth_headers, monkeypatch
):
    await _seed_foreign_records()
    runner = (await app.get("/api/v1/projects/proj-test/runners", headers=auth_headers)).json()[0]
    foreign_runner = await app.post(
        "/api/v1/projects/proj-test/agents",
        json={"name": "foreign-runner", "runner_id": "runner-other"},
        headers=auth_headers,
    )
    foreign_charter = await app.post(
        "/api/v1/projects/proj-test/agents",
        json={"name": "foreign-charter", "runner_id": runner["id"], "charter_id": "charter-other"},
        headers=auth_headers,
    )
    assert foreign_runner.status_code == 404
    assert foreign_charter.status_code == 404

    monkeypatch.setattr(
        "hub.api.v1.agents.probe_agent",
        lambda *_: {"runnable": False, "reason": "CLI unavailable"},
    )
    unavailable = await app.post(
        "/api/v1/projects/proj-test/agents",
        json={"name": "unlaunchable", "runner_id": runner["id"]},
        headers=auth_headers,
    )
    assert unavailable.status_code == 409
    assert unavailable.json()["detail"] == "CLI unavailable"


@pytest.mark.asyncio
async def test_operator_agent_color_assignment_is_stable(app, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "hub.api.v1.agents.probe_agent",
        lambda *_: {"runnable": True, "reason": None},
    )
    runner = (await app.get("/api/v1/projects/proj-test/runners", headers=auth_headers)).json()[0]
    colors = []
    for name in ("first-ui-agent", "second-ui-agent"):
        response = await app.post(
            "/api/v1/projects/proj-test/agents",
            json={"name": name, "runner_id": runner["id"]},
            headers=auth_headers,
        )
        assert response.status_code == 201
        colors.append(response.json()["color_index"])
    assert colors == [0, 1]
