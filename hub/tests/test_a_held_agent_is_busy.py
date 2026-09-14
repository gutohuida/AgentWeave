"""`a-spent-allowance-holds-the-queue` group 3 — a held agent is busy, to every reader that asks.

Finding F355. After the provider refuses an agent's turn because its usage allowance is spent,
`schedule_agent` holds that agent's autonomous input until the reset (design D4, tested in
`test_a_refused_turn_holds_the_queue.py`). Every other place that decides whether to give an agent
work has to read the same fact, or it queues input that only waits:

* a loop's busy guard (D6, task 3.4), and a flow's own walk (3.4b) and free list (3.4c);
* rung 3's sentence, which must name the hold when a hold is why nobody was free (3.4d);
* the board's stalled answer, which must be the guard's when the guard refuses (3.4e);
* a plain job, which keeps one queued copy rather than one per tick (D7, tasks 3.5 and 3.6);
* the start-up passes: the wake is re-armed (D5, 3.3) and a held firing is not failed (D10, 3.7).

The hold is recorded here as `_execute_run` records it, a `TurnUsage` row carrying the refused
reading, without a turn to make it.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from hub import provider_allowance, task_attribution
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    Conversation,
    InboundQueueEntry,
    JobRun,
    Loop,
    Run,
    Task,
    TaskDependency,
    TurnUsage,
)
from hub.inbound_queue import new_entry
from hub.provider_allowance import hold_busy_reason, hold_coalesce_reason, provider_hold
from hub.run_reconciliation import reconcile_stale_job_runs
from hub.scheduler import (
    DECISION_IN_FLIGHT,
    DECISION_STALLED,
    JobScheduler,
    _agents_that_are_free,
    decide_firing,
    resolve_reviewer,
)
from hub.utils import short_id

from .test_flow_width import _decide, _flow, _pairs, _task
from .test_loop_busy_guard import _make_loop_job
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"


def _reading(resets_at):
    """The measured reading (the change's tasks.md, head)."""
    epoch = resets_at.timestamp()
    return {
        "status": "rejected",
        "resetsAt": epoch,
        "rateLimitType": "five_hour",
        "overageStatus": "rejected",
        "overageDisabledReason": "out_of_credits",
        "isUsingOverage": False,
        "unifiedWindows": {"five_hour": {"utilization": 1.02, "resetsAt": epoch}},
    }


async def _hold(agent, *, observed_ago=timedelta(minutes=1), resets_in=timedelta(hours=1)):
    """Record a refusal for *agent*. A negative *resets_in* is a reset already past."""
    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        run_id = f"run-{short_id()}"
        db.add(Run(id=run_id, project_id=PROJECT, agent=agent, status="failed"))
        await db.flush()
        db.add(
            TurnUsage(
                id=f"usage-{short_id()}",
                run_id=run_id,
                project_id=PROJECT,
                agent=agent,
                status="unavailable",
                allowance=_reading(now + resets_in),
                observed_at=now - observed_ago,
            )
        )
        await db.commit()


async def _uninformative_row(agent):
    """What crash reconciliation writes: no sample, so it says nothing about the provider."""
    async with async_session_factory() as db:
        run_id = f"run-{short_id()}"
        db.add(Run(id=run_id, project_id=PROJECT, agent=agent, status="interrupted"))
        await db.flush()
        db.add(
            TurnUsage(
                id=f"usage-{short_id()}",
                run_id=run_id,
                project_id=PROJECT,
                agent=agent,
                status="unavailable",
                observed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


async def _queue(agent, conversation_id, *, origin_type="agent", task_id=None, content="input"):
    async with async_session_factory() as db:
        if await db.get(Conversation, conversation_id) is None:
            db.add(
                Conversation(id=conversation_id, project_id=PROJECT, agent=agent, lifecycle="open")
            )
        entry = new_entry(
            project_id=PROJECT,
            agent=agent,
            origin_type=origin_type,
            origin_agent="peer" if origin_type == "agent" else None,
            content=content,
            hop_depth=0,
            conversation_id=conversation_id,
            task_id=task_id,
        )
        db.add(entry)
        await db.commit()
        return entry.id


async def _entries_for(agent):
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(InboundQueueEntry)
                    .where(InboundQueueEntry.agent == agent)
                    .order_by(InboundQueueEntry.sequence)
                )
            )
            .scalars()
            .all()
        )


