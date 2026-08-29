"""Tests for task 3.10: scheduled jobs route through the direct execution path.

`JobScheduler._do_fire_job` no longer creates a synthetic `Message` for the watchdog to
detect and re-trigger — it calls `agent_trigger.trigger_agent_directly` directly, the same
function `POST /agent/trigger` uses. `_job_agent_skip_reason` ports the self-registered-poll-
agent guard the removed watchdog function (`_trigger_agent_from_message`, deleted from
`src/agentweave/watchdog.py`) used to enforce, checked here against the Hub's own `Agent`
table instead of the CLI's session.json.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
import hub.api.v1.agents as agents_api
from hub import checkpoints
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
    RunDivergence,
    Task,
)
from hub.run_task_binding import TERMINAL_FOR_BINDING, release_block_for_question
from hub.scheduler import (
    _LOOP_BRIEFING_CHECKPOINT_CHARS,
    CLAIMABLE_LOOP_TASK_STATUSES,
    JobScheduler,
    _claim_loop_task,
    _loop_stall_reason,
    _loop_stop_reason,
    cron_day_ambiguity_reason,
    finalize_job_run_for_conversation,
)
from hub.task_transitions import TRANSITIONS


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


async def _claim_one(db, loop, agent="claim-probe"):
    """`loop-becomes-a-flow` group 1 made `_claim_loop_task` set-valued. This test was written
    against the scalar it used to return and asserts exactly the same fact about exactly the same
    claim; unwrapping here keeps the assertion about *the claim* rather than about its container.

    **Takes an agent as of `loop-becomes-a-flow` group 3**, because claimability became a question
    about a *(task, agent)* pair. These tests predate that and none of them is about review, so
    they pass a name no fixture ever records as completing anything -- which is what makes the
    claim they assert the actor-blind one they were written for.
    """
    claimed = await _claim_loop_task(db, loop, agent=agent)
    return claimed[0] if claimed else None


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
        # Design D13, task A4.3: the background run above actually completed.
        assert job_runs[0].status == "completed"


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
        # Design D13, task A4.3: the entry queued successfully, but the busy agent never
        # actually ran it in this test, so the firing is "in_progress", not yet a terminal
        # status — nothing here finalizes it, unlike the full round-trip tests below.
        assert run.status == "in_progress"
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


@pytest.mark.asyncio
async def test_job_that_cannot_start_records_the_queue_reason_as_failed():
    from hub.turn_scheduler import ScheduleResult

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="cannot-start", agent="unbound-job-agent")

    reason = "No runner is bound to this agent. Bind a runner before starting it."
    with patch(
        "hub.turn_scheduler.schedule_agent",
        AsyncMock(return_value=ScheduleResult(waiting_reason=reason)),
    ):
        scheduler = JobScheduler()
        async with async_session_factory() as db:
            fresh_job = await db.get(AIJob, job.id)
            success = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert success is True
    async with async_session_factory() as db:
        run = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalar_one()
        assert run.status == "failed"
        assert run.error_summary == reason


@pytest.mark.asyncio
async def test_a_request_level_refusal_still_fails_the_job_run():
    """F108 changed what the *operator's route* does with a refusal; the flow path is untouched.

    The sibling above covers an environment-level refusal. This one covers the population F108
    newly answers with a status code, and asserts the flow consumer is indifferent to it: a job
    firing into a request-level refusal still records `failed` with the reason, exactly as before.
    `terminal_failure` is what this branch reads and this change never touched it — the refusal is
    carried alongside, in a field only the route looks at.
    """
    from hub.turn_scheduler import ScheduleResult, TurnRefusal

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="request-level", agent="ghost-job-agent")

    reason = "ghost-job-agent is not an agent in this project, so there is nothing to trigger."
    with patch(
        "hub.turn_scheduler.schedule_agent",
        AsyncMock(
            return_value=ScheduleResult(
                waiting_reason=reason,
                refusal=TurnRefusal(status_code=409, detail=reason, entry_ids=("entry-x",)),
            )
        ),
    ):
        scheduler = JobScheduler()
        async with async_session_factory() as db:
            fresh_job = await db.get(AIJob, job.id)
            success = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert success is True
    async with async_session_factory() as db:
        run = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalar_one()
        assert run.status == "failed"
        assert run.error_summary == reason


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
        # B2.5/D17: `stop_at` elapsing is a "stopped" ending, never "completed" — only a drained
        # queue is.
        assert loop.ending_state == "stopped"

        run = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalar_one()
        assert run.status == "skipped"
        assert run.error_summary == loop.stop_reason
        conversations = (
            (await db.execute(select(Conversation).where(Conversation.agent == job.agent)))
            .scalars()
            .all()
        )
        assert conversations == []

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
        # B2.5/D17: a drained queue is "completed", the one ending distinct from every other
        # "stopped" path.
        assert loop.ending_state == "completed"


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
        # Design D13, task A4.3: the background run above actually completed, so
        # `finalize_job_run_for_conversation` (agent_trigger.py) has already flipped this out
        # of "in_progress".
        assert run.status == "completed"
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
        # `every-run-knows-its-task` D1/D2: the staged entry now carries `task_id`, so the run
        # that starts on it binds and advances it past `assigned` to `in_progress` before this
        # drain returns — the claim ladder's own outcome (which task got claimed) is unchanged.
        assert older.status == "in_progress"
        assert older.assignee == "loop-agent-claim-oldest"
        assert newer.status == "pending"
        assert newer.assignee is None


@pytest.mark.asyncio
async def test_loop_fire_claims_the_oldest_even_when_updated_differs(
    app, auth_headers, bind_runner
):
    """Regression, found live on 2026-08-19 by driving human-only check 13.1 against a real agent.

    `test_loop_fire_claims_the_oldest_pending_task` above sets only `created_at` and inserts both
    rows in one transaction, so their `updated` values tie *exactly* — and under a tie the
    `created_at` tiebreak decides, so it passed. Production creates tasks in separate requests,
    where `updated` differs by however far apart they were created, and the old
    `Task.updated.desc()` key then picked the **newest** pending task before `created_at` was ever
    consulted. The live loop claimed BRAVO while ALPHA sat pending.

    This test sets `updated` explicitly and in the *opposite* order to `created_at`, so it fails
    against the old ordering and can only pass if `updated` is scoped to non-pending rows.
    """
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-claim-updated": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-claim-updated", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 4455
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-claim-upd"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="claim-updated", agent="loop-agent-claim-updated")
        loop = await _make_loop(db, job_id=job.id, purpose="claim the oldest despite updated")
        db.add(
            Task(
                id="task-upd-older",
                project_id="proj-test",
                title="older",
                status="pending",
                loop_id=loop.id,
                created_at=now - timedelta(minutes=5),
                updated=now - timedelta(minutes=5),
            )
        )
        db.add(
            Task(
                id="task-upd-newer",
                project_id="proj-test",
                title="newer",
                status="pending",
                loop_id=loop.id,
                created_at=now,
                updated=now,
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
        older = await db.get(Task, "task-upd-older")
        newer = await db.get(Task, "task-upd-newer")
        # `every-run-knows-its-task` D1/D2: the started run binds and advances the claimed task
        # past `assigned` to `in_progress` — see the sibling test above for the full reasoning.
        assert older.status == "in_progress", "the OLDER pending task must be claimed"
        assert older.assignee == "loop-agent-claim-updated"
        assert newer.status == "pending", "the newer pending task must be left alone"
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
async def test_loop_fire_resumes_an_assigned_task_rather_than_stranding_it(
    app, auth_headers, bind_runner
):
    """13.1a, settled by the operator 2026-08-19: a firing resumes a claimed-but-unstarted task.

    A firing claims by moving `pending -> assigned`; reaching `in_progress` needs the agent to
    call `update_task` itself, which it may never do. While `assigned` was excluded from the claim
    candidates, that task became invisible to every later firing -- and `_loop_stop_reason` still
    counted it as open, since `TERMINAL_FOR_BINDING` is only `("approved", "rejected")`. The loop
    could then neither claim it nor stop because of it. Demonstrated live on the trial Hub
    (`loop-33deddaf`: three firings, nothing claimed, `stopped_at` still null).

    So: the loop's own claim ladder does not re-enter the older task's `assigned` status just to
    resume it — it was never at risk of being skipped. What happens next is a separate mechanism:
    the run started on it now binds via `task_id` (`every-run-knows-its-task` D1/D2) and advances
    it to `in_progress`, the same way any other bound run does. Before that change, a job/flow
    firing's queue entry never carried `task_id`, so this task sat labelled `assigned` for the
    whole time the agent was actually working on it — resumed, yes, but invisible in its own
    status. The newer pending task is left alone either way.
    """
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-resume-assigned": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-resume-assigned", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 4466
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-resume"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="resume-assigned", agent="loop-agent-resume-assigned")
        loop = await _make_loop(db, job_id=job.id, purpose="resume rather than strand")
        db.add(
            Task(
                id="task-resume-assigned",
                project_id="proj-test",
                title="claimed but never started",
                status="assigned",
                assignee="loop-agent-resume-assigned",
                loop_id=loop.id,
                created_at=now - timedelta(minutes=5),
                updated=now - timedelta(minutes=5),
            )
        )
        db.add(
            Task(
                id="task-resume-untouched",
                project_id="proj-test",
                title="newer, still pending",
                status="pending",
                loop_id=loop.id,
                created_at=now,
                updated=now,
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
        resumed = await db.get(Task, "task-resume-assigned")
        untouched = await db.get(Task, "task-resume-untouched")
        # Resumed and then advanced: the bound run moves it to `in_progress` (D1/D2), where before
        # this change it would have stayed `assigned` for the run's entire duration.
        assert resumed.status == "in_progress"
        assert resumed.assignee == "loop-agent-resume-assigned"
        # And the pending one is NOT claimed alongside it -- that skipping is what stranded work.
        assert untouched.status == "pending"
        assert untouched.assignee is None


def _statuses_in_neither_set() -> set:
    """The gap between the claim and the stop condition, derived rather than restated.

    A status in neither set is invisible to `_claim_loop_task` and counted as open by
    `_loop_stop_reason` at the same time -- the §3 spin. Computed from the transition map so that
    adding a status to the machine without placing it in one set or the other shows up here
    instead of as a loop that fires forever. Hardcoding this list is how it was miscounted once:
    `revision_needed` was in the gap and went unnoticed because the list said "completed,
    under_review" and nobody re-derived it.
    """
    all_statuses = set(TRANSITIONS) | {to for moves in TRANSITIONS.values() for to in moves}
    return all_statuses - set(CLAIMABLE_LOOP_TASK_STATUSES) - set(TERMINAL_FOR_BINDING)


def test_only_the_awaiting_someone_else_statuses_sit_in_the_claim_stop_gap():
    """The gap is legitimate for exactly the statuses that mean "someone else's turn".

    `completed` and `under_review` belong there: the loop's agent genuinely cannot act, so
    `_loop_stall_reason` names the wait rather than the claim swallowing it. Anything else in the
    gap is a bug -- `revision_needed` was, until 2026-08-20, and it stalled a loop whose reviewer
    had done everything right.

    `blocked` joined on 2026-08-21, moving *out* of the claim rather than failing to enter it. It is
    the most literal member: the "someone else" is a person, and the thing being waited on is a
    question only they can answer. Widening this expectation is the deliberate half of that change --
    the gap growing is correct here, where for `revision_needed` it was the bug.
    """
    assert _statuses_in_neither_set() == {"completed", "under_review", "blocked"}


def test_blocked_is_not_claimable_because_nothing_the_loop_can_fire_will_answer_it():
    """The mirror of the test below, and the reason they differ.

    Both statuses mean "work that stopped". `revision_needed` stopped because a reviewer sent it
    back, so the loop's own agent is exactly who resumes it. `blocked` stopped because a person was
    asked a question, and `park_task_for_question` is the only way in -- so a task sitting here has
    an **unanswered** question, and no agent the loop can fire is able to answer it.

    Answering is the resume: `release_block_for_question` moves the task to `in_progress`, which is
    claimable, on the very next tick. So stalling costs nothing and claiming costs a spawned agent
    per tick that cannot advance the work.

    See `openspec/explorations/2026-08-21-which-band-blocked-belongs-to.md`.
    """
    assert "blocked" not in CLAIMABLE_LOOP_TASK_STATUSES
    # Not terminal either -- it sits in the stall gap with `completed` and `under_review`, which is
    # what makes `_loop_stall_reason` name it instead of the claim swallowing it.
    assert "blocked" not in TERMINAL_FOR_BINDING
    assert "blocked" in _statuses_in_neither_set()
    # And the two sets that already agreed keep agreeing.
    assert "blocked" not in agents_api._ACTIVE_TASK_STATUSES
    assert "blocked" not in checkpoints._LIVE_TASK_STATUSES


def test_revision_needed_is_claimable_so_a_returned_review_resumes():
    """A reviewer who sends work back must not strand the loop.

    `revision_needed -> in_progress` is `_BOTH`, so the loop's own agent is exactly who should
    pick it up -- and two other status sets already treat it as live work.
    """
    assert "revision_needed" in CLAIMABLE_LOOP_TASK_STATUSES
    assert TRANSITIONS["revision_needed"]["in_progress"]
    assert "revision_needed" in agents_api._ACTIVE_TASK_STATUSES
    assert "revision_needed" in checkpoints._LIVE_TASK_STATUSES


@pytest.mark.asyncio
@pytest.mark.parametrize("stalled_status", sorted(_statuses_in_neither_set()))
async def test_a_stalled_loop_queue_is_neither_claimable_nor_drained(stalled_status):
    """Every status in the gap, parametrized from the gap itself rather than from a literal.

    A task awaiting review is invisible to `_claim_loop_task` and simultaneously counted as open
    by `_loop_stop_reason` -- that combination is what `_loop_stall_reason` exists to name. Driven
    off `_statuses_in_neither_set()` so a status that later falls into the gap is covered here the
    moment it does, without anyone remembering to add it.
    """

    suffix = f"stalled-{stalled_status}"
    async with async_session_factory() as db:
        job = await _make_job(db, suffix=suffix, agent=f"loop-agent-{suffix}")
        loop = await _make_loop(
            db, job_id=job.id, purpose="stalled, not drained", stop_when_queue_empties=True
        )
        db.add(
            Task(
                id=f"task-{suffix}",
                project_id="proj-test",
                title="worked, awaiting a reviewer",
                status=stalled_status,
                loop_id=loop.id,
            )
        )
        await db.commit()

    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        # Nothing to work on...
        assert await _claim_one(db, fresh_loop) is None
        # ...and no reason to stop, because the queue is stalled rather than drained.
        assert await _loop_stop_reason(db, fresh_job) is None
        # That combination used to mean "fire anyway". It now has a name of its own, and the
        # name carries the breakdown an operator needs to see what is being waited on.
        stall = await _loop_stall_reason(db, fresh_loop, agent="claim-probe")
        assert stall is not None
        assert "stalled" in stall
        assert f"1 {stalled_status}" in stall


@pytest.mark.asyncio
async def test_loop_whose_tasks_are_all_completed_but_unapproved_skips_instead_of_spinning(
    app, auth_headers, bind_runner
):
    """The §3 spin of `openspec/explorations/2026-08-20-the-loop-under-dependencies.md`,
    reproduced 2026-08-20 and then fixed.

    Before the fix this asserted `[True, True, True]`, three `JobRun`s at `completed`, and an
    agent spawned on every tick having nothing to do -- `completed` is in neither
    `CLAIMABLE_LOOP_TASK_STATUSES` nor `TERMINAL_FOR_BINDING`, so the queue was invisible to the
    claim and counted as open by the stop condition at once. Same "spinning on none" failure the
    2026-08-19 fix was written against; that one added `assigned` to the claimable set and left
    this route open.

    Now: each firing is refused, records a `skipped` `JobRun` naming what it is waiting on, and
    spawns nothing. The job stays enabled and stays scheduled -- stalled is not finished, and
    approving one of these tasks must be enough to bring the loop back on the next tick, which is
    the last block below.
    """
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-spin": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-spin", cli="claude")

    # Exactly two reads, for the ONE firing that should reach a spawn -- the recovery at the end.
    # If a stalled firing ever spawns again, this list runs dry and the test says so.
    fake_session = MagicMock()
    fake_session.pid = 4747
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-spin-recover"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="spin", agent="loop-agent-spin")
        loop = await _make_loop(
            db,
            job_id=job.id,
            purpose="worked but never reviewed",
            stop_when_queue_empties=True,
        )
        for n in (1, 2):
            db.add(
                Task(
                    id=f"task-spin-{n}",
                    project_id="proj-test",
                    title=f"done, awaiting a reviewer who never comes ({n})",
                    status="completed",
                    assignee="loop-agent-spin",
                    loop_id=loop.id,
                    created_at=now - timedelta(minutes=10 - n),
                    updated=now - timedelta(minutes=10 - n),
                )
            )
        await db.commit()

    firings = []
    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            scheduler = JobScheduler()
            for _ in range(3):
                async with async_session_factory() as db:
                    fresh_job = await db.get(AIJob, job.id)
                    firings.append(
                        await scheduler._fire_job_internal(
                            fresh_job, trigger="scheduled", session=db
                        )
                    )
                for task in list(agent_trigger._background_runs):
                    await task

    # Every stalled firing is refused.
    assert firings == [False, False, False]

    async with async_session_factory() as db:
        # Refused, but NOT stopped: still enabled, so the cron keeps ticking.
        refreshed_job = await db.get(AIJob, job.id)
        assert refreshed_job.enabled is True

        refreshed_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        assert refreshed_loop.stop_reason is None
        assert refreshed_loop.stopped_at is None
        assert refreshed_loop.ending_state is None

        # Both tasks left exactly as they were -- nothing was claimed to be worked on.
        tasks = (
            (await db.execute(select(Task).where(Task.loop_id == refreshed_loop.id)))
            .scalars()
            .all()
        )
        assert [t.status for t in tasks] == ["completed", "completed"]

        # No agent was spawned. **One** skipped JobRun counting all three refusals — this asserted
        # three rows until `loop-notices-and-reacts` group 2, which made a continuing stall count in
        # place rather than append (design D6). The fact under test is unchanged: three firings, no
        # agent, and a record naming what is being waited on. What changed is that the record does
        # not multiply, because `JobRun` feeds the last-ten-runs view and a stalled loop was burying
        # the firings that did work.
        job_runs = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
        assert len(job_runs) == 1
        assert job_runs[0].tick_count == 3
        assert {r.status for r in job_runs} == {"skipped"}
        assert all("stalled" in r.error_summary for r in job_runs)
        assert all("2 completed" in r.error_summary for r in job_runs)

        conversations = (
            (await db.execute(select(Conversation).where(Conversation.agent == job.agent)))
            .scalars()
            .all()
        )
        assert conversations == []

        runs = (await db.execute(select(Run).where(Run.agent == "loop-agent-spin"))).scalars().all()
        assert runs == []

    # And it recovers by itself: the moment the queue holds something claimable, the very next
    # tick works it. This is what "skip" buys over "stop", which would have disabled the job.
    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-spin-unblocked",
                project_id="proj-test",
                title="new work, claimable",
                status="pending",
                loop_id=f"loop-{job.id}",
                created_at=now,
                updated=now,
            )
        )
        await db.commit()

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            async with async_session_factory() as db:
                fresh_job = await db.get(AIJob, job.id)
                recovered = await scheduler._fire_job_internal(
                    fresh_job, trigger="scheduled", session=db
                )
            for task in list(agent_trigger._background_runs):
                await task

    assert recovered is True

    async with async_session_factory() as db:
        unblocked = await db.get(Task, "task-spin-unblocked")
        # `every-run-knows-its-task` D1/D2: the recovering run binds via `task_id` and advances
        # the claimed task past `assigned` to `in_progress`.
        assert unblocked.status == "in_progress"
        assert unblocked.assignee == "loop-agent-spin"


@pytest.mark.asyncio
async def test_loop_whose_only_task_is_blocked_on_an_unanswered_question_skips_instead_of_spinning(
    app, auth_headers, bind_runner
):
    """§4 of `openspec/explorations/2026-08-21-which-band-blocked-belongs-to.md`.

    The same spin as the test above, reached by the one route that fix left open. That fix keys on
    *the claim returned nothing* -- `_do_fire_job` consults `_loop_stall_reason` only when
    `claimed_task is None`. `blocked` was in `CLAIMABLE_LOOP_TASK_STATUSES`, so the claim returned
    something and the stall check was never reached.

    A task sitting in `blocked` provably has an **unanswered** question: `park_task_for_question` is
    the only thing that enters the status, and `release_block_for_question` moves it straight to
    `in_progress` the moment that question is answered or declined. So firing an agent at it cannot
    make progress -- the answer is what makes progress -- which is the same "someone else's turn" the
    gap already holds `completed` and `under_review` for.

    Before `blocked` left the claimable set this asserted `[True, True, True]`, three spawned runs,
    and a briefing that never mentioned the block: `_compose_loop_briefing` emits title, description
    and acceptance criteria only, so the agent received a blocked task rendered exactly like a fresh
    one. The last block is the recovery, and it is why stalling costs nothing.
    """
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-blocked": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-blocked", cli="claude")

    # Two reads, for the ONE firing that should reach a spawn -- the recovery at the end. If a
    # stalled firing ever spawns again, this runs dry and the test says so rather than passing.
    fake_session = MagicMock()
    fake_session.pid = 4848
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-blocked-recover"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="blocked", agent="loop-agent-blocked")
        loop = await _make_loop(
            db,
            job_id=job.id,
            purpose="waiting on an answer nobody has given",
            stop_when_queue_empties=True,
        )
        db.add(
            Task(
                id="task-blocked-1",
                project_id="proj-test",
                title="started, then hit something only a person can supply",
                status="blocked",
                blocked_reason="Which database should the migration target?",
                assignee="loop-agent-blocked",
                loop_id=loop.id,
                created_at=now - timedelta(minutes=9),
                updated=now - timedelta(minutes=9),
            )
        )
        db.add(
            Question(
                id="q-blocked-1",
                project_id="proj-test",
                from_agent="loop-agent-blocked",
                question="Which database should the migration target?",
                blocking=True,
                answered=False,
                blocked_task_id="task-blocked-1",
            )
        )
        await db.commit()

    firings = []
    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            scheduler = JobScheduler()
            for _ in range(3):
                async with async_session_factory() as db:
                    fresh_job = await db.get(AIJob, job.id)
                    firings.append(
                        await scheduler._fire_job_internal(
                            fresh_job, trigger="scheduled", session=db
                        )
                    )
                for task in list(agent_trigger._background_runs):
                    await task

    assert firings == [False, False, False]

    async with async_session_factory() as db:
        # Stalled, not finished: the answer may still arrive, so the cron must keep ticking.
        refreshed_job = await db.get(AIJob, job.id)
        assert refreshed_job.enabled is True

        refreshed_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        assert refreshed_loop.stop_reason is None
        assert refreshed_loop.stopped_at is None

        # The task is left exactly as it was, still waiting, still saying what for.
        parked = await db.get(Task, "task-blocked-1")
        assert parked.status == "blocked"
        assert parked.blocked_reason == "Which database should the migration target?"

        # Nothing spawned. One skipped JobRun counting all three refusals (design D6 — see the
        # note on the completed-and-unapproved test above for why this stopped being three rows).
        job_runs = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
        assert len(job_runs) == 1
        assert job_runs[0].tick_count == 3
        assert {r.status for r in job_runs} == {"skipped"}
        assert all("stalled" in r.error_summary for r in job_runs)
        assert all("1 blocked" in r.error_summary for r in job_runs)

        runs = (
            (await db.execute(select(Run).where(Run.agent == "loop-agent-blocked"))).scalars().all()
        )
        assert runs == []

    # The answer arriving is the recovery, and it needs no help from the loop: the release moves the
    # task to `in_progress`, which is claimable, so the very next tick works it.
    async with async_session_factory() as db:
        question = await db.get(Question, "q-blocked-1")
        question.answered = True
        question.answer = "The trial one, on 8010."
        released = await release_block_for_question(db, question)
        assert released is not None
        assert released.status == "in_progress"
        assert released.blocked_reason is None
        await db.commit()

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            async with async_session_factory() as db:
                fresh_job = await db.get(AIJob, job.id)
                recovered = await scheduler._fire_job_internal(
                    fresh_job, trigger="scheduled", session=db
                )
            for task in list(agent_trigger._background_runs):
                await task

    assert recovered is True


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
        # Design D13, task A4.3: the background run above actually completed.
        assert run.status == "completed"
        tasks = (
            (await db.execute(select(Task).where(Task.loop_id == f"loop-{job.id}"))).scalars().all()
        )
        assert tasks == []


@pytest.mark.asyncio
async def test_loop_fire_whose_spawn_fails_leaves_the_job_run_failed_not_stuck_in_progress(
    app, auth_headers, bind_runner
):
    """Design D13, task A4.3: a firing that queues successfully becomes "in_progress"
    (`scheduler.py::_do_fire_job`), and a spawn that then fails before the agent ever ran must
    still resolve it to a terminal status, not leave it stuck — `agent_trigger.py`'s early
    `FileNotFoundError` handler is the one of five `finalize_job_run_for_conversation` call
    sites most likely to have been missed, since it fires before either of the two "success"
    call sites (agent_trigger.py's two `run.status = final_status` finalize blocks) ever run."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-spawn-fail": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-spawn-fail", cli="claude")

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="spawn-fail", agent="loop-agent-spawn-fail")
        await _make_loop(db, job_id=job.id, purpose="spawn never starts")

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn",
        MagicMock(side_effect=FileNotFoundError("claude was not found in PATH")),
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

    assert success is True  # the firing itself queued fine; the spawn is what failed

    async with async_session_factory() as db:
        run = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalar_one()
        assert run.status == "failed"


