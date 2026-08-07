"""Phase 7 contracts for the Hub-owned, effect-only agent tool surface."""

import inspect
import json

import pytest
from sqlalchemy import select

from hub.db.models import Agent, InboundQueueEntry, Project, ProjectSession, Run


async def _tool_names() -> set[str]:
    from hub.mcp_server import mcp

    return {tool.name for tool in await mcp.list_tools()}


@pytest.mark.asyncio
async def test_canonical_surface_has_no_coordination_or_configuration_bypasses():
    names = await _tool_names()
    assert {
        "get_inbox",
        "mark_read",
        "register_agent",
        "get_agent_config",
        "update_agent_config",
        "heartbeat",
        "get_context",
        "get_agent_context",
        "get_status",
        "list_agents",
        "list_jobs",
        "get_job",
    }.isdisjoint(names)
    assert {
        "send_message",
        "create_task",
        "list_tasks",
        "get_task",
        "update_task",
        "ask_user",
        "get_answer",
        "request_agent",
    } <= names


def test_canonical_effect_signatures_do_not_accept_caller_identity():
    from hub import mcp_server

    for name in ("send_message", "create_task", "update_task", "ask_user", "request_agent"):
        params = inspect.signature(getattr(mcp_server, name)).parameters
        assert "from_agent" not in params
        assert "assigner" not in params
        assert "requester" not in params


def test_cli_mcp_module_reexports_the_canonical_hub_surface():
    from agentweave.mcp import server as cli_server
    from hub import mcp_server as hub_server

    assert cli_server.mcp is hub_server.mcp
    assert cli_server.request_agent is hub_server.request_agent


def test_runner_commands_inject_one_stdio_surface_for_claude_and_codex():
    from hub.runner_commands import build_command

    mcp_command = ["python", "C:/agentweave/hub/mcp_server.py"]
    claude = build_command(runner="claude", cli="claude", prompt="work", mcp_command=mcp_command)
    config = json.loads(claude[claude.index("--mcp-config") + 1])
    assert config == {
        "mcpServers": {
            "agentweave": {
                "type": "stdio",
                "command": "python",
                "args": ["C:/agentweave/hub/mcp_server.py"],
            }
        }
    }

    codex = build_command(runner="codex", cli="codex", prompt="work", mcp_command=mcp_command)
    assert 'mcp_servers.agentweave.command="python"' in codex
    assert 'mcp_servers.agentweave.args=["C:/agentweave/hub/mcp_server.py"]' in codex


@pytest.mark.asyncio
async def test_request_agent_copies_preapproved_template_and_queues_work(app, auth_headers):
    from hub.db.engine import async_session_factory

    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.agent_budget = 3
        session_row = await session.get(ProjectSession, "proj-test")
        session_data = {
            "agents": {
                "lead": {"runner": "claude", "principal": True},
                "worker-template": {"runner": "claude", "model": "haiku"},
            }
        }
        if session_row:
            session_row.data = session_data
        else:
            session.add(ProjectSession(project_id="proj-test", data=session_data))
        session.add(
            Run(
                id="run-source",
                project_id="proj-test",
                agent="lead",
                status="running",
                turn_depth=0,
            )
        )
        await session.commit()

    response = await app.post(
        "/api/v1/projects/proj-test/agents/request",
        headers=auth_headers,
        json={
            "name": "worker-2",
            "template": "worker-template",
            "task": "Implement the queue consumer",
            "run_id": "run-source",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "queued"

    async with async_session_factory() as session:
        agent = (
            await session.execute(
                select(Agent).where(Agent.project_id == "proj-test", Agent.name == "worker-2")
            )
        ).scalar_one()
        assert agent.config["model"] == "haiku"
        entry = (
            await session.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.agent == "worker-2")
            )
        ).scalar_one()
        assert entry.origin_agent == "lead"
        assert entry.hop_depth == 1
        assert entry.content == "Implement the queue consumer"