async def _job_runs(job_id):
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(JobRun).where(JobRun.job_id == job_id).order_by(JobRun.fired_at)
                )
            )
            .scalars()
            .all()
        )


async def _fire(job_id, times=1):
    outcomes = []
    for _ in range(times):
        async with async_session_factory() as db:
            job = await db.get(AIJob, job_id)
            outcomes.append(await JobScheduler()._fire_job_internal(job, "scheduled", session=db))
    return outcomes


async def _the_hold(agent):
    async with async_session_factory() as db:
        hold = await provider_hold(db, PROJECT, agent)
    assert hold is not None
    return hold


def _clock(hold):
    return hold.hold_until.strftime("%H:%M") + " UTC"


def _end_every_hold(monkeypatch):
    monkeypatch.setattr(
        provider_allowance, "_utcnow", lambda: datetime.now(timezone.utc) + timedelta(hours=2)
    )


# ---------------------------------------------------------------------------
# 3.4 — a loop's busy guard answers "held" (design D6). No other agent in the project.
# ---------------------------------------------------------------------------


async def test_a_loop_firing_while_its_agent_is_held_records_nothing(app):
    """The existing *records nothing* shape: no `JobRun`, no queue entry, the task untouched."""
    async with async_session_factory() as db:
        job, _loop, task = await _make_loop_job(db, suffix="held", agent="held-loop")
    await _hold("held-loop")

    outcomes = await _fire(job.id, times=3)

    assert await _entries_for("held-loop") == []
    assert await _job_runs(job.id) == []
    assert outcomes == [False] * 3
    async with async_session_factory() as db:
        fresh = await db.get(Task, task.id)
    assert (fresh.status, fresh.assignee) == ("pending", None)


async def test_the_guard_answers_with_the_holds_short_form(app):
    from hub.scheduler import _loop_agent_busy_reason

    await _hold("held-guard")
    hold = await _the_hold("held-guard")
    async with async_session_factory() as db:
        reason = await _loop_agent_busy_reason(db, PROJECT, "held-guard")
    assert reason == hold_busy_reason("held-guard", hold)
    assert _clock(hold) in reason


async def test_after_the_hold_the_loop_firing_proceeds(app, monkeypatch):
    async with async_session_factory() as db:
        job, _loop, task = await _make_loop_job(db, suffix="after-hold", agent="held-after")
    await _hold("held-after")
    await _fire(job.id)
    _end_every_hold(monkeypatch)

    await _fire(job.id)

    async with async_session_factory() as db:
        fresh = await db.get(Task, task.id)
    assert fresh.assignee == "held-after"
    assert fresh.status != "pending"


# ---------------------------------------------------------------------------
# 3.4b — the flow's own walk reads the hold (design D6). A second, free agent `other` is what
# lets these firings past the busy guard; without it they could not tell 3.4 from 3.4b.
# ---------------------------------------------------------------------------

DEV = "held-dev"
OTHER = "held-other"


async def _held_flow(app, auth_headers, bind_runner, *, suffix):
    await _roster(app, auth_headers, bind_runner, DEV, OTHER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix=suffix, agent=DEV)
    await _hold(DEV)
    return job, loop


