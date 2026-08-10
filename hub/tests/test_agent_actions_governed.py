"""Governed agent-request and scheduled-work capabilities."""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AgentJobDeletion, AIJob, JobRun, Project, ProjectSession, Run


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

    deleted = await app.delete(f"/api/v1/agent-actions/jobs/{job_id}", headers=headers)
    assert deleted.status_code == 204
    async with async_session_factory() as session:
        audit = (
            await session.execute(select(AgentJobDeletion).where(AgentJobDeletion.job_id == job_id))
        ).scalar_one()
        assert audit.run_id == "run-job-owner"
        assert audit.agent == "lead"