@pytest.mark.asyncio
async def test_request_agent_refuses_to_exceed_project_budget(app, auth_headers):
    from hub.db.engine import async_session_factory

    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.agent_budget = 1
        session_row = await session.get(ProjectSession, "proj-test")
        session_data = {"agents": {"lead": {"runner": "claude"}, "template": {"runner": "claude"}}}
        if session_row:
            session_row.data = session_data
        else:
            session.add(ProjectSession(project_id="proj-test", data=session_data))
        session.add(
            Run(
                id="run-budget",
                project_id="proj-test",
                agent="lead",
                status="running",
                turn_depth=0,
            )
        )
        await session.commit()

    response = await app.post(
        "/api/v1/projects/proj-test/agents/request",
        headers=auth_headers,
        json={"name": "extra", "template": "template", "task": "work", "run_id": "run-budget"},
    )
    assert response.status_code == 409
    assert "agent budget" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_agent_job_mutation_requires_operator_allowance(app, auth_headers):
    denied_headers = {
        **auth_headers,
        "X-AgentWeave-Agent": "lead",
        "X-AgentWeave-Run": "run-job-agent",
    }
    from hub.db.engine import async_session_factory

    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-job-agent",
                project_id="proj-test",
                agent="lead",
                status="running",
                turn_depth=0,
            )
        )
        await session.commit()

    body = {
        "name": "nightly",
        "agent": "lead",
        "message": "run tests",
        "cron": "0 2 * * *",
        "session_mode": "new",
    }
    denied = await app.post("/api/v1/projects/proj-test/jobs", headers=denied_headers, json=body)
    assert denied.status_code == 403
    assert "operator approval" in denied.json()["detail"].lower()

    settings = await app.patch(
        "/api/v1/projects/proj-test/queue/settings",
        headers=auth_headers,
        json={
            "hop_budget": 6,
            "turn_delivery_cap": 10,
            "agent_budget": 8,
            "allow_agent_jobs": True,
        },
    )
    assert settings.status_code == 200
    allowed = await app.post("/api/v1/projects/proj-test/jobs", headers=denied_headers, json=body)
    assert allowed.status_code == 201, allowed.text
    reset = await app.patch(
        "/api/v1/projects/proj-test/queue/settings",
        headers=auth_headers,
        json={
            "hop_budget": 6,
            "turn_delivery_cap": 10,
            "agent_budget": 8,
            "allow_agent_jobs": False,
        },
    )
    assert reset.status_code == 200


@pytest.mark.asyncio
async def test_full_multi_agent_command_session_needs_no_tool_protocol_server(app, auth_headers):
    """The ordinary-command REST path retains every outbound agent capability."""
    from hub.db.engine import async_session_factory

    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.agent_budget = 20
        session_row = await session.get(ProjectSession, "proj-test")
        data = dict(session_row.data if session_row else {})
        agents = dict(data.get("agents", {}))
        agents.update(
            {
                "cli-lead": {"runner": "manual", "hub_client": "cli"},
                "cli-worker": {"runner": "manual", "hub_client": "cli"},
                "cli-template": {"runner": "manual", "hub_client": "cli"},
            }
        )
        data["agents"] = agents
        if session_row:
            session_row.data = data
        else:
            session.add(ProjectSession(project_id="proj-test", data=data))
        for agent_name in ("cli-lead", "cli-worker", "cli-template"):
            existing = await session.get(Agent, agent_name)
            if existing is None:
                session.add(
                    Agent(id=agent_name, project_id="proj-test", name=agent_name)
                )
        session.add(
            Run(
                id="run-cli-session",
                project_id="proj-test",
                agent="cli-lead",
                status="running",
                turn_depth=0,
            )
        )
        await session.commit()

    task = await app.post(
        "/api/v1/projects/proj-test/tasks",
        headers=auth_headers,
        json={
            "title": "Command-only task",
            "description": "verify parity",
            "assignee": "cli-worker",
            "assigner": "cli-lead",
            "priority": "medium",
            "requirements": [],
            "acceptance_criteria": [],
        },
    )
    assert task.status_code == 201
    updated = await app.patch(
        f"/api/v1/projects/proj-test/tasks/{task.json()['id']}",
        headers=auth_headers,
        json={"status": "in_progress"},
    )
    assert updated.status_code == 200

    message = await app.post(
        "/api/v1/projects/proj-test/messages",
        headers=auth_headers,
        json={
            "from": "cli-lead",
            "to": "cli-worker",
            "subject": "Work",
            "content": "Handle the command-path task",
            "type": "delegation",
            "run_id": "run-cli-session",
        },
    )
    assert message.status_code == 201

    question = await app.post(
        "/api/v1/projects/proj-test/questions",
        headers=auth_headers,
        json={"from_agent": "cli-lead", "question": "Proceed?", "blocking": False, "header": "Decide", "options": [{"label": "Yes"}, {"label": "No"}], "multi_select": False},
    )
    assert question.status_code == 201
    answer_poll = await app.get(
        f"/api/v1/projects/proj-test/questions/{question.json()['id']}", headers=auth_headers
    )
    assert answer_poll.status_code == 200

    requested = await app.post(
        "/api/v1/projects/proj-test/agents/request",
        headers=auth_headers,
        json={
            "name": "cli-worker-2",
            "template": "cli-template",
            "task": "Assist cli-worker",
            "run_id": "run-cli-session",
        },
    )
    assert requested.status_code == 201
    assert requested.json()["status"] == "queued"

    worker_queue = await app.get(
        "/api/v1/projects/proj-test/queue/cli-worker?state=queued", headers=auth_headers
    )
    assert any(entry["origin_agent"] == "cli-lead" for entry in worker_queue.json())
