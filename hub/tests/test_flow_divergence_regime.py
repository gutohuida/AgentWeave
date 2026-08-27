"""`every-run-knows-its-task`, groups 3-5 (D4-D7).

Group 3 answers one question with one function: was this run a live flow's own ordinary work
turn? Groups 4 and 5 are both readers of that answer, not two more places that ask it — that
drift is the defect `one-answer-to-what-is-happening` exists to end, and this change inherits the
same discipline for the run boundary.

Fixtures build **real** `AIJob`/`Loop`/`JobRun`/`Run` rows rather than a hand-built stand-in for
"this run belongs to a live flow" — task 3.4's own warning, after task 4.9 of
`one-answer-to-what-is-happening` first passed its mutation check for the wrong reason by testing
only a fixture shaped like the thing rather than the thing.
"""

import pytest
from sqlalchemy import select

from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, EventLog, InboundQueueEntry, JobRun, Loop, Run, RunDivergence, Task
from hub.run_divergence import evaluate_run_end, is_live_flow_work_turn
from hub.run_task_binding import POLICIES, POLICY_FLOW, bind_run_to_task
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator

from .test_agent_trigger import _init_repo
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures — real rows, not a shape that merely looks like a live flow
# ---------------------------------------------------------------------------


async def _flow_context(db, *, agent, suffix, stopped_at=None, archived_at=None):
    """A live (or not) flow: an `AIJob`, its `Loop`, and one `JobRun` firing into a fresh
    conversation. Returns the conversation id."""
    job = AIJob(
        id=f"job-{suffix}",
        project_id="proj-test",
        name="flow",
        agent=agent,
        message="work the queue",
        cron="*/5 * * * *",
        enabled=True,
    )
    db.add(job)
    await db.flush()
    db.add(
        Loop(
            id=f"loop-{suffix}",
            project_id="proj-test",
            job_id=job.id,
            purpose="flow",
            stopped_at=stopped_at,
            archived_at=archived_at,
        )
    )
    conversation = new_conversation(project_id="proj-test", agent=agent, origin="job")
    db.add(conversation)
    await db.flush()
    db.add(
        JobRun(
            id=f"jobrun-{suffix}",
            job_id=job.id,
            project_id="proj-test",
            status="in_progress",
            conversation_id=conversation.id,
        )
    )
    await db.flush()
    return conversation.id


async def _flow_work_run(
    db,
    *,
    run_id,
    agent,
    task_id,
    task_status="pending",
    policy=None,
    escalation_agent=None,
    stopped_at=None,
    archived_at=None,
    run_status="completed",
):
    """A run the flow fired to do ordinary work, bound to `task_id` the way group 2 makes real:
    `task_id` staged on the queue entry, bound via `bind_run_to_task` when the run starts."""
    conversation_id = await _flow_context(
        db, agent=agent, suffix=run_id, stopped_at=stopped_at, archived_at=archived_at
    )
    task = Task(
        id=task_id,
        project_id="proj-test",
        title="flow work",
        status=task_status,
        divergence_policy=policy,
        escalation_agent=escalation_agent,
    )
    db.add(task)
    run = Run(
        id=run_id,
        project_id="proj-test",
        agent=agent,
        status=run_status,
        conversation_id=conversation_id,
    )
    db.add(run)
    await db.flush()
    await bind_run_to_task(db, run, task)
    await db.commit()
    return run, task


async def _flow_review_run(db, *, run_id, agent, task):
    """A review turn the *same* flow staffed — its conversation belongs to a live loop too, which
    is exactly why the predicate cannot merely ask "does this run's conversation belong to a live
    loop" and must also exclude a review by kind."""
    conversation_id = await _flow_context(db, agent=agent, suffix=run_id)
    run = Run(
        id=run_id,
        project_id="proj-test",
        agent=agent,
        status="completed",
        conversation_id=conversation_id,
    )
    db.add(run)
    await db.flush()
    db.add(
        InboundQueueEntry(
            id=f"entry-{run_id}",
            project_id="proj-test",
            agent=agent,
            origin_type="job",
            content="Review the work",
            hop_depth=0,
            state="delivered",
            delivered_in_run_id=run_id,
            review_task_id=task.id,
        )
    )
    await bind_run_to_task(db, run, task)
    await db.commit()
    return run


async def _unbound_flow_conversation_run(db, *, run_id, agent, task):
    """A run bound to `task` whose conversation was never fired by any flow (no `JobRun` names
    it) — the shape a delegation or a direct operator trigger produces."""
    run = Run(id=run_id, project_id="proj-test", agent=agent, status="completed")
    db.add(run)
    await db.flush()
    await bind_run_to_task(db, run, task)
    await db.commit()
    return run


