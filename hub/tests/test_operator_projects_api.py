"""Instance-operator authentication and explicit project route contracts."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AgentHeartbeat, ApiKey, OperatorCredential, Project, Run, Task


async def _add_second_project() -> None:
    async with async_session_factory() as session:
        session.add(Project(id="proj-second", name="Second Project"))
        await session.commit()


@pytest.mark.asyncio
async def test_instance_operator_credential_lists_every_project(app, auth_headers) -> None:
    await _add_second_project()

    response = await app.get("/api/v1/projects", headers=auth_headers)

    assert response.status_code == 200
    assert {project["id"] for project in response.json()} == {"proj-test", "proj-second"}


@pytest.mark.asyncio
async def test_project_collection_includes_safe_live_agent_summary(app, auth_headers) -> None:
    async with async_session_factory() as session:
        session.add(
            Agent(
                id="agent-project-summary",
                project_id="proj-test",
                name="summary-agent",
                color_index=3,
            )
        )
        session.add(
            AgentHeartbeat(
                id="heartbeat-project-summary",
                project_id="proj-test",
                agent="summary-agent",
                status="running",
                timestamp=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    response = await app.get("/api/v1/projects", headers=auth_headers)
    project = next(item for item in response.json() if item["id"] == "proj-test")
    assert project["agents"] == [
        {
            "id": "agent-project-summary",
            "name": "summary-agent",
            "color_index": 3,
            "status": "running",
            "last_seen": project["agents"][0]["last_seen"],
        }
    ]
    assert project["agents"][0]["last_seen"] is not None
    assert "path_key" not in project


@pytest.mark.asyncio
async def test_project_scoped_api_key_is_not_an_operator_credential(app) -> None:
    legacy_key = "aw_live_legacy_project_key_123456"
    async with async_session_factory() as session:
        session.add(ApiKey(id=legacy_key, project_id="proj-test", label="legacy", revoked=False))
        await session.commit()

    response = await app.get("/api/v1/projects", headers={"Authorization": f"Bearer {legacy_key}"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_operator_project_paths_isolate_task_resources(app, auth_headers) -> None:
    await _add_second_project()

    created = await app.post(
        "/api/v1/projects/proj-second/tasks",
        json={"title": "Second only"},
        headers=auth_headers,
    )
    first = await app.get("/api/v1/projects/proj-test/tasks", headers=auth_headers)
    second = await app.get("/api/v1/projects/proj-second/tasks", headers=auth_headers)

    assert created.status_code == 201
    assert first.status_code == 200
    assert first.json() == []
    assert [task["title"] for task in second.json()] == ["Second only"]
    async with async_session_factory() as session:
        task = await session.scalar(select(Task).where(Task.title == "Second only"))
        assert task is not None
        assert task.project_id == "proj-second"


@pytest.mark.asyncio
async def test_unknown_project_id_is_rejected_before_resource_access(app, auth_headers) -> None:
    response = await app.get("/api/v1/projects/proj-does-not-exist/tasks", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


@pytest.mark.asyncio
async def test_run_credential_cannot_choose_an_operator_project_path(app) -> None:
    token = "aw_run_operator-boundary-test"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-operator-boundary",
                project_id="proj-test",
                agent="bounded",
                status="running",
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()

    response = await app.get(
        "/api/v1/projects/proj-test/tasks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_operator_credential_model_has_no_project_binding() -> None:
    assert "project_id" not in OperatorCredential.__table__.columns


@pytest.mark.asyncio
async def test_open_get_and_relocate_existing_project(app, auth_headers, tmp_path) -> None:
    original = tmp_path / "original"
    relocated = tmp_path / "relocated"
    original.mkdir()

    opened = await app.post(
        "/api/v1/projects/open",
        json={"path": str(original)},
        headers=auth_headers,
    )
    assert opened.status_code == 200, opened.text
    project_id = opened.json()["id"]
    assert opened.json()["path_display"] == str(original.resolve())
    assert opened.json()["directory_state"] == "available"

    detail = await app.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == project_id

    original.rename(relocated)
    moved = await app.post(
        f"/api/v1/projects/{project_id}/relocate",
        json={"path": str(relocated)},
        headers=auth_headers,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["id"] == project_id
    assert moved.json()["path_display"] == str(relocated.resolve())


@pytest.mark.asyncio
async def test_create_project_returns_agents_state_path_and_budgets(
    app, auth_headers, tmp_path
) -> None:
    target = tmp_path / "created"
    created = await app.post(
        "/api/v1/projects/create",
        json={"path": str(target), "name": "Created Project"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Created Project"
    assert body["path_display"] == str(target.resolve())
    assert body["directory_state"] == "available"
    assert body["agents"] == []
    assert body["hop_budget"] == 6
    assert body["turn_delivery_cap"] == 10
    assert body["agent_budget"] == 8
    assert body["token_budget"] is None
    assert body["allow_agent_jobs"] is False


@pytest.mark.asyncio
async def test_project_settings_update_is_validated_and_atomic(app, auth_headers) -> None:
    updated = await app.put(
        "/api/v1/projects/proj-test/settings",
        json={
            "name": "Renamed",
            "hop_budget": 9,
            "turn_delivery_cap": 4,
            "agent_budget": 12,
            "token_budget": 5000,
            "allow_agent_jobs": True,
        },
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json() == {
        "name": "Renamed",
        "hop_budget": 9,
        "turn_delivery_cap": 4,
        "agent_budget": 12,
        "token_budget": 5000,
        "allow_agent_jobs": True,
    }
    queue_settings = await app.get(
        "/api/v1/projects/proj-test/queue/settings", headers=auth_headers
    )
    assert queue_settings.json() == {
        "hop_budget": 9,
        "turn_delivery_cap": 4,
        "agent_budget": 12,
        "allow_agent_jobs": True,
    }

    invalid = await app.put(
        "/api/v1/projects/proj-test/settings",
        json={
            "name": "Must not persist",
            "hop_budget": 0,
            "turn_delivery_cap": "many",
            "agent_budget": 1,
            "token_budget": -1,
            "allow_agent_jobs": False,
        },
        headers=auth_headers,
    )
    assert invalid.status_code == 422
    fields = {error["loc"][-1] for error in invalid.json()["detail"]}
    assert {"hop_budget", "turn_delivery_cap", "token_budget"} <= fields

    unchanged = await app.get("/api/v1/projects/proj-test/settings", headers=auth_headers)
    assert unchanged.status_code == 200
    assert unchanged.json()["name"] == "Renamed"


@pytest.mark.asyncio
async def test_setup_token_returns_operator_credential_without_project_selection(app) -> None:
    response = await app.get("/api/v1/setup/token", headers={"Host": "localhost"})
    assert response.status_code == 200
    assert response.json() == {"api_key": "aw_live_testkey_abcdefgh"}


@pytest.mark.asyncio
async def test_setup_token_does_not_fall_back_to_a_project_api_key(app) -> None:
    async with async_session_factory() as session:
        operator = await session.get(OperatorCredential, "aw_live_testkey_abcdefgh")
        assert operator is not None
        operator.revoked = True
        await session.commit()

    response = await app.get("/api/v1/setup/token", headers={"Host": "localhost"})
    assert response.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("project_path", "response_type"),
    [
        ("/api/v1/projects/proj-test/tasks", list),
        ("/api/v1/projects/proj-test/agents", list),
        (
            "/api/v1/projects/proj-test/agent/missing/conversations",
            list,
        ),
        ("/api/v1/projects/proj-test/jobs", list),
        ("/api/v1/projects/proj-test/project/specs", dict),
        ("/api/v1/projects/proj-test/logs", list),
    ],
)
async def test_explicit_project_resource_routes_preserve_response_contracts(
    app, auth_headers, project_path: str, response_type: type
) -> None:
    response = await app.get(project_path, headers=auth_headers)

    assert response.status_code == 200
    assert isinstance(response.json(), response_type)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "legacy_path",
    [
        "/api/v1/tasks",
        "/api/v1/agents",
        "/api/v1/agent/missing/conversations",
        "/api/v1/jobs",
        "/api/v1/project/specs",
        "/api/v1/logs",
    ],
)
async def test_implicit_legacy_project_routes_are_removed(
    app, auth_headers, legacy_path: str
) -> None:
    response = await app.get(legacy_path, headers=auth_headers)

    assert response.status_code == 404
