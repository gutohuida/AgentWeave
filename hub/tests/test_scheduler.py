"""Tests for task 3.10: scheduled jobs route through the direct execution path.

`JobScheduler._do_fire_job` no longer creates a synthetic `Message` for the watchdog to
detect and re-trigger — it calls `agent_trigger.trigger_agent_directly` directly, the same
function `POST /agent/trigger` uses. `_job_agent_skip_reason` ports the self-registered-poll-
agent guard the removed watchdog function (`_trigger_agent_from_message`, deleted from
`src/agentweave/watchdog.py`) used to enforce, checked here against the Hub's own `Agent`
table instead of the CLI's session.json.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AIJob, InboundQueueEntry, JobRun, Loop, Message, Run, Task
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
async def test_fired_job_creates_a_run_via_direct_execution_not_a_message(
    app, auth_headers, bind_runner
):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"job-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("job-claude", cli="claude")

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
        assert runs[0].initiator == "autonomous"

        delivered = (
            await db.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.agent == "job-claude")
            )
        ).scalar_one()
        assert delivered.origin_type == "job"

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
async def test_job_arriving_while_agent_runs_is_queued(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"busy-job-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("busy-job-claude", cli="claude")

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

    assert success is True

    async with async_session_factory() as db:
        run = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalar_one()
        assert run.status == "fired"
        from hub.db.models import InboundQueueEntry

        queued = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(
                        InboundQueueEntry.agent == "busy-job-claude",
                        InboundQueueEntry.state == "queued",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert [entry.content for entry in queued] == ["hello from a scheduled job"]
        assert queued[0].origin_type == "job"


async def _make_loop(db, *, job_id, **fields):
    loop = Loop(id=f"loop-{job_id}", project_id="proj-test", job_id=job_id, **fields)
    db.add(loop)
    await db.commit()
    return loop


@pytest.mark.asyncio
async def test_loop_with_past_stop_at_skips_the_fire_and_disables_the_job():
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="stop-at", agent="loop-agent-stop-at")
        await _make_loop(
            db,
            job_id=job.id,
            purpose="test loop",
            stop_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        success = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert success is False

    async with async_session_factory() as db:
        refreshed_job = await db.get(AIJob, job.id)
        assert refreshed_job.enabled is False

        loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        assert loop.stop_reason is not None
        assert "stop time" in loop.stop_reason
        assert loop.stopped_at is not None

        run = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalar_one()
        assert run.status == "skipped"
        assert run.error_summary == loop.stop_reason

    # A subsequent manual fire still refuses — the job stays disabled, it does not fire anyway.
    async with async_session_factory() as db:
        refreshed_job = await db.get(AIJob, job.id)
        second_attempt = await scheduler._fire_job_internal(
            refreshed_job, trigger="manual", session=db
        )
    assert second_attempt is False


@pytest.mark.asyncio
async def test_loop_with_stop_when_queue_empties_and_no_tasks_stops():
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="empty-queue", agent="loop-agent-empty")
        await _make_loop(db, job_id=job.id, purpose="drain the queue", stop_when_queue_empties=True)

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        success = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert success is False

    async with async_session_factory() as db:
        refreshed_job = await db.get(AIJob, job.id)
        assert refreshed_job.enabled is False
        loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        assert "queue is empty" in loop.stop_reason


@pytest.mark.asyncio
async def test_loop_with_stop_when_queue_empties_and_a_pending_task_does_not_stop(
    app, auth_headers, bind_runner
):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-open": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-open", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 4343
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-job-open"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="open-queue", agent="loop-agent-open")
        loop = await _make_loop(
            db, job_id=job.id, purpose="keep going", stop_when_queue_empties=True
        )
        db.add(
            Task(
                id="task-loop-open-1",
                project_id="proj-test",
                title="still open",
                status="pending",
                loop_id=loop.id,
            )
        )
        await db.commit()

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
        refreshed_job = await db.get(AIJob, job.id)
        assert refreshed_job.enabled is True
        loop_row = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        assert loop_row.stop_reason is None
        assert loop_row.stopped_at is None

        run = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalar_one()
        assert run.status == "fired"
        assert run.conversation_id is not None