async def _orphan_job_conversation_run(db, *, run_id, agent, task):
    """A run whose conversation carries `origin='job'` but no `JobRun` row names it at all — the
    "conversation has no JobRun" branch, as opposed to "no conversation to look up"."""
    conversation = new_conversation(project_id="proj-test", agent=agent, origin="job")
    db.add(conversation)
    await db.flush()
    run = Run(
        id=run_id,
        project_id="proj-test",
        agent=agent,
        status="completed",
        conversation_id=conversation.id,
    )
    db.add(run)
    await db.flush()
    await bind_run_to_task(db, run, task)
    await db.commit()
    return run


async def _divergence(run_id: str) -> RunDivergence | None:
    async with async_session_factory() as db:
        result = await db.execute(select(RunDivergence).where(RunDivergence.run_id == run_id))
        return result.scalars().first()


async def _diverged_event(run_id: str) -> dict | None:
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "run_diverged")))
            .scalars()
            .all()
        )
    for row in rows:
        if (row.data or {}).get("run_id") == run_id:
            return row.data
    return None


async def _resolved_events(task_id: str) -> list[dict]:
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(EventLog).where(EventLog.event_type == "run_divergence_resolved")
                )
            )
            .scalars()
            .all()
        )
    return [row.data for row in rows if (row.data or {}).get("task_id") == task_id]