async def test_a_held_assignee_with_its_briefing_queued_is_not_briefed_again(
    app, auth_headers, bind_runner
):
    job, loop = await _held_flow(app, auth_headers, bind_runner, suffix="queued")
    async with async_session_factory() as db:
        task = await _task(db, loop, "queued", status="assigned", assignee=DEV)
    await _queue(DEV, "conv-held-briefing", origin_type="job", task_id=task.id)

    await _fire(job.id, times=3)

    assert len(await _entries_for(DEV)) == 1
    decision = await _decide(job.id, loop.id, agent=DEV)
    assert decision.kind == DECISION_IN_FLIGHT
    staffing = task_attribution.staffing_from_decision(decision)
    assert staffing.agent_for(task.id) == DEV


async def test_a_held_assignee_with_nothing_queued_for_its_task_is_briefed_once(
    app, auth_headers, bind_runner
):
    """(Round 3.) Its queued input is a peer message, so nobody has briefed it on its task. In
    flight on the assignment alone would breach `agent-loops`' *actually working* requirement."""
    job, loop = await _held_flow(app, auth_headers, bind_runner, suffix="unbriefed")
    async with async_session_factory() as db:
        task = await _task(db, loop, "unbriefed", status="assigned", assignee=DEV)
    await _queue(DEV, "conv-held-peer", content="a peer's note")

    await _fire(job.id)
    briefings = [entry for entry in await _entries_for(DEV) if entry.task_id == task.id]
    assert len(briefings) == 1

    for _ in range(2):
        decision = await _decide(job.id, loop.id, agent=DEV)
        assert decision.kind == DECISION_IN_FLIGHT
        await _fire(job.id)
    assert [entry.task_id for entry in await _entries_for(DEV)] == [None, task.id]


async def test_a_held_job_agent_is_passed_over_for_an_unassigned_task(
    app, auth_headers, bind_runner
):
    job, loop = await _held_flow(app, auth_headers, bind_runner, suffix="default")
    async with async_session_factory() as db:
        task = await _task(db, loop, "default")

    decision = await _decide(job.id, loop.id, agent=DEV)

    assert _pairs(decision) == [(task.id, OTHER)]


async def test_another_agents_entry_naming_the_task_does_not_put_it_in_flight(
    app, auth_headers, bind_runner
):
    """(Round 4 — REV.) `on_it` maps a task to whichever agent has input naming it."""
    job, loop = await _held_flow(app, auth_headers, bind_runner, suffix="others")
    async with async_session_factory() as db:
        task = await _task(db, loop, "others", status="assigned", assignee=DEV)
    await _queue(OTHER, "conv-held-others", task_id=task.id, content="a peer to other")

    await _fire(job.id)

    assert [entry.task_id for entry in await _entries_for(DEV)] == [task.id]


# ---------------------------------------------------------------------------
# 3.4c — the free list's running half reads the hold (design D6)
# ---------------------------------------------------------------------------


async def test_a_held_agent_holding_no_task_is_not_free(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, DEV, OTHER)
    await _hold(DEV)

    async with async_session_factory() as db:
        free = await _agents_that_are_free(db, PROJECT)

    assert free == [OTHER]


async def test_with_every_agent_held_a_flow_firing_is_refused_and_records_nothing(
    app, auth_headers, bind_runner
):
    """(Round 3.) Each holds no task; otherwise the holdings half excludes them already."""
    await _roster(app, auth_headers, bind_runner, DEV, OTHER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="all-held", agent=DEV)
        await _task(db, loop, "all-held")
    await _hold(DEV)
    await _hold(OTHER)

    assert await _fire(job.id) == [False]

    assert await _job_runs(job.id) == []
    assert await _entries_for(DEV) == []
    assert await _entries_for(OTHER) == []


# ---------------------------------------------------------------------------
# 3.4d — rung 3 names the hold (design D6)
# ---------------------------------------------------------------------------

AUTHOR = "rung3-author"
REVIEWER = "rung3-reviewer"
_TODAY = (
    "could not staff this step: no agent is free to take it. Every agent on the roster is either "
    "running a turn, already holding active work, or is the one that completed this task and so "
    "may not review it."
)


