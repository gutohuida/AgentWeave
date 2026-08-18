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
from hub.checkpoint_generation import render_checkpoint
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AIJob,
    Checkpoint,
    Conversation,
    EventLog,
    InboundQueueEntry,
    JobRun,
    Loop,
    Message,
    Question,
    Run,
    Task,
)
from hub.scheduler import _LOOP_BRIEFING_CHECKPOINT_CHARS, JobScheduler, _loop_stop_reason


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
async def test_loop_with_stop_when_queue_empties_and_a_drained_queue_stops():
    """Every task the loop ever held has reached a terminal status — that is a drained queue."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="empty-queue", agent="loop-agent-empty")
        loop = await _make_loop(
            db, job_id=job.id, purpose="drain the queue", stop_when_queue_empties=True
        )
        db.add(
            Task(
                id="task-loop-drained-1",
                project_id="proj-test",
                # `approved`, not `completed` — TERMINAL_FOR_BINDING is ("approved", "rejected"),
                # so a completed task is still open work awaiting review.
                title="finished",
                status="approved",
                loop_id=loop.id,
            )
        )
        await db.commit()

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
async def test_loop_with_stop_when_queue_empties_and_no_tasks_yet_keeps_running():
    """A loop created before its work exists must not disable itself on its first tick.

    Create-then-populate is the natural order for the "shorter dev loops that keep developing"
    the stop condition is meant to serve. Arming "queue is empty" at creation would kill the loop
    permanently (`job.enabled = False`) before it had ever run anything — so the condition means
    *drained*, and a queue that has never held a task has not drained.
    """
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="unpopulated", agent="loop-agent-unpopulated")
        await _make_loop(
            db, job_id=job.id, purpose="about to be filled", stop_when_queue_empties=True
        )

    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        reason = await _loop_stop_reason(db, fresh_job)

    assert reason is None

    async with async_session_factory() as db:
        refreshed_job = await db.get(AIJob, job.id)
        assert refreshed_job.enabled is True
        loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        assert loop.stop_reason is None
        assert loop.stopped_at is None


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


@pytest.mark.asyncio
async def test_loop_fire_claims_the_oldest_pending_task(app, auth_headers, bind_runner):
    """Task 6.1/6.2: with only entry-status (`pending`) candidates, the firing claims the
    oldest by `created_at` — not the most recently created — and stamps it `assigned` with
    `assignee=job.agent`. The newer pending task is left untouched."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-claim-oldest": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-claim-oldest", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 4444
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-claim-1"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="claim-oldest", agent="loop-agent-claim-oldest")
        loop = await _make_loop(db, job_id=job.id, purpose="claim the oldest")
        db.add(
            Task(
                id="task-loop-claim-newer",
                project_id="proj-test",
                title="newer",
                status="pending",
                loop_id=loop.id,
                created_at=now,
            )
        )
        db.add(
            Task(
                id="task-loop-claim-older",
                project_id="proj-test",
                title="older",
                status="pending",
                loop_id=loop.id,
                created_at=now - timedelta(minutes=5),
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
        older = await db.get(Task, "task-loop-claim-older")
        newer = await db.get(Task, "task-loop-claim-newer")
        assert older.status == "assigned"
        assert older.assignee == "loop-agent-claim-oldest"
        assert newer.status == "pending"
        assert newer.assignee is None


@pytest.mark.asyncio
async def test_loop_fire_resumes_an_active_task_instead_of_claiming_another(
    app, auth_headers, bind_runner
):
    """Task 6.1/6.2: an existing `in_progress` task in the queue wins over a `pending` one —
    resumed (status left untouched) rather than re-entered — and only that task's `assignee`
    is stamped. The pending task is not touched at all."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-resume": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-resume", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 4545
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-resume-1"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="resume", agent="loop-agent-resume")
        loop = await _make_loop(db, job_id=job.id, purpose="resume in-progress work")
        db.add(
            Task(
                id="task-loop-resume-active",
                project_id="proj-test",
                title="already underway",
                status="in_progress",
                loop_id=loop.id,
            )
        )
        db.add(
            Task(
                id="task-loop-resume-pending",
                project_id="proj-test",
                title="not yet started",
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
        active = await db.get(Task, "task-loop-resume-active")
        pending = await db.get(Task, "task-loop-resume-pending")
        assert active.status == "in_progress"
        assert active.assignee == "loop-agent-resume"
        assert pending.status == "pending"
        assert pending.assignee is None


@pytest.mark.asyncio
async def test_loop_fire_with_empty_queue_claims_nothing_and_does_not_error(
    app, auth_headers, bind_runner
):
    """Task 6.3: a loop with no `stop_when_queue_empties` and no tasks at all still fires —
    the empty-queue stop condition does not apply, so this exercises `_claim_loop_task`'s own
    empty-candidate path (`None`) rather than being pre-empted by `_loop_stop_reason`."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-empty-no-stop": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-empty-no-stop", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 4646
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-empty-1"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="empty-no-stop", agent="loop-agent-empty-no-stop")
        await _make_loop(db, job_id=job.id, purpose="no tasks yet, no stop condition")

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
        run = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalar_one()
        assert run.status == "fired"
        tasks = (
            (await db.execute(select(Task).where(Task.loop_id == f"loop-{job.id}"))).scalars().all()
        )
        assert tasks == []


async def _make_checkpoint(db, *, checkpoint_id, loop_id, conversation_id, body):
    """A checkpoint attributed to `loop_id`, in a conversation OTHER than the one about to fire
    — mirrors L7's own `test_latest_checkpoint_for_loop_crosses_conversations`, since a loop's
    next firing is, by construction, a conversation that does not exist yet (task 7.2's own
    docstring)."""
    conversation = Conversation(id=conversation_id, project_id="proj-test", agent="irrelevant")
    db.add(conversation)
    checkpoint = Checkpoint(
        id=checkpoint_id,
        project_id="proj-test",
        conversation_id=conversation_id,
        loop_id=loop_id,
        agent="irrelevant",
        trigger="operator",
        status="ready",
        lineage_id=checkpoint_id,
        body=body,
    )
    db.add(checkpoint)
    await db.commit()
    return checkpoint


@pytest.mark.asyncio
async def test_loop_briefing_omits_prior_checkpoint_section_on_a_first_firing(
    app, auth_headers, bind_runner
):
    """Task 9.3: a loop's first firing has no prior checkpoint at all — the briefing must not
    claim one exists."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-briefing-first": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-briefing-first", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 4747
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-briefing-1"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="briefing-first", agent="loop-agent-briefing-first")
        loop = await _make_loop(db, job_id=job.id, purpose="brief the first firing")
        db.add(
            Task(
                id="task-loop-briefing-first",
                project_id="proj-test",
                title="the only task",
                description="do the thing",
                acceptance_criteria=["it works"],
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
        entry = (
            await db.execute(
                select(InboundQueueEntry).where(
                    InboundQueueEntry.agent == "loop-agent-briefing-first"
                )
            )
        ).scalar_one()

    assert "# Loop briefing" in entry.content
    assert "Purpose: brief the first firing" in entry.content
    assert "## Current task: the only task" in entry.content
    assert "do the thing" in entry.content
    assert "it works" in entry.content
    assert "## Prior checkpoint" not in entry.content
    assert "Queue: 1 open, 0 done" in entry.content
    assert entry.content.endswith("hello from a scheduled job")


@pytest.mark.asyncio
async def test_loop_briefing_includes_a_prior_checkpoint_in_full_under_the_cap(
    app, auth_headers, bind_runner
):
    """Task 9.3: a later firing's briefing carries the prior firing's checkpoint body in full,
    reused from a DIFFERENT conversation than the one about to fire (a loop's checkpoint is
    scoped by `loop_id`, never by `conversation_id` — see `_make_checkpoint`)."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-briefing-prior": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-briefing-prior", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 4848
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-briefing-2"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="briefing-prior", agent="loop-agent-briefing-prior")
        loop = await _make_loop(db, job_id=job.id, purpose="brief a later firing")
        checkpoint = await _make_checkpoint(
            db,
            checkpoint_id="cp-briefing-prior",
            loop_id=loop.id,
            conversation_id="conv-briefing-prior-earlier",
            body="Made progress on the queue. Nothing blocking.",
        )
        db.add(
            Task(
                id="task-loop-briefing-prior",
                project_id="proj-test",
                title="continue the work",
                status="pending",
                loop_id=loop.id,
            )
        )
        await db.commit()
        rendered = render_checkpoint(checkpoint)

    assert len(rendered) <= _LOOP_BRIEFING_CHECKPOINT_CHARS, "fixture must stay under the cap"

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
        entry = (
            await db.execute(
                select(InboundQueueEntry).where(
                    InboundQueueEntry.agent == "loop-agent-briefing-prior"
                )
            )
        ).scalar_one()

    assert "## Prior checkpoint" in entry.content
    assert rendered in entry.content


@pytest.mark.asyncio
async def test_loop_briefing_truncates_an_oversized_prior_checkpoint_to_exactly_the_cap(
    app, auth_headers, bind_runner
):
    """Task 9.3: an over-cap checkpoint is truncated to EXACTLY `_LOOP_BRIEFING_CHECKPOINT_CHARS`
    — not omitted, not truncated to some other length."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-briefing-overcap": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-briefing-overcap", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 4949
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-briefing-3"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="briefing-overcap", agent="loop-agent-briefing-overcap")
        loop = await _make_loop(db, job_id=job.id, purpose="brief an over-cap firing")
        checkpoint = await _make_checkpoint(
            db,
            checkpoint_id="cp-briefing-overcap",
            loop_id=loop.id,
            conversation_id="conv-briefing-overcap-earlier",
            body="x" * 10_000,
        )
        await db.commit()
        rendered = render_checkpoint(checkpoint)

    assert len(rendered) > _LOOP_BRIEFING_CHECKPOINT_CHARS, "fixture must exceed the cap"
    expected_truncated = rendered[:_LOOP_BRIEFING_CHECKPOINT_CHARS]

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
        entry = (
            await db.execute(
                select(InboundQueueEntry).where(
                    InboundQueueEntry.agent == "loop-agent-briefing-overcap"
                )
            )
        ).scalar_one()

    section_start = entry.content.index("## Prior checkpoint\n\n")
    section = entry.content[section_start + len("## Prior checkpoint\n\n") :]
    section = section[: len(expected_truncated)]
    assert section == expected_truncated
    assert len(section) == _LOOP_BRIEFING_CHECKPOINT_CHARS
    assert rendered not in entry.content


@pytest.mark.asyncio
async def test_non_loop_job_fired_content_is_byte_identical_to_job_message(
    app, auth_headers, bind_runner
):
    """Task 9.3: the regression guard for every non-loop job in the whole suite — no `Loop` row
    means no briefing is composed at all, and `job.message` reaches the queue untouched."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"job-agent-no-loop": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("job-agent-no-loop", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 5050
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-no-loop"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="no-loop", agent="job-agent-no-loop")

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
        entry = (
            await db.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.agent == "job-agent-no-loop")
            )
        ).scalar_one()

    assert entry.content == job.message == "hello from a scheduled job"