@pytest.mark.asyncio
async def test_finalize_job_run_for_conversation_touches_only_the_matching_in_progress_row(app):
    """Design D13, task A4.3, unit-level: `JobRun` and `Run` share no foreign key —
    `conversation_id` is the only correlation `finalize_job_run_for_conversation` has to work
    with — so this proves the query shape directly against hand-built rows rather than only
    through a full spawn, where a wrong query (matching on job/project instead of conversation)
    could still pass by accident if only one loop is ever in flight at a time."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="finalize-unit", agent="agent-finalize-unit")
        other_conversation_in_progress = JobRun(
            id="run-other-in-progress",
            job_id=job.id,
            project_id="proj-test",
            status="in_progress",
            conversation_id="conv-other",
        )
        target = JobRun(
            id="run-target",
            job_id=job.id,
            project_id="proj-test",
            status="in_progress",
            conversation_id="conv-target",
        )
        already_terminal_same_conversation = JobRun(
            id="run-already-done",
            job_id=job.id,
            project_id="proj-test",
            status="completed",
            conversation_id="conv-target",
        )
        db.add_all([other_conversation_in_progress, target, already_terminal_same_conversation])
        await db.commit()

        await finalize_job_run_for_conversation(db, "conv-target", "failed")
        # No matching row (unknown conversation, or None — most `Run`s are not job firings at
        # all) is a no-op, not an error.
        await finalize_job_run_for_conversation(db, "conv-does-not-exist", "failed")
        await finalize_job_run_for_conversation(db, None, "failed")
        await db.commit()

        assert (await db.get(JobRun, "run-other-in-progress")).status == "in_progress"
        assert (await db.get(JobRun, "run-target")).status == "failed"
        assert (await db.get(JobRun, "run-already-done")).status == "completed"


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
async def test_loop_edit_staged_mid_firing_leaves_that_firings_briefing_untouched_and_applies_next(
    app, auth_headers, bind_runner
):
    """Design D11 (tasks A2.2/A2.3): an edit staged while a firing is already under way must not
    reach that firing's own briefing — the firing already in flight keeps the definition it was
    briefed with — and must be applied, in full, at the very next firing, before that firing's own
    briefing is composed."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-pending-edit": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-pending-edit", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 5151
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-pending-1"}\n',
        "",
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-pending-2"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="pending-edit", agent="loop-agent-pending-edit")
        loop = await _make_loop(db, job_id=job.id, purpose="the original purpose")
        job_id = job.id
        loop_id = loop.id

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            scheduler = JobScheduler()

            # Firing 1: briefed with the original purpose.
            async with async_session_factory() as db:
                fresh_job = await db.get(AIJob, job_id)
                first_success = await scheduler._fire_job_internal(
                    fresh_job, trigger="scheduled", session=db
                )
            for task in list(agent_trigger._background_runs):
                await task
            assert first_success is True

            # An edit lands while firing 1's agent turn is still the most recent thing that
            # happened — the scenario A2.3 exists to protect. `_fire_job_internal` has already
            # returned by this point in the test, but nothing about the edit path knows that; it
            # behaves identically whether the prior firing's turn is still running or already
            # finished, because nothing re-reads the loop mid-turn (see
            # `_stage_pending_loop_edit`'s own comment).
            staged = await app.patch(
                f"/api/v1/projects/proj-test/jobs/{job_id}",
                json={"purpose": "the revised purpose"},
                headers=auth_headers,
            )
            assert staged.status_code == 200
            assert staged.json()["loop"]["purpose"] == "the original purpose"
            assert staged.json()["loop"]["pending_edit"]["purpose"] == "the revised purpose"

            # Firing 2: applies the staged edit before composing its own briefing.
            async with async_session_factory() as db:
                fresh_job = await db.get(AIJob, job_id)
                second_success = await scheduler._fire_job_internal(
                    fresh_job, trigger="scheduled", session=db
                )
            for task in list(agent_trigger._background_runs):
                await task
            assert second_success is True

    async with async_session_factory() as db:
        entries = (
            (
                await db.execute(
                    select(InboundQueueEntry)
                    .where(InboundQueueEntry.agent == "loop-agent-pending-edit")
                    .order_by(InboundQueueEntry.sequence)
                )
            )
            .scalars()
            .all()
        )
        loop = await db.get(Loop, loop_id)
        applied_events = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "loop_edit_applied")))
            .scalars()
            .all()
        )

    assert len(entries) == 2
    assert "Purpose: the original purpose" in entries[0].content
    assert "the revised purpose" not in entries[0].content
    assert "Purpose: the revised purpose" in entries[1].content
    assert "the original purpose" not in entries[1].content

    # The live field is now the applied value, and nothing is pending any more.
    assert loop.purpose == "the revised purpose"
    assert loop.pending_purpose is None
    assert loop.pending_edit_at is None

    assert len(applied_events) == 1
    assert applied_events[0].data["id"] == loop_id
    assert applied_events[0].data["actor"] == "operator"
    assert applied_events[0].data["changes"]["purpose"] == {
        "from": "the original purpose",
        "to": "the revised purpose",
    }

    detail_resp = await app.get(f"/api/v1/projects/proj-test/loops/{loop_id}", headers=auth_headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["purpose"] == "the revised purpose"
    assert detail_resp.json()["pending_edit"] is None


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


@pytest.mark.asyncio
async def test_run_count_and_last_run_describe_firings_not_considerations(
    app, auth_headers, bind_runner
):
    """Finding F11: `AIJob.run_count`/`last_run` used to count every tick, skips included.

    Measured on the 2026-08-23 stress drive: a loop card read "9 runs · last run 18:01" for a
    loop that had spawned an agent **4** times, with `last_run` pointing at a firing that did
    nothing. Both fields were stamped at the top of `_do_fire_job`, above every skip branch, so
    they described "the scheduler considered this job".

    The shape below is the measured one in miniature — three stalled ticks, then one real firing
    once the queue holds claimable work. `next_run` is asserted separately and deliberately: the
    schedule advances on a skip too, because a `next_run` left in the past would be its own lie.
    """
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"loop-agent-count": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("loop-agent-count", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 4848
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-count"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="count", agent="loop-agent-count")
        loop = await _make_loop(
            db,
            job_id=job.id,
            purpose="counted honestly",
            stop_when_queue_empties=True,
        )
        db.add(
            Task(
                id="task-count-stalled",
                project_id="proj-test",
                title="done, awaiting review",
                status="completed",
                assignee="loop-agent-count",
                loop_id=loop.id,
                created_at=now - timedelta(minutes=5),
                updated=now - timedelta(minutes=5),
            )
        )
        await db.commit()

    scheduler = JobScheduler()
    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            for _ in range(3):
                async with async_session_factory() as db:
                    fresh_job = await db.get(AIJob, job.id)
                    assert (
                        await scheduler._fire_job_internal(
                            fresh_job, trigger="scheduled", session=db
                        )
                        is False
                    )

    async with async_session_factory() as db:
        stalled_job = await db.get(AIJob, job.id)
        # Three considerations, no firing.
        assert stalled_job.run_count == 0
        assert stalled_job.last_run is None
        # ...but the schedule itself did move on.
        assert stalled_job.next_run is not None
        # The skips are still recorded, in the place that was always honest about them — as one
        # row counting three since `loop-notices-and-reacts` group 2 (design D6). The point of this
        # test is that `run_count`/`last_run` describe firings rather than considerations, and that
        # is unaffected: three considerations, zero firings, and a record that says so.
        job_runs = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
        assert len(job_runs) == 1
        assert job_runs[0].tick_count == 3
        assert {r.status for r in job_runs} == {"skipped"}

    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-count-claimable",
                project_id="proj-test",
                title="real work",
                status="pending",
                loop_id=f"loop-{job.id}",
                created_at=now,
                updated=now,
            )
        )
        await db.commit()

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            async with async_session_factory() as db:
                fresh_job = await db.get(AIJob, job.id)
                assert (
                    await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)
                    is True
                )
            for task in list(agent_trigger._background_runs):
                await task

    async with async_session_factory() as db:
        fired_job = await db.get(AIJob, job.id)
        assert fired_job.run_count == 1
        assert fired_job.last_run is not None
        # The one stamped time belongs to the firing that did the work, not to the last skip.
        job_runs = (
            (
                await db.execute(
                    select(JobRun)
                    .where(JobRun.job_id == job.id, JobRun.status != "skipped")
                    .order_by(JobRun.fired_at)
                )
            )
            .scalars()
            .all()
        )
        assert len(job_runs) == 1
        assert fired_job.last_run == job_runs[0].fired_at