async def _completed_task(db, task_id="task-rung3"):
    task = Task(id=task_id, project_id=PROJECT, title="finished", status="completed")
    db.add(task)
    await db.commit()
    return task


async def test_rung_three_names_the_usage_limit_when_a_hold_is_why_nobody_was_free(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    await _hold(REVIEWER)
    async with async_session_factory() as db:
        task = await _completed_task(db)
        choice = await resolve_reviewer(db, task, project_id=PROJECT, exclude={AUTHOR})

    assert choice.rung == "unstaffed"
    assert "waiting for its provider's usage limit to reset" in choice.reason
    assert "either running a turn, already holding active work, or " not in choice.reason


async def test_rung_three_reads_exactly_as_today_with_no_agent_held(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        task = await _completed_task(db)
        choice = await resolve_reviewer(db, task, project_id=PROJECT, exclude={AUTHOR})

    assert choice.reason == _TODAY


async def test_rung_three_with_the_hold_fits_a_job_runs_error_summary(
    app, auth_headers, bind_runner
):
    author, reviewer = "a" * 32, "r" * 32
    await _roster(app, auth_headers, bind_runner, author, reviewer)
    await _hold(reviewer)
    async with async_session_factory() as db:
        task = await _completed_task(db, task_id="t" * 64)
        choice = await resolve_reviewer(db, task, project_id=PROJECT, exclude={author})

    assert "usage limit" in choice.reason
    assert len(choice.reason) <= 500


# ---------------------------------------------------------------------------
# 3.4e — the board's stalled answer is the guard's when the guard refuses (Round 4 — REV)
# ---------------------------------------------------------------------------


async def _summary(job_id):
    from hub.api.v1.jobs import _batch_loop_summaries

    async with async_session_factory() as db:
        return (await _batch_loop_summaries(db, [job_id]))[job_id]


async def test_a_held_single_agent_loop_reads_held_not_no_claimable_task(app):
    async with async_session_factory() as db:
        job, _loop, _task_row = await _make_loop_job(db, suffix="board-held", agent="board-held")
    await _hold("board-held")
    await _queue("board-held", "conv-board-peer", content="a peer's note")
    hold = await _the_hold("board-held")

    summary = await _summary(job.id)

    assert _clock(hold) in summary.stall_reason
    assert "no claimable task" not in summary.stall_reason


async def test_a_loop_whose_agent_is_working_its_task_does_not_read_stalled(app):
    async with async_session_factory() as db:
        job, _loop, task = await _make_loop_job(db, suffix="board-work", agent="board-work")
        db.add(
            Run(
                id="run-board-work",
                project_id=PROJECT,
                agent="board-work",
                status="running",
                task_id=task.id,
            )
        )
        await db.commit()

    summary = await _summary(job.id)

    assert summary.stall_reason is None


async def test_with_no_hold_and_nothing_running_the_stalled_reason_is_unchanged(app):
    """Gated: its one task waits on another outside the loop, so the walk stalls on its own."""
    async with async_session_factory() as db:
        job, loop, task = await _make_loop_job(db, suffix="board-gated", agent="board-gated")
        db.add(Task(id="task-board-prereq", project_id=PROJECT, title="first", status="assigned"))
        await db.commit()
        db.add(
            TaskDependency(
                id="dep-board-gated",
                project_id=PROJECT,
                task_id=task.id,
                depends_on_task_id="task-board-prereq",
            )
        )
        await db.commit()
        fresh_loop = (await db.execute(select(Loop).where(Loop.id == loop.id))).scalar_one()
        decision = await decide_firing(db, fresh_loop, default_agent="board-gated")
    assert decision.kind == DECISION_STALLED

    summary = await _summary(job.id)

    assert summary.stall_reason == decision.stall_reason


# ---------------------------------------------------------------------------
# 3.5 / 3.6 — a plain job coalesces while its agent is held (design D7)
# ---------------------------------------------------------------------------


async def _plain_job(job_id, agent):
    async with async_session_factory() as db:
        db.add(
            AIJob(
                id=job_id,
                project_id=PROJECT,
                name=f"Plain {job_id}",
                agent=agent,
                message="standing instruction",
                cron="*/5 * * * *",
                session_mode="new",
                enabled=True,
            )
        )
        await db.commit()


async def test_a_held_plain_job_firing_leaves_its_job_run_in_progress(app):
    """3.6. Its entry will be delivered at the reset, so the firing has not failed."""
    await _plain_job("job-held-once", "plain-once")
    await _hold("plain-once")

    await _fire("job-held-once")

    [firing] = await _job_runs("job-held-once")
    assert firing.status == "in_progress"
    [entry] = await _entries_for("plain-once")
    assert (entry.state, entry.conversation_id) == ("queued", firing.conversation_id)


async def test_further_firings_during_a_hold_coalesce_into_one_counted_row(app):
    """The hold came from a refusal on another conversation, so the first firing queues. The
    first coalesced firing writes a row with `tick_count` 1, because the newest row is still the
    first firing's `in_progress` one; the next two count against it."""
    await _plain_job("job-held-many", "plain-many")
    await _hold("plain-many")

    await _fire("job-held-many", times=4)

    assert len(await _entries_for("plain-many")) == 1
    first, coalesced = await _job_runs("job-held-many")
    assert first.status == "in_progress"
    assert (coalesced.status, coalesced.tick_count) == ("skipped", 3)
    assert coalesced.error_summary == hold_coalesce_reason(
        "plain-many", await _the_hold("plain-many")
    )


async def test_when_the_jobs_own_firing_was_refused_the_very_next_firing_coalesces(app):
    """(Round 2.) The LoopEngine shape: the refused turn's entry is back on its conversation, and
    its firing is `in_progress` (D10)."""
    await _plain_job("job-held-own", "plain-own")
    async with async_session_factory() as db:
        db.add(
            JobRun(
                id="run-held-own",
                job_id="job-held-own",
                project_id=PROJECT,
                status="in_progress",
                conversation_id="conv-held-own",
            )
        )
        await db.commit()
    await _queue("plain-own", "conv-held-own", origin_type="job")
    await _hold("plain-own")

    await _fire("job-held-own")

    assert len(await _entries_for("plain-own")) == 1
    runs = await _job_runs("job-held-own")
    assert [(run.status, run.tick_count) for run in runs] == [("in_progress", 1), ("skipped", 1)]


async def test_with_no_hold_every_firing_queues(app):
    """Today's behaviour, pinned: a plain job is not busy-guarded."""
    await _plain_job("job-unheld", "plain-unheld")

    await _fire("job-unheld", times=4)

    assert len(await _entries_for("plain-unheld")) == 4


# ---------------------------------------------------------------------------
# 3.7 — a restart leaves a held firing in progress (design D10)
# ---------------------------------------------------------------------------


async def _stale_firing(run_id, agent, conversation_id):
    await _plain_job(f"job-{run_id}", agent)
    async with async_session_factory() as db:
        db.add(
            JobRun(
                id=run_id,
                job_id=f"job-{run_id}",
                project_id=PROJECT,
                status="in_progress",
                conversation_id=conversation_id,
            )
        )
        await db.commit()
    await _queue(agent, conversation_id, origin_type="job")


async def test_a_held_firing_survives_a_restart(app):
    await _stale_firing("run-restart-held", "restart-held", "conv-restart-held")
    await _hold("restart-held")

    await reconcile_stale_job_runs()

    async with async_session_factory() as db:
        assert (await db.get(JobRun, "run-restart-held")).status == "in_progress"


async def test_a_firing_whose_reset_passed_while_the_hub_was_down_survives_a_restart(app):
    """D5's start-up re-arm is about to deliver it, so the Hub's promise still stands."""
    await _stale_firing("run-restart-reset", "restart-reset", "conv-restart-reset")
    await _hold("restart-reset", observed_ago=timedelta(hours=2), resets_in=-timedelta(hours=1))

    await reconcile_stale_job_runs()

    async with async_session_factory() as db:
        assert (await db.get(JobRun, "run-restart-reset")).status == "in_progress"


async def test_a_firing_for_an_agent_with_no_runner_and_no_refusal_still_fails(app):
    """The docstring's decided case, pinned unchanged: a repair the Hub cannot promise."""
    await _stale_firing("run-restart-unbound", "restart-unbound", "conv-restart-unbound")

    await reconcile_stale_job_runs()

    async with async_session_factory() as db:
        assert (await db.get(JobRun, "run-restart-unbound")).status == "failed"


# ---------------------------------------------------------------------------
# 3.3 — the start-up re-arm (design D5)
# ---------------------------------------------------------------------------


@pytest.fixture
def armed(monkeypatch):
    recorder = MagicMock()
    monkeypatch.setattr(provider_allowance, "arm_allowance_wake", recorder)
    return recorder


@pytest.fixture
def redrained(monkeypatch):
    import hub.run_reconciliation as run_reconciliation

    recorder = AsyncMock()
    monkeypatch.setattr(run_reconciliation, "schedule_or_defer", recorder)
    return recorder


async def test_an_agent_with_queued_input_and_a_future_hold_is_armed(app, armed, redrained):
    await _queue("rearm-future", "conv-rearm-future")
    await _hold("rearm-future")
    hold = await _the_hold("rearm-future")

    await provider_allowance.arm_held_queues()

    armed.assert_called_once_with(PROJECT, "rearm-future", hold.hold_until)
    redrained.assert_not_called()


async def test_an_agent_whose_hold_passed_while_the_hub_was_down_is_redrained(
    app, armed, redrained
):
    await _queue("rearm-past", "conv-rearm-past")
    await _hold("rearm-past", observed_ago=timedelta(hours=2), resets_in=-timedelta(hours=1))

    await provider_allowance.arm_held_queues()

    armed.assert_not_called()
    redrained.assert_awaited_once_with({(PROJECT, "rearm-past")})


async def test_an_agent_with_no_queued_input_is_not_armed(app, armed, redrained):
    await _hold("rearm-idle")

    await provider_allowance.arm_held_queues()

    armed.assert_not_called()
    redrained.assert_not_called()


async def test_a_crash_reconciled_row_after_the_refusal_does_not_hide_it(app, armed, redrained):
    """(Round 2.) Crash reconciliation runs just before, in the same `lifespan`."""
    await _queue("rearm-crashed", "conv-rearm-crashed")
    await _hold("rearm-crashed")
    await _uninformative_row("rearm-crashed")

    await provider_allowance.arm_held_queues()

    armed.assert_called_once()
    assert armed.call_args.args[:2] == (PROJECT, "rearm-crashed")


async def test_the_hub_re_arms_held_queues_at_start_right_after_the_scheduler(monkeypatch):
    """After `init_scheduler`, which holds the wakes, and after both reconciliations."""
    import hub.main as main

    order = []
    for name in (
        "init_db",
        "reconcile_interrupted_runs",
        "reconcile_stale_job_runs",
        "init_scheduler",
        "arm_held_queues",
        "terminate_all_active_runs",
        "shutdown_scheduler",
        "_settle_background_runs",
    ):

        async def _record(*args, _name=name, **kwargs):
            order.append(_name)

        monkeypatch.setattr(main, name, _record)
    monkeypatch.setattr(main.instance_identity, "load_or_create", lambda: None)
    monkeypatch.setattr(main, "_ui_staleness_warning", lambda: None)
    monkeypatch.setattr(main, "engine", SimpleNamespace(dispose=AsyncMock()))

    async with main.lifespan(None):
        pass

    assert order[:5] == [
        "init_db",
        "reconcile_interrupted_runs",
        "reconcile_stale_job_runs",
        "init_scheduler",
        "arm_held_queues",
    ]
