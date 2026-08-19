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
from hub.scheduler import (
    _LOOP_BRIEFING_CHECKPOINT_CHARS,
    JobScheduler,
    _loop_stop_reason,
    finalize_job_run_for_conversation,
)


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
        assert older.status == "assigned"
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
        assert older.status == "assigned", "the OLDER pending task must be claimed"
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

    So: the older `assigned` task is resumed, its status is NOT re-entered, and the newer pending
    task is left alone.
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
        # Resumed, not re-entered: an already-active task keeps its status (design D3).
        assert resumed.status == "assigned"
        assert resumed.assignee == "loop-agent-resume-assigned"
        # And the pending one is NOT claimed alongside it -- that skipping is what stranded work.
        assert untouched.status == "pending"
        assert untouched.assignee is None


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
