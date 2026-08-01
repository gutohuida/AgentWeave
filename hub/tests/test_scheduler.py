"""Tests for task 3.10: scheduled jobs route through the direct execution path.

`JobScheduler._do_fire_job` no longer creates a synthetic `Message` for the watchdog to
detect and re-trigger — it calls `agent_trigger.trigger_agent_directly` directly, the same
function `POST /agent/trigger` uses. `_job_agent_skip_reason` ports the pilot-mode and
self-registered-poll-agent guards the removed watchdog function
(`_trigger_agent_from_message`, deleted from `src/agentweave/watchdog.py`) used to enforce,
checked here against the Hub's own `Agent` table instead of the CLI's session.json.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AIJob, JobRun, Message, Run
from hub.scheduler import JobScheduler


async def _make_job(db, *, suffix, agent, session_mode="new"):
    job = AIJob(
        id=f"job-sched-{suffix}",
        project_id="proj-test",
        name=f"Test Job {suffix}",
        agent=agent,
        message="hello from a scheduled job",
        cron="0 9 * * *",
        session_mode=session_mode,
        enabled=True,
    )
    db.add(job)
    await db.commit()
    return job


@pytest.mark.asyncio
async def test_fired_job_creates_a_run_via_direct_execution_not_a_message(app, auth_headers):
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"job-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    fake_session = MagicMock()
    fake_session.pid = 4242
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-job-1"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="direct", agent="job-claude")

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            scheduler = JobScheduler()
            async with async_session_factory() as db:
                fresh_job = await db.get(AIJob, job.id)
                success = await scheduler._fire_job_internal(
                    fresh_job, trigger="scheduled", session=db
                )

            for task in list(agent_trigger._background_runs):
                await task

    assert success is True

    async with async_session_factory() as db:
        runs = (await db.execute(select(Run).where(Run.agent == "job-claude"))).scalars().all()
        assert len(runs) == 1
        assert runs[0].status == "completed"

        # The old protocol wrote a synthetic Message for the watchdog to scan and
        # re-trigger from; the direct-execution path must not write one at all.
        messages = (
            (await db.execute(select(Message).where(Message.recipient == "job-claude")))
            .scalars()
            .all()
        )
        assert messages == []

        job_runs = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
        assert len(job_runs) == 1
        assert job_runs[0].status == "fired"


@pytest.mark.asyncio
async def test_job_for_pilot_agent_is_skipped_not_fired(app, auth_headers):
    async with async_session_factory() as db:
        db.add(
            Agent(
                id="agent-pilot-sched",
                project_id="proj-test",
                name="pilot-job-agent",
                pilot=True,
            )
        )
        job = await _make_job(db, suffix="pilot", agent="pilot-job-agent")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        success = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert success is False

    async with async_session_factory() as db:
        run = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalar_one()
        assert run.status == "skipped"
        assert "pilot" in run.error_summary

        # No Run row (task 3.3's table) should exist — the agent was never spawned.
        agent_runs = (
            (await db.execute(select(Run).where(Run.agent == "pilot-job-agent"))).scalars().all()
        )
        assert agent_runs == []


@pytest.mark.asyncio
async def test_job_for_self_registered_poll_agent_is_skipped(app, auth_headers):
    async with async_session_factory() as db:
        db.add(
            Agent(
                id="agent-poll-sched",
                project_id="proj-test",
                name="poll-job-agent",
                self_registered=True,
                contact_mode="poll",
            )
        )
        job = await _make_job(db, suffix="poll", agent="poll-job-agent")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        success = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert success is False

    async with async_session_factory() as db:
        run = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalar_one()
        assert run.status == "skipped"
        assert "poll" in run.error_summary


@pytest.mark.asyncio
async def test_job_fire_failure_is_recorded_with_the_real_reason(app, auth_headers):
    # An agent that already has a run in progress makes trigger_agent_directly raise
    # TriggerAgentError deterministically (no CLI-availability mocking needed) — proves
    # the JobRun now records the *actual* rejection reason, not an assumed success.
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"busy-job-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    async with async_session_factory() as db:
        db.add(
            Run(
                id="run-busy-for-job",
                project_id="proj-test",
                agent="busy-job-claude",
                status="running",
            )
        )
        job = await _make_job(db, suffix="fail", agent="busy-job-claude")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        success = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert success is False

    async with async_session_factory() as db:
        run = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalar_one()
        assert run.status == "failed"
        assert "already has a run in progress" in run.error_summary


@pytest.mark.asyncio
async def test_run_job_endpoint_returns_409_for_a_skipped_pilot_agent(app, auth_headers):
    import hub.scheduler as scheduler_module

    create_resp = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Pilot Run Now Job",
            "agent": "pilot-run-now-agent",
            "message": "hi",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    job_id = create_resp.json()["id"]

    async with async_session_factory() as db:
        db.add(
            Agent(
                id="agent-pilot-run-now",
                project_id="proj-test",
                name="pilot-run-now-agent",
                pilot=True,
            )
        )
        await db.commit()

    scheduler_module._scheduler_instance = JobScheduler()
    try:
        resp = await app.post(f"/api/v1/jobs/{job_id}/run", headers=auth_headers)
        assert resp.status_code == 409
        assert "pilot" in resp.json()["detail"]
    finally:
        scheduler_module._scheduler_instance = None