@pytest.mark.asyncio
async def test_a_stopped_loops_final_tick_does_not_count_as_a_run():
    """F11's other skip route: the branch that ends the loop must not bill it for a firing.

    `stop_at` elapsing disables the job from inside `_do_fire_job`. That tick reached no agent and
    queued no entry, so the count an operator reads afterwards is the count of work the loop
    actually did — here, none.
    """
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="count-stop", agent="loop-agent-count-stop")
        await _make_loop(
            db,
            job_id=job.id,
            purpose="ends before it works",
            stop_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        assert (
            await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db) is False
        )

    async with async_session_factory() as db:
        stopped_job = await db.get(AIJob, job.id)
        assert stopped_job.enabled is False
        assert stopped_job.run_count == 0
        assert stopped_job.last_run is None
        run = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalar_one()
        assert run.status == "skipped"


# ---------------------------------------------------------------------------
# Finding F1 — the day-field ambiguity detector itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cron",
    [
        "0 0 15 * 5",  # the measured case: stored as 2026-08-28, fires 2027-05-15
        "0 0 1 * 1",
        "0 0 15 * MON",  # aliases count
        "0 0 */2 * 1",  # a step is a restriction
        "0 0 1,15 * 1-3",  # lists and ranges too
    ],
)
def test_cron_day_ambiguity_is_named_for_expressions_restricting_both_day_fields(cron):
    reason = cron_day_ambiguity_reason(cron)
    assert reason is not None
    assert "day-of-month" in reason and "day-of-week" in reason
    assert "two jobs" in reason


