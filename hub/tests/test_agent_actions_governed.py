"""Governed agent-request and scheduled-work capabilities."""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AIJob,
    JobRun,
    Loop,
    Project,
    ProjectSession,
    Run,
    Task,
)


async def _actor(agent: str = "lead", run_id: str = "run-governed") -> dict[str, str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_agent_request_uses_bound_requester_template_and_budget(app):
    headers = await _actor()
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.agent_budget = 3
        session.add(
            ProjectSession(
                project_id="proj-test",
                data={
                    "agents": {
                        "lead": {"runner": "claude", "principal": True},
                        "worker-template": {"runner": "manual", "model": "small"},
                    }
                },
            )
        )
        await session.commit()

    rejected = await app.post(
        "/api/v1/agent-actions/agents/request",
        headers=headers,
        json={"name": "worker", "template": "worker-template", "task": "work", "run_id": "x"},
    )
    assert rejected.status_code == 422

    response = await app.post(
        "/api/v1/agent-actions/agents/request",
        headers={**headers, "X-AgentWeave-Agent": "impostor"},
        json={"name": "worker", "template": "worker-template", "task": "do work"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["requester"] == "lead"

    async with async_session_factory() as session:
        agent = (await session.execute(select(Agent).where(Agent.name == "worker"))).scalar_one()
        assert agent.created_by_run_id == "run-governed"
        assert agent.config["model"] == "small"


@pytest.mark.asyncio
async def test_agent_job_operations_require_allowance_and_retain_run(app, auth_headers):
    headers = await _actor(run_id="run-job-owner")
    body = {
        "name": "nightly",
        "agent": "lead",
        "message": "run tests",
        "cron": "0 2 * * *",
        "enabled": True,
    }

    denied = await app.post("/api/v1/agent-actions/jobs", headers=headers, json=body)
    assert denied.status_code == 403

    settings = await app.patch(
        "/api/v1/projects/proj-test/queue/settings",
        headers=auth_headers,
        json={
            "hop_budget": 8,
            "turn_delivery_cap": 10,
            "agent_budget": 8,
            "allow_agent_jobs": True,
        },
    )
    assert settings.status_code == 200

    created = await app.post(
        "/api/v1/agent-actions/jobs",
        headers={**headers, "X-AgentWeave-Run": "fake"},
        json=body,
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    toggled = await app.patch(
        f"/api/v1/agent-actions/jobs/{job_id}", headers=headers, json={"enabled": False}
    )
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is False
    disabled_run = await app.post(f"/api/v1/agent-actions/jobs/{job_id}/run", headers=headers)
    assert disabled_run.status_code == 400

    await app.patch(f"/api/v1/agent-actions/jobs/{job_id}", headers=headers, json={"enabled": True})
    fired = await app.post(f"/api/v1/agent-actions/jobs/{job_id}/run", headers=headers)
    assert fired.status_code == 503

    async with async_session_factory() as session:
        job = await session.get(AIJob, job_id)
        assert job.created_by_run_id == "run-job-owner"
        assert job.updated_by_run_id == "run-job-owner"
        job_run = (
            await session.execute(select(JobRun).where(JobRun.job_id == job_id))
        ).scalar_one()
        assert job_run.requested_by_run_id == "run-job-owner"

    # D16 (B2.1): an agent's DELETE is refused exactly like the operator's — nothing is deletable.
    deleted = await app.delete(f"/api/v1/agent-actions/jobs/{job_id}", headers=headers)
    assert deleted.status_code == 400

    # Archiving is the real alternative (B2.2), governed by the same allowance as every other
    # agent-originated job mutation, and it retains the archiving run's attribution.
    archived = await app.post(f"/api/v1/agent-actions/jobs/{job_id}/archive", headers=headers)
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived_at"] is not None
    async with async_session_factory() as session:
        job = await session.get(AIJob, job_id)
        assert job.archived_at is not None
        assert job.updated_by_run_id == "run-job-owner"


async def _allow_agent_jobs(app, auth_headers):
    settings = await app.patch(
        "/api/v1/projects/proj-test/queue/settings",
        headers=auth_headers,
        json={
            "hop_budget": 8,
            "turn_delivery_cap": 10,
            "agent_budget": 8,
            "allow_agent_jobs": True,
        },
    )
    assert settings.status_code == 200


@pytest.mark.asyncio
async def test_create_loop_via_agent_actions_with_a_stop_condition_makes_an_empty_queue_loop(
    app, auth_headers
):
    """`create_loop` (`mcp_server.py`) posts here — `/agent-actions/jobs` widened with the loop
    fields (design D2, `2026-08-18-a-loop-writes-its-own-queue`). No `initial_tasks` supplied, so
    the loop exists with nothing queued."""
    headers = await _actor(run_id="run-loop-empty")
    await _allow_agent_jobs(app, auth_headers)

    created = await app.post(
        "/api/v1/agent-actions/jobs",
        headers=headers,
        json={
            "name": "nightly loop",
            "agent": "lead",
            "message": "work the queue",
            "cron": "0 2 * * *",
            "purpose": "decompose the backlog",
            "stop_when_queue_empties": True,
        },
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]
    loop = created.json()["loop"]
    assert loop is not None
    assert loop["purpose"] == "decompose the backlog"

    async with async_session_factory() as session:
        loop_row = (await session.execute(select(Loop).where(Loop.job_id == job_id))).scalar_one()
        assert loop_row.created_by_run_id == "run-loop-empty"
        queued = (
            (await session.execute(select(Task).where(Task.loop_id == loop_row.id))).scalars().all()
        )
        assert queued == []


@pytest.mark.asyncio
async def test_create_loop_via_agent_actions_with_initial_tasks_seeds_the_queue(app, auth_headers):
    """`initial_tasks` creates the named tasks with `loop_id` set to the new loop's id, in the
    same call (design D2 task 11.2) — the "definition window" is pre-first-fire authorship, so
    the loop's own creator adding to its own brand-new queue is never subject to design D7's
    already-fired gate (`job.run_count` is 0 for a job this same call just created)."""
    headers = await _actor(run_id="run-loop-seeded")
    await _allow_agent_jobs(app, auth_headers)

    created = await app.post(
        "/api/v1/agent-actions/jobs",
        headers=headers,
        json={
            "name": "seeded loop",
            "agent": "lead",
            "message": "work the queue",
            "cron": "0 2 * * *",
            "stop_when_queue_empties": True,
            "initial_tasks": [
                {"title": "First task", "description": "Do the first thing"},
                {"title": "Second task", "priority": "high"},
            ],
        },
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    async with async_session_factory() as session:
        loop_row = (await session.execute(select(Loop).where(Loop.job_id == job_id))).scalar_one()
        queued = (
            (await session.execute(select(Task).where(Task.loop_id == loop_row.id))).scalars().all()
        )
        assert {task.title for task in queued} == {"First task", "Second task"}
        assert all(task.loop_id == loop_row.id for task in queued)
        by_title = {task.title: task for task in queued}
        assert by_title["First task"].description == "Do the first thing"
        assert by_title["Second task"].priority == "high"


@pytest.mark.asyncio
async def test_archive_job_via_agent_actions_refuses_when_the_job_has_a_loop(app, auth_headers):
    """B3.3: a loop is archived by the operator only (mirrors B2.2's operator-only loop rule) —
    an agent's own governed archive route must not be a back door around that, even though the
    same route happily archives a bare job (see
    `test_agent_job_operations_require_allowance_and_retain_run` above). The operator's own path
    through this same route is unaffected."""
    headers = await _actor(run_id="run-loop-archive")
    await _allow_agent_jobs(app, auth_headers)

    created = await app.post(
        "/api/v1/agent-actions/jobs",
        headers=headers,
        json={
            "name": "loop to protect",
            "agent": "lead",
            "message": "work the queue",
            "cron": "0 2 * * *",
            "stop_when_queue_empties": True,
        },
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    refused = await app.post(f"/api/v1/agent-actions/jobs/{job_id}/archive", headers=headers)
    assert refused.status_code == 400
    assert "operator only" in refused.json()["detail"]

    async with async_session_factory() as session:
        job = await session.get(AIJob, job_id)
        assert job.archived_at is None

    # The operator's own path through the same route is not subject to this restriction.
    operator_archived = await app.post(
        f"/api/v1/projects/proj-test/jobs/{job_id}/archive", headers=auth_headers
    )
    assert operator_archived.status_code == 200, operator_archived.text


@pytest.mark.asyncio
async def test_create_loop_via_agent_actions_rejects_an_invalid_initial_task(app, auth_headers):
    """A malformed entry is refused (422) rather than silently dropped or stored half-shaped."""
    headers = await _actor(run_id="run-loop-bad-task")
    await _allow_agent_jobs(app, auth_headers)

    created = await app.post(
        "/api/v1/agent-actions/jobs",
        headers=headers,
        json={
            "name": "bad loop",
            "agent": "lead",
            "message": "work the queue",
            "cron": "0 2 * * *",
            "stop_when_queue_empties": True,
            "initial_tasks": [{"description": "No title at all"}],
        },
    )
    assert created.status_code == 422, created.text
