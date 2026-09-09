"""Governed agent-request and scheduled-work capabilities."""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.api.v1.agents import FULL_ACCESS_PERMISSION_MODE
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AIJob,
    JobRun,
    Loop,
    PermissionRequest,
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

    # Archiving is the real alternative (B2.2) — but it is the one job mutation the allowance does
    # not settle. **This block asserted the opposite until 2026-09-09**: it archived with only the
    # standing allowance, expected 200, and said in a comment that archiving was "governed by the
    # same allowance as every other agent-originated job mutation". That was one side of a live
    # disagreement — `archive_job`'s own docstring and design D18 said the operator must direct
    # every archive — and the answer depended on which adapter the agent came through. The operator
    # settled it on the D18 side by approving this change, whose delta states it as a scenario of
    # its own (*"Archiving scheduled work is directed, on either path"*), so a green test was
    # asserting behaviour this change removes. See §3.9 of
    # `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`.
    refused = await app.post(f"/api/v1/agent-actions/jobs/{job_id}/archive", headers=headers)
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "operator_direction_required"
    request_id = detail["permission_request_id"]
    async with async_session_factory() as session:
        job = await session.get(AIJob, job_id)
        assert job.archived_at is None

    decided = await app.post(
        f"/api/v1/projects/proj-test/permission-requests/{request_id}/decide",
        headers=auth_headers,
        json={"allow": True},
    )
    assert decided.status_code == 200, decided.text

    # The caller repeats the request the refusal told it to repeat, and it retains the archiving
    # run's attribution — the half of this block that is unchanged.
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


async def _job_for_archiving(app, headers, name: str = "archivable") -> str:
    created = await app.post(
        "/api/v1/agent-actions/jobs",
        headers=headers,
        json={"name": name, "agent": "lead", "message": "run tests", "cron": "0 2 * * *"},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _cards(job_id: str) -> list:
    """Every direction request opened for this job, oldest first."""
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(PermissionRequest)
                .where(PermissionRequest.tool_use_id == f"archive-{job_id}")
                .order_by(PermissionRequest.created_at)
            )
        ).scalars()
        return list(rows)


@pytest.mark.asyncio
async def test_archiving_needs_direction_under_the_most_permissive_posture(app, auth_headers):
    """3.3: the rule is *whatever the run's permission posture is*, and posture is the case that
    would quietly satisfy it.

    `full_access` is the most permissive posture an agent can be given, and it is the one an
    unattended run has. It reaches this route through nothing — the posture is an environment
    variable of the spawned process — so what this test really pins is that no path exists by
    which it could, and it is here because the alternative to a test is a comment claiming so.
    """
    headers = await _actor(run_id="run-posture")
    await _allow_agent_jobs(app, auth_headers)
    async with async_session_factory() as session:
        agent = (
            await session.execute(select(Agent).where(Agent.name == "lead"))
        ).scalar_one_or_none()
        if agent is None:
            agent = Agent(id="agent-posture", project_id="proj-test", name="lead")
            session.add(agent)
        agent.default_permission_mode = FULL_ACCESS_PERMISSION_MODE
        agent.config = {**(agent.config or {}), "yolo": True}
        await session.commit()

    job_id = await _job_for_archiving(app, headers, name="posture job")
    refused = await app.post(f"/api/v1/agent-actions/jobs/{job_id}/archive", headers=headers)

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "operator_direction_required"
    async with async_session_factory() as session:
        assert (await session.get(AIJob, job_id)).archived_at is None


@pytest.mark.asyncio
async def test_the_standing_allowance_is_not_a_standing_yes(app, auth_headers):
    """3.3 from the other side: the allowance is on, and it is what let this job be created and
    every other mutation of it go through. It still does not archive it."""
    headers = await _actor(run_id="run-allowance")
    await _allow_agent_jobs(app, auth_headers)
    job_id = await _job_for_archiving(app, headers, name="allowance job")

    toggled = await app.patch(
        f"/api/v1/agent-actions/jobs/{job_id}", headers=headers, json={"enabled": False}
    )
    assert toggled.status_code == 200, toggled.text

    refused = await app.post(f"/api/v1/agent-actions/jobs/{job_id}/archive", headers=headers)
    assert refused.status_code == 409, refused.text
    message = refused.json()["detail"]["message"]
    assert "standing allowance" in message
    # The refusal is only useful if it says what to do next, which for a caller with no injected
    # tool is the whole protocol: watch the request, then repeat this one.
    assert "/api/v1/agent-actions/permission-requests/" in message
    assert refused.json()["detail"]["poll"].endswith(
        refused.json()["detail"]["permission_request_id"]
    )