@pytest.mark.parametrize(
    "cron",
    [
        "0 9 * * *",
        "*/5 * * * *",
        "0 9 * * 1-5",
        "0 9 15 * *",
        "0 0 * * 0",
        "0 0 * * 7",  # 7 is Sunday, and one day is still a restriction — but of one field only
        "0 9 15 * 0-6",  # a day-of-week naming all seven days restricts nothing
        "0 9 15 * 1-7",  # ...and neither does 1-7, where 7 folds back onto 0
        "0 9 1-31 * 5",  # a day-of-month naming every day restricts nothing either
    ],
)
def test_cron_day_ambiguity_is_silent_for_everything_else(cron):
    assert cron_day_ambiguity_reason(cron) is None


@pytest.mark.parametrize(
    "cron",
    [
        "not a cron",
        "0 0 L * 5",  # `L` is outside this grammar
        "0 0 15 * 5#2",  # ...so is `#`
        "0 0 15 * 5 0",  # six fields is not our grammar; `add_job` refuses it separately
        "0 0 22-2 * 5",  # a wrapping range is read differently by different implementations
    ],
)
def test_cron_day_ambiguity_declines_to_judge_what_it_cannot_read(cron):
    """`None` here means *undecided*, not *fine*.

    croniter and APScheduler stay the authorities on whether an expression is valid at all; this
    detector only ever adds a refusal, and a detector that guessed at an extension it does not
    implement would reject schedules that work.
    """
    assert cron_day_ambiguity_reason(cron) is None