async def _divergence_responses(agent: str | None = None) -> list[InboundQueueEntry]:
    async with async_session_factory() as db:
        predicates = [InboundQueueEntry.origin_type == "divergence"]
        if agent is not None:
            predicates.append(InboundQueueEntry.agent == agent)
        result = await db.execute(
            select(InboundQueueEntry).where(*predicates).order_by(InboundQueueEntry.sequence)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# 3.1 / 3.4 — the predicate, exercised branch by branch against real rows
# ---------------------------------------------------------------------------


async def test_a_live_flows_work_turn_is_true(app):
    async with async_session_factory() as db:
        run, _task = await _flow_work_run(
            db, run_id="run-pred-live", agent="worker", task_id="task-pred-live"
        )
        assert await is_live_flow_work_turn(db, run) is True


async def test_a_review_turn_is_not_a_work_turn(app):
    async with async_session_factory() as db:
        task = Task(
            id="task-pred-review", project_id="proj-test", title="reviewed", status="under_review"
        )
        db.add(task)
        await db.flush()
        run = await _flow_review_run(db, run_id="run-pred-review", agent="critic", task=task)
        assert await is_live_flow_work_turn(db, run) is False


async def test_a_delegated_run_is_not_a_flow_work_turn(app):
    async with async_session_factory() as db:
        task = Task(
            id="task-pred-delegated", project_id="proj-test", title="delegated", status="pending"
        )
        db.add(task)
        await db.flush()
        run = await _unbound_flow_conversation_run(
            db, run_id="run-pred-delegated", agent="worker", task=task
        )
        assert await is_live_flow_work_turn(db, run) is False


async def test_an_operator_started_run_is_not_a_flow_work_turn(app):
    async with async_session_factory() as db:
        task = Task(
            id="task-pred-operator", project_id="proj-test", title="operator work", status="pending"
        )
        db.add(task)
        await db.flush()
        run = await _unbound_flow_conversation_run(
            db, run_id="run-pred-operator", agent="worker", task=task
        )
        assert await is_live_flow_work_turn(db, run) is False


async def test_a_stopped_flows_run_is_not_live(app):
    from datetime import datetime, timezone

    async with async_session_factory() as db:
        run, _task = await _flow_work_run(
            db,
            run_id="run-pred-stopped",
            agent="worker",
            task_id="task-pred-stopped",
            stopped_at=datetime.now(timezone.utc),
        )
        assert await is_live_flow_work_turn(db, run) is False


async def test_an_archived_flows_run_is_not_live(app):
    from datetime import datetime, timezone

    async with async_session_factory() as db:
        run, _task = await _flow_work_run(
            db,
            run_id="run-pred-archived",
            agent="worker",
            task_id="task-pred-archived",
            archived_at=datetime.now(timezone.utc),
        )
        assert await is_live_flow_work_turn(db, run) is False


async def test_a_conversation_with_no_jobrun_is_not_a_flow_work_turn(app):
    async with async_session_factory() as db:
        task = Task(id="task-pred-orphan", project_id="proj-test", title="orphan", status="pending")
        db.add(task)
        await db.flush()
        run = await _orphan_job_conversation_run(
            db, run_id="run-pred-orphan", agent="worker", task=task
        )
        assert await is_live_flow_work_turn(db, run) is False


# ---------------------------------------------------------------------------
# 4.1-4.6 — severity is derived, and resolution gets its own event kind
# ---------------------------------------------------------------------------


async def test_a_healthy_flow_work_divergence_is_announced_at_info(app):
    """4.1. Nothing broke: the task is still held by the same agent, under a live flow, and the
    run ended cleanly. That is the mechanism working, not a failure — `info`, not `warn`."""
    async with async_session_factory() as db:
        run, task = await _flow_work_run(
            db, run_id="run-div-info", agent="worker", task_id="task-div-info"
        )
        assert task.assignee == "worker", "bind_run_to_task names the agent that started the run"

    assert await evaluate_run_end("run-div-info") is not None
    payload = await _diverged_event("run-div-info")
    assert payload is not None

    async with async_session_factory() as db:
        row = await db.execute(select(EventLog).where(EventLog.event_type == "run_diverged"))
        matching = [
            r for r in row.scalars().all() if (r.data or {}).get("run_id") == "run-div-info"
        ]
        assert len(matching) == 1
        assert matching[0].severity == "info"


async def test_the_same_shape_with_the_assignee_cleared_is_warn(app):
    """4.2. The task is no longer visibly held by anyone — the healthy-continuation story does not
    hold, whatever the flow's own state says."""
    async with async_session_factory() as db:
        run, task = await _flow_work_run(
            db, run_id="run-div-cleared", agent="worker", task_id="task-div-cleared"
        )
        task.assignee = None
        await db.commit()

    assert await evaluate_run_end("run-div-cleared") is not None

    async with async_session_factory() as db:
        row = await db.execute(select(EventLog).where(EventLog.event_type == "run_diverged"))
        matching = [
            r for r in row.scalars().all() if (r.data or {}).get("run_id") == "run-div-cleared"
        ]
        assert matching[0].severity == "warn"


async def test_the_same_shape_with_an_unclean_ending_is_warn(app):
    """4.3. A crash is still divergent (the module's own stated rule), and it is never the quiet
    case — a run that did not end cleanly gets the operator's attention regardless of who still
    holds the task."""
    async with async_session_factory() as db:
        run, _task = await _flow_work_run(
            db,
            run_id="run-div-crash",
            agent="worker",
            task_id="task-div-crash",
            run_status="failed",
        )

    assert await evaluate_run_end("run-div-crash", input_returned=False) is not None

    async with async_session_factory() as db:
        row = await db.execute(select(EventLog).where(EventLog.event_type == "run_diverged"))
        matching = [
            r for r in row.scalars().all() if (r.data or {}).get("run_id") == "run-div-crash"
        ]
        assert matching[0].severity == "warn"


async def test_a_delegated_divergence_is_still_warn(app):
    """4.4. Nothing outside the flow path changes — nothing here has ever been quiet, and this
    change does not make it so."""
    async with async_session_factory() as db:
        task = Task(
            id="task-div-delegated", project_id="proj-test", title="delegated", status="pending"
        )
        db.add(task)
        await db.flush()
        await _unbound_flow_conversation_run(
            db, run_id="run-div-delegated", agent="worker", task=task
        )

    assert await evaluate_run_end("run-div-delegated") is not None

    async with async_session_factory() as db:
        row = await db.execute(select(EventLog).where(EventLog.event_type == "run_diverged"))
        matching = [
            r for r in row.scalars().all() if (r.data or {}).get("run_id") == "run-div-delegated"
        ]
        assert matching[0].severity == "warn"


async def test_the_divergence_row_does_not_carry_severity_at_all(app):
    """4.5. Severity governs the announcement, never the record — the row's own columns are
    identical whichever way the announcement was made."""
    async with async_session_factory() as db:
        await _flow_work_run(
            db, run_id="run-div-row-info", agent="worker", task_id="task-div-row-info"
        )
    await evaluate_run_end("run-div-row-info")

    async with async_session_factory() as db:
        task = Task(
            id="task-div-row-warn", project_id="proj-test", title="delegated", status="pending"
        )
        db.add(task)
        await db.flush()
        await _unbound_flow_conversation_run(
            db, run_id="run-div-row-warn", agent="worker", task=task
        )
    await evaluate_run_end("run-div-row-warn")

    info_row = await _divergence("run-div-row-info")
    warn_row = await _divergence("run-div-row-warn")
    tracked_columns = {"task_status_at_end", "run_exit_status", "policy_applied", "outcome"}
    assert (
        set(RunDivergence.__table__.columns.keys()) & {"severity"} == set()
    ), "severity must not be a column on RunDivergence at all"
    for column in tracked_columns:
        assert getattr(info_row, column) == getattr(warn_row, column)


async def test_resolving_open_divergences_names_the_task_and_the_count(app):
    """4.6. A count of zero is not an event — closing nothing is not news."""
    async with async_session_factory() as db:
        run, task = await _flow_work_run(
            db, run_id="run-div-resolve", agent="worker", task_id="task-div-resolve"
        )
    assert await evaluate_run_end("run-div-resolve") is not None
    assert await _divergence("run-div-resolve") is not None

    async with async_session_factory() as db:
        task = await db.get(Task, "task-div-resolve")
        await apply_transition(db, task, "assigned", operator())
        await db.commit()

    events = await _resolved_events("task-div-resolve")
    assert events == [{"task_id": "task-div-resolve", "count": 1}]

    async with async_session_factory() as db:
        row = await db.get(RunDivergence, (await _divergence("run-div-resolve")).sequence)
        assert row.resolved_at is not None

    # A second transition with nothing open left to close emits nothing new.
    async with async_session_factory() as db:
        task = await db.get(Task, "task-div-resolve")
        await apply_transition(db, task, "in_progress", operator())
        await db.commit()
    assert await _resolved_events("task-div-resolve") == [
        {"task_id": "task-div-resolve", "count": 1}
    ], "nothing was open, so nothing new was emitted"


# ---------------------------------------------------------------------------
# 5.1-5.5 — the flow governs its own work divergence, not `retry`
# ---------------------------------------------------------------------------


async def test_a_live_flows_retry_task_records_the_flow_regime_and_starts_nothing(app):
    """5.1. The flow is going to fire this task again on its own next tick — `retry` starting a
    second run here would race it."""
    async with async_session_factory() as db:
        await _flow_work_run(
            db, run_id="run-flow-retry", agent="worker", task_id="task-flow-retry", policy="retry"
        )

    assert await evaluate_run_end("run-flow-retry") is not None

    divergence = await _divergence("run-flow-retry")
    assert divergence.policy_applied == POLICY_FLOW
    assert divergence.outcome == "surfaced"
    assert await _divergence_responses("worker") == [], "no response run was queued"


async def test_the_same_policy_off_the_flow_path_still_retries(app):
    """5.2. Same task, same policy — but this run was not the flow's own firing, so `retry`
    applies exactly as it always has."""
    async with async_session_factory() as db:
        task = Task(
            id="task-off-flow-retry",
            project_id="proj-test",
            title="delegated retry",
            status="pending",
            divergence_policy="retry",
        )
        db.add(task)
        await db.flush()
        await _unbound_flow_conversation_run(
            db, run_id="run-off-flow-retry", agent="worker", task=task
        )

    assert await evaluate_run_end("run-off-flow-retry") is not None

    divergence = await _divergence("run-off-flow-retry")
    assert divergence.policy_applied == "retry"
    assert divergence.outcome == "retried"
    assert [e.agent for e in await _divergence_responses("worker")] == ["worker"]


async def test_a_live_flows_escalate_task_still_escalates(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """5.3. Escalation moves the work to a different agent — not something the flow's next firing
    does, so it is not a duplicate of anything and the carve-out does not apply to it."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, "worker", "escalation-target")

    async with async_session_factory() as db:
        await _flow_work_run(
            db,
            run_id="run-flow-escalate",
            agent="worker",
            task_id="task-flow-escalate",
            policy="escalate",
            escalation_agent="escalation-target",
        )

    assert await evaluate_run_end("run-flow-escalate") is not None

    divergence = await _divergence("run-flow-escalate")
    assert divergence.policy_applied == "escalate"
    assert divergence.outcome == "escalated"
    assert divergence.previous_assignee == "worker"
    assert [e.agent for e in await _divergence_responses("escalation-target")] == [
        "escalation-target"
    ]


async def test_policy_flow_can_never_be_set_on_a_task():
    """5.4. The same assertion group 2 made for `POLICY_REVIEW` — a régime a divergence row may
    record but a task may never carry."""
    assert POLICY_FLOW not in POLICIES


async def test_a_stopped_flows_retry_task_is_governed_by_the_task_policy_again(app):
    """5.5. The flow is not going to fire this task again — nothing to race, so `retry` applies
    exactly as it would off the flow path entirely."""
    from datetime import datetime, timezone

    async with async_session_factory() as db:
        await _flow_work_run(
            db,
            run_id="run-flow-stopped-retry",
            agent="worker",
            task_id="task-flow-stopped-retry",
            policy="retry",
            stopped_at=datetime.now(timezone.utc),
        )

    assert await evaluate_run_end("run-flow-stopped-retry") is not None

    divergence = await _divergence("run-flow-stopped-retry")
    assert divergence.policy_applied == "retry"
    assert divergence.outcome == "retried"
    assert [e.agent for e in await _divergence_responses("worker")] == ["worker"]