@pytest.mark.asyncio
async def test_loop_queue_exhausted_event_fires_with_no_pending_request():
    """Task 10.1/10.2: the queue draining with nothing else outstanding still fires the new
    `loop_queue_exhausted` event, with `pending_request` null — and the existing `loop_stopped`
    event keeps firing exactly as before (a regression guard: this section adds a second event, it
    does not replace or alter the first)."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="exhausted-clean", agent="loop-agent-exhausted-clean")
        loop = await _make_loop(
            db, job_id=job.id, purpose="drain cleanly", stop_when_queue_empties=True
        )
        db.add(
            Task(
                id="task-loop-exhausted-clean-1",
                project_id="proj-test",
                title="finished",
                status="approved",
                loop_id=loop.id,
            )
        )
        await db.commit()

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        success = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert success is False

    async with async_session_factory() as db:
        refreshed_job = await db.get(AIJob, job.id)
        assert refreshed_job.enabled is False
        refreshed_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        assert refreshed_loop.stopped_at is not None

        stopped_events = (
            (
                await db.execute(
                    select(EventLog).where(
                        EventLog.project_id == "proj-test", EventLog.event_type == "loop_stopped"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert any(e.data.get("loop_id") == loop.id for e in stopped_events)

        exhausted_events = (
            (
                await db.execute(
                    select(EventLog).where(
                        EventLog.project_id == "proj-test",
                        EventLog.event_type == "loop_queue_exhausted",
                    )
                )
            )
            .scalars()
            .all()
        )
        matching = [e for e in exhausted_events if e.data.get("loop_id") == loop.id]

    assert len(matching) == 1
    assert matching[0].data["job_id"] == job.id
    assert matching[0].data["pending_request"] is None


@pytest.mark.asyncio
async def test_loop_queue_exhausted_event_names_an_unread_message_to_the_creator():
    """The `Message` case: mail from the loop's executor to its creator, still unread when the
    queue drains, is named on the event. `to` is the `Message` model's own `recipient` field, not a
    conversation match — only the `Question` half of D6's sentence carries a conversation
    qualifier, grammatically."""
    async with async_session_factory() as db:
        creator_run = Run(
            id="run-loop-exhausted-creator",
            project_id="proj-test",
            agent="loop-creator-agent",
            status="completed",
        )
        db.add(creator_run)
        await db.commit()

        job = await _make_job(db, suffix="exhausted-message", agent="loop-agent-exhausted-message")
        loop = await _make_loop(
            db,
            job_id=job.id,
            purpose="wait on the creator",
            stop_when_queue_empties=True,
            created_by_run_id=creator_run.id,
        )
        db.add(
            Task(
                id="task-loop-exhausted-message-1",
                project_id="proj-test",
                title="finished",
                status="approved",
                loop_id=loop.id,
            )
        )
        db.add(
            Message(
                id="msg-loop-exhausted-1",
                project_id="proj-test",
                sender="loop-agent-exhausted-message",
                recipient="loop-creator-agent",
                subject="need a decision",
                content="need a decision on the next batch",
                read=False,
            )
        )
        await db.commit()

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        success = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert success is False

    async with async_session_factory() as db:
        refreshed_job = await db.get(AIJob, job.id)
        assert refreshed_job.enabled is False
        refreshed_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        assert refreshed_loop.stopped_at is not None

        exhausted_events = (
            (
                await db.execute(
                    select(EventLog).where(
                        EventLog.project_id == "proj-test",
                        EventLog.event_type == "loop_queue_exhausted",
                    )
                )
            )
            .scalars()
            .all()
        )
        matching = [e for e in exhausted_events if e.data.get("loop_id") == loop.id]

    assert len(matching) == 1
    pending = matching[0].data["pending_request"]
    assert pending["kind"] == "message"
    assert pending["to"] == "loop-creator-agent"
    assert pending["reason"] == "need a decision"
    assert pending["created_at"] is not None


@pytest.mark.asyncio
async def test_loop_queue_exhausted_event_names_an_unanswered_question_from_a_prior_firing():
    """The `Question` case. Loop jobs never resume a conversation — task 8.1 refuses
    `session_mode="resume"` for the whole lifetime of a loop job, not just at creation — so THIS
    firing's own conversation is always brand new and empty at the point the queue is found empty.
    A pending `ask_user` has to be found in the most recent EARLIER firing's conversation instead,
    via that firing's `JobRun.conversation_id`."""
    async with async_session_factory() as db:
        job = await _make_job(
            db, suffix="exhausted-question", agent="loop-agent-exhausted-question"
        )
        loop = await _make_loop(
            db, job_id=job.id, purpose="wait on an answer", stop_when_queue_empties=True
        )
        db.add(
            Task(
                id="task-loop-exhausted-question-1",
                project_id="proj-test",
                title="finished",
                status="approved",
                loop_id=loop.id,
            )
        )
        db.add(
            JobRun(
                id="jobrun-loop-exhausted-question-prior",
                job_id=job.id,
                project_id="proj-test",
                status="fired",
                trigger="scheduled",
                conversation_id="conv-loop-exhausted-question-prior",
            )
        )
        db.add(
            Question(
                id="question-loop-exhausted-1",
                project_id="proj-test",
                from_agent="loop-agent-exhausted-question",
                question="should the loop keep going past batch 3?",
                answered=False,
                conversation_id="conv-loop-exhausted-question-prior",
            )
        )
        await db.commit()

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        success = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert success is False

    async with async_session_factory() as db:
        refreshed_job = await db.get(AIJob, job.id)
        assert refreshed_job.enabled is False
        refreshed_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        assert refreshed_loop.stopped_at is not None

        exhausted_events = (
            (
                await db.execute(
                    select(EventLog).where(
                        EventLog.project_id == "proj-test",
                        EventLog.event_type == "loop_queue_exhausted",
                    )
                )
            )
            .scalars()
            .all()
        )
        matching = [e for e in exhausted_events if e.data.get("loop_id") == loop.id]

    assert len(matching) == 1
    pending = matching[0].data["pending_request"]
    assert pending["kind"] == "question"
    assert pending["to"] is None
    assert pending["reason"] == "should the loop keep going past batch 3?"
    assert pending["created_at"] is not None