@pytest.mark.asyncio
async def test_a_caller_that_repeats_the_request_does_not_open_a_second_card(app, auth_headers):
    """A caller polling the effect rather than the request must not multiply the operator's work."""
    headers = await _actor(run_id="run-twice")
    await _allow_agent_jobs(app, auth_headers)
    job_id = await _job_for_archiving(app, headers, name="twice job")

    first = await app.post(f"/api/v1/agent-actions/jobs/{job_id}/archive", headers=headers)
    second = await app.post(f"/api/v1/agent-actions/jobs/{job_id}/archive", headers=headers)

    assert first.status_code == second.status_code == 409
    assert (
        first.json()["detail"]["permission_request_id"]
        == second.json()["detail"]["permission_request_id"]
    )
    assert len(await _cards(job_id)) == 1


@pytest.mark.asyncio
async def test_the_operators_refusal_is_an_answer_rather_than_a_hurdle(app, auth_headers):
    """A denial comes back as 403 and stays denied. 409 means *not yet*, 403 means *no*, and an
    agent that could turn the second into the first by asking again would be voting."""
    headers = await _actor(run_id="run-refused")
    await _allow_agent_jobs(app, auth_headers)
    job_id = await _job_for_archiving(app, headers, name="refused job")

    opened = await app.post(f"/api/v1/agent-actions/jobs/{job_id}/archive", headers=headers)
    request_id = opened.json()["detail"]["permission_request_id"]
    decided = await app.post(
        f"/api/v1/projects/proj-test/permission-requests/{request_id}/decide",
        headers=auth_headers,
        json={"allow": False},
    )
    assert decided.status_code == 200, decided.text

    refused = await app.post(f"/api/v1/agent-actions/jobs/{job_id}/archive", headers=headers)
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["code"] == "operator_refused"
    assert len(await _cards(job_id)) == 1
    async with async_session_factory() as session:
        assert (await session.get(AIJob, job_id)).archived_at is None


@pytest.mark.asyncio
async def test_no_card_is_opened_for_an_archive_that_could_not_have_happened(app, auth_headers):
    """Ordering: the direction gate runs after the allowance, and after the job is known to exist,
    to be unarchived and to have no loop. Asking a person to authorise a 404 is asking them to read
    something meaningless, and a card the run never comes back for is one they dismiss by hand."""
    headers = await _actor(run_id="run-ordering")
    await _allow_agent_jobs(app, auth_headers)

    missing = await app.post("/api/v1/agent-actions/jobs/job-nope/archive", headers=headers)
    assert missing.status_code == 404, missing.text
    assert await _cards("job-nope") == []

    loop_job = await app.post(
        "/api/v1/agent-actions/jobs",
        headers=headers,
        json={
            "name": "looping",
            "agent": "lead",
            "message": "work the queue",
            "cron": "0 2 * * *",
            "stop_when_queue_empties": True,
        },
    )
    assert loop_job.status_code == 201, loop_job.text
    loop_id = loop_job.json()["id"]
    refused = await app.post(f"/api/v1/agent-actions/jobs/{loop_id}/archive", headers=headers)
    assert refused.status_code == 400, refused.text
    assert "operator only" in refused.json()["detail"]
    assert await _cards(loop_id) == []

    # And a run whose allowance was withdrawn never reaches the gate either.
    plain_id = await _job_for_archiving(app, headers, name="ordering job")
    await app.patch(
        "/api/v1/projects/proj-test/queue/settings",
        headers=auth_headers,
        json={
            "hop_budget": 8,
            "turn_delivery_cap": 10,
            "agent_budget": 8,
            "allow_agent_jobs": False,
        },
    )
    ungoverned = await app.post(f"/api/v1/agent-actions/jobs/{plain_id}/archive", headers=headers)
    assert ungoverned.status_code == 403, ungoverned.text
    assert await _cards(plain_id) == []


@pytest.mark.asyncio
async def test_the_operators_own_archive_needs_no_direction(app, auth_headers):
    """The rule is about an agent acting without a person, so the person is not asked to authorise
    themselves. `agent_identity`/`run_identity` both absent is how the allowance check itself
    recognises an operator call; the gate mirrors that rather than restating it differently."""
    headers = await _actor(run_id="run-operator-path")
    await _allow_agent_jobs(app, auth_headers)
    job_id = await _job_for_archiving(app, headers, name="operator job")

    archived = await app.post(
        f"/api/v1/projects/proj-test/jobs/{job_id}/archive", headers=auth_headers
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived_at"] is not None
    assert await _cards(job_id) == []