def test_the_two_cron_readers_this_repository_holds_really_do_disagree():
    """The premise of F1, asserted rather than assumed.

    If a future dependency bump makes croniter and APScheduler agree on the day pair, this test
    fails and the refusal above becomes removable. Until then it is the evidence that the two
    numeric answers the product used to render were genuinely different answers, not rounding.
    """
    croniter = pytest.importorskip("croniter").croniter
    cron_trigger = pytest.importorskip("apscheduler.triggers.cron").CronTrigger

    start = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    cron = "0 0 15 * 5"

    or_reading = croniter(cron, start).get_next(datetime)
    parts = cron.split()
    and_reading = cron_trigger(
        minute=parts[0],
        hour=parts[1],
        day=parts[2],
        month=parts[3],
        day_of_week=parts[4],
        timezone="UTC",
    ).get_next_fire_time(None, start)

    assert or_reading.date() != and_reading.date()
    # croniter fires on the next Friday *or* the 15th, whichever comes first; APScheduler waits
    # for a 15th that is also a Friday. Months apart, from the same five fields.
    assert (and_reading - or_reading).days > 200


# ---------------------------------------------------------------------------
# `every-run-knows-its-task` group 2 (D1/D2, F66) — a flow work firing binds the run it starts
#
# Before this group both of the scheduler's staging paths set `review_task_id` for a review
# selection and nothing at all for an ordinary one, so `run.task_id` was NULL on every flow work
# run the product ever started (F5's measured "10 across 202 runs" — the ~10% is delegation and
# operator triggers, which already set it). `binding_from_entries` reads `task_id` (or
# `review_task_id`) off the *queue entry*, not off the selection the ladder made, so a firing that
# claims a task for ordinary work must say so on the entry it stages, or nothing downstream ever
# learns it.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_primary_firing_that_claims_work_stages_task_id_not_review_task_id(
    app, auth_headers, bind_runner
):
    """2.1 — the primary staging path (`scheduler.py` ~2302)."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"flow-stages-work": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("flow-stages-work", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 6001
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-stages-1"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="stages-work", agent="flow-stages-work")
        loop = await _make_loop(db, job_id=job.id, purpose="stage the work")
        db.add(
            Task(
                id="task-flow-stages",
                project_id="proj-test",
                title="do the thing",
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
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "flow-stages-work")
                )
            )
            .scalars()
            .first()
        )
        assert entry is not None
        assert entry.task_id == "task-flow-stages"
        assert entry.review_task_id is None


@pytest.mark.asyncio
async def test_a_firing_that_staffs_a_review_stages_review_task_id_not_task_id(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """2.2 — D2's separation pinned in both directions: a review selection carries
    `review_task_id`, never `task_id`, even though the same firing now writes both fields."""
    from .test_agent_trigger import _init_repo
    from .test_flow_fires_a_review_turn import _attribute_completion, _flow, _queued_entry_for
    from .test_review_turn import _author_commit, _reviewable_task, _roster

    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    await _roster(
        app, auth_headers, bind_runner, "flow-stages-review-author", "flow-stages-review-critic"
    )
    await _reviewable_task(commit=sha)

    async with async_session_factory() as db:
        await _attribute_completion(db, "task-1", "flow-stages-review-author")
        job, _loop = await _flow(
            db, suffix="stages-review", agent="flow-stages-review-author", task_id="task-1"
        )

    scheduler = JobScheduler()
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        async with async_session_factory() as db:
            fresh_job = await db.get(AIJob, job.id)
            await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    entry = await _queued_entry_for("flow-stages-review-critic")
    assert entry is not None
    assert entry.review_task_id == "task-1"
    assert entry.task_id is None


@pytest.mark.asyncio
async def test_a_flow_work_run_binds_and_starts_its_claimed_task(app, auth_headers, bind_runner):
    """2.3 — the run delivering the work entry is bound to that task, and the task reaches
    `in_progress` without the agent moving it (the runtime's own move, `bind_run_to_task`)."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"flow-binds-work": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("flow-binds-work", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 6002
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-binds-1"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="binds-work", agent="flow-binds-work")
        loop = await _make_loop(db, job_id=job.id, purpose="bind the work")
        db.add(
            Task(
                id="task-flow-binds",
                project_id="proj-test",
                title="do the thing",
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
                await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)
            for task in list(agent_trigger._background_runs):
                await task

    async with async_session_factory() as db:
        run = (
            (await db.execute(select(Run).where(Run.agent == "flow-binds-work"))).scalars().first()
        )
        assert run is not None
        assert run.task_id == "task-flow-binds"

        task = await db.get(Task, "task-flow-binds")
        assert task.status == "in_progress"


@pytest.mark.asyncio
async def test_a_firing_that_claims_no_task_starts_an_unbound_run_with_no_divergence(
    app, auth_headers, bind_runner
):
    """2.4 — a plain job with no loop makes no selection, so its run starts unbound and records
    no divergence when it ends: there was no task to have neglected."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"flow-unbound-run": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("flow-unbound-run", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 6003
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-unbound-1"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    async with async_session_factory() as db:
        await _make_job(db, suffix="unbound-run", agent="flow-unbound-run")

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            scheduler = JobScheduler()
            async with async_session_factory() as db:
                fresh_job = await db.get(AIJob, "job-sched-unbound-run")
                await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)
            for task in list(agent_trigger._background_runs):
                await task

    async with async_session_factory() as db:
        run = (
            (await db.execute(select(Run).where(Run.agent == "flow-unbound-run"))).scalars().first()
        )
        assert run is not None
        assert run.task_id is None

        divergences = (
            (await db.execute(select(RunDivergence).where(RunDivergence.run_id == run.id)))
            .scalars()
            .all()
        )
        assert divergences == []


@pytest.mark.asyncio
async def test_a_flow_work_run_that_moves_nothing_is_divergent(app, auth_headers, bind_runner):
    """2.5 — the behaviour that has never once fired in production: before this group,
    `run.task_id` was NULL on every flow work run, so this boundary check never had anything to
    check. With `task_id` staged, a run that ends without moving its task IS divergent."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"flow-neglects-work": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("flow-neglects-work", cli="claude")

    fake_session = MagicMock()
    fake_session.pid = 6004
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-neglects-1"}\n',
        "",
    ]
    fake_session.wait.return_value = 0

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="neglects-work", agent="flow-neglects-work")
        loop = await _make_loop(db, job_id=job.id, purpose="neglect the work")
        db.add(
            Task(
                id="task-flow-neglects",
                project_id="proj-test",
                title="do the thing",
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
                await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)
            for task in list(agent_trigger._background_runs):
                await task

    async with async_session_factory() as db:
        run = (
            (await db.execute(select(Run).where(Run.agent == "flow-neglects-work")))
            .scalars()
            .first()
        )
        assert run is not None

        task = await db.get(Task, "task-flow-neglects")
        # The runtime's own move to `in_progress` is not an actor transition (design D5 in
        # `run_task_binding.run_advanced_its_task`), so an agent that never records anything
        # itself has genuinely moved nothing.
        assert task.status == "in_progress"

        divergences = (
            (await db.execute(select(RunDivergence).where(RunDivergence.run_id == run.id)))
            .scalars()
            .all()
        )
        assert len(divergences) == 1
        assert divergences[0].task_id == "task-flow-neglects"