@pytest.mark.asyncio
async def test_loop_queue_exhausted_event_prefers_the_question_when_both_are_outstanding():
    """When an unanswered `Question` from a prior firing AND an unread `Message` to the creator
    are both outstanding, the event names the `Question` — design decision recorded in
    `tasks.md`'s 10.1/10.2 note: a `Question` is a hard block on the run that asked it, closer to
    "what this loop was actually waiting on" than mail sitting unread, and D6 states no tiebreak."""
    async with async_session_factory() as db:
        creator_run = Run(
            id="run-loop-exhausted-both-creator",
            project_id="proj-test",
            agent="loop-creator-agent-both",
            status="completed",
        )
        db.add(creator_run)
        await db.commit()

        job = await _make_job(db, suffix="exhausted-both", agent="loop-agent-exhausted-both")
        loop = await _make_loop(
            db,
            job_id=job.id,
            purpose="wait on either",
            stop_when_queue_empties=True,
            created_by_run_id=creator_run.id,
        )
        db.add(
            Task(
                id="task-loop-exhausted-both-1",
                project_id="proj-test",
                title="finished",
                status="approved",
                loop_id=loop.id,
            )
        )
        db.add(
            JobRun(
                id="jobrun-loop-exhausted-both-prior",
                job_id=job.id,
                project_id="proj-test",
                status="fired",
                trigger="scheduled",
                conversation_id="conv-loop-exhausted-both-prior",
            )
        )
        db.add(
            Question(
                id="question-loop-exhausted-both-1",
                project_id="proj-test",
                from_agent="loop-agent-exhausted-both",
                question="which of the two should win?",
                answered=False,
                conversation_id="conv-loop-exhausted-both-prior",
            )
        )
        db.add(
            Message(
                id="msg-loop-exhausted-both-1",
                project_id="proj-test",
                sender="loop-agent-exhausted-both",
                recipient="loop-creator-agent-both",
                subject="also waiting on this",
                content="also waiting on this",
                read=False,
            )
        )
        await db.commit()

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        success = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert success is False

    async with async_session_factory() as db:
        exhausted_events = (
            (
                await db.execute(
                    select(EventLog).where(
                        EventLog.project_id == "proj-test",
                        EventLog.event_type == "loop_queue_exhausted",
                    )
                )
            )
            .scalars()
            .all()
        )
        matching = [e for e in exhausted_events if e.data.get("loop_id") == loop.id]

    assert len(matching) == 1
    assert matching[0].data["pending_request"]["kind"] == "question"
