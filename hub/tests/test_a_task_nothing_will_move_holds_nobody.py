"""`a-task-nothing-will-move-holds-nobody` — an assigned task holds its assignee only while
something will move it.

**The defect (F352's definition half).** `_agents_that_are_free` counted an agent busy while it was
the assignee of *any* task in a live status, anywhere in the project. `_loop_candidates` walks only
`Task.loop_id == loop.id`, so a task with no `loop_id`, or whose loop had ended, was never reached
by any firing, and its assignee was withdrawn from every flow in the project until somebody other
than a flow moved the task. LoopEngine froze on exactly this: a finished task's review could not be
staffed because every other agent held a bookmark the Architect had assigned outside the loop.

**The rule now (design D1).** A holding counts only while a loop that has not ended will walk it,
or a turn queued for the assignee within the hop budget names it. A running turn needs no arm of
its own: a running assignee is excluded by the running half whatever it holds.

**And the guard's other half (design D8, F372).** Widening the pool would have let a busy job
agent's *empty* loop proceed wherever a bookmark-holder existed, and an empty loop's firing briefs
the job's own agent -- the busy one -- on every tick. So the busy guard also refuses when the loop
holds no open task.

Every test here names the mutation that makes it fail; the tick in `tasks.md` records it.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, InboundQueueEntry, JobRun, Loop, Project, Task
from hub.inbound_queue import new_entry, release_entry
from hub.run_task_binding import tasks_with_a_turn_pending_or_running
from hub.scheduler import (
    JobScheduler,
    _agents_that_are_free,
    _loop_flow_busy_reason,
    decide_firing,
)
from hub.task_transitions import LIVE_STATUSES

from .review_evidence import record_review_evidence
from .test_a_held_agent_is_busy import _hold
from .test_a_loop_does_not_staff_its_own_review import AUTHOR, _completed_by, _fresh_loop
from .test_a_loop_does_not_staff_its_own_review import _queue as _flow_queue
from .test_a_loop_does_not_staff_its_own_review import _task as _flow_task
from .test_loop_busy_guard import _make_loop_job, _running_turn
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"
DEV = "dev"


@pytest.fixture
def live_scheduler(monkeypatch):
    """A `JobScheduler` the manual-run route can find. Without it the route answers 503 *"Job
    scheduler not available"* before it reaches the firing, which is how F48 survived."""
    import hub.scheduler as scheduler_module

    instance = JobScheduler()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: instance)
    return instance


async def _loop(db, *, suffix, enabled=True, ending_state=None):
    """A job and its loop, holding nothing. `enabled=False` with no ending is a pause (D2)."""
    job = AIJob(
        id=f"job-reach-{suffix}",
        project_id=PROJECT,
        name=f"Reach {suffix}",
        agent="loop-owner",
        message="work the queue",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=enabled,
    )
    db.add(job)
    await db.commit()
    loop = Loop(
        id=f"loop-reach-{suffix}",
        project_id=PROJECT,
        job_id=job.id,
        purpose=f"reach {suffix}",
        ending_state=ending_state,
    )
    db.add(loop)
    await db.commit()
    return job, loop


async def _holding(db, *, task_id="task-held", assignee=DEV, status="assigned", loop_id=None):
    task = Task(
        id=task_id,
        project_id=PROJECT,
        title=f"held by {assignee}",
        status=status,
        assignee=assignee,
        loop_id=loop_id,
    )
    db.add(task)
    await db.commit()
    return task


async def _entry(db, *, agent, task_id=None, review_task_id=None, hop_depth=0):
    """Input queued for *agent*, naming a task. A peer message, which is the only origin that can
    sit past the hop budget (`messages.py`)."""
    entry = new_entry(
        project_id=PROJECT,
        agent=agent,
        origin_type="agent",
        origin_agent="peer",
        content="about your task",
        hop_depth=hop_depth,
        task_id=task_id,
        review_task_id=review_task_id,
    )
    db.add(entry)
    await db.commit()
    return entry


async def _free():
    async with async_session_factory() as db:
        return await _agents_that_are_free(db, PROJECT)


def _no_spawn():
    """`schedule_agent` made inert, so a firing that stages somebody leaves its entry `queued` and
    starts no process. What is asserted is what the firing *queued*, which is before this."""
    from hub.turn_scheduler import ScheduleResult

    return patch(
        "hub.turn_scheduler.schedule_agent",
        AsyncMock(return_value=ScheduleResult(waiting_reason=None, terminal_failure=False)),
    )


async def _entries_for(agent, *, task_id=None):
    async with async_session_factory() as db:
        query = select(func.count()).select_from(InboundQueueEntry)
        query = query.where(InboundQueueEntry.agent == agent)
        if task_id is not None:
            query = query.where(InboundQueueEntry.task_id == task_id)
        return await db.scalar(query)


async def _job_runs(job_id):
    async with async_session_factory() as db:
        return await db.scalar(
            select(func.count()).select_from(JobRun).where(JobRun.job_id == job_id)
        )


# ---------------------------------------------------------------------------
# 1.2 - 1.7b — the predicate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", sorted(LIVE_STATUSES))
async def test_a_task_outside_every_loop_holds_nobody(app, auth_headers, bind_runner, status):
    """1.2. The LoopEngine bookmark, in every live status: status is not the variable."""
    await _roster(app, auth_headers, bind_runner, DEV)
    async with async_session_factory() as db:
        await _holding(db, status=status)

    assert DEV in await _free()


async def test_a_task_in_a_live_loop_holds_its_assignee(app, auth_headers, bind_runner):
    """1.3. D4's pile-up guard, where it is right: a queue something will serve."""
    await _roster(app, auth_headers, bind_runner, DEV)
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="live")
        await _holding(db, loop_id=loop.id)

    assert DEV not in await _free()


async def test_a_paused_loop_still_holds(app, auth_headers, bind_runner):
    """1.4. Design D2, the position flagged to the operator: re-enabling the loop briefs the
    assignee on this task again, so freeing it meanwhile would give it a second queue."""
    await _roster(app, auth_headers, bind_runner, DEV)
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="paused", enabled=False)
        await _holding(db, loop_id=loop.id)

    assert DEV not in await _free()


@pytest.mark.parametrize("ending_state", ["stopped", "completed"])
async def test_an_ended_loop_holds_nobody(app, auth_headers, bind_runner, ending_state):
    """1.5, the two endings `loop_ending.end_loop` writes. Nothing walks an ended loop again."""
    await _roster(app, auth_headers, bind_runner, DEV)
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix=ending_state, enabled=False, ending_state=ending_state)
        await _holding(db, loop_id=loop.id)

    assert DEV in await _free()


async def test_a_loop_archived_through_the_job_route_holds_nobody(app, auth_headers, bind_runner):
    """1.5, Round 2. The operator's `POST /jobs/{id}/archive` retires a looping job **without
    ending its loop** -- driven through the route so that is what is tested, not a row this test
    wrote. The loop is then hidden from the default listing, so a hold here would be invisible."""
    await _roster(app, auth_headers, bind_runner, DEV)
    async with async_session_factory() as db:
        job, loop = await _loop(db, suffix="archived")
        await _holding(db, loop_id=loop.id)

    res = await app.post(f"/api/v1/projects/{PROJECT}/jobs/{job.id}/archive", headers=auth_headers)
    assert res.status_code == 200, res.text
    async with async_session_factory() as db:
        archived = await db.get(Loop, loop.id)
        # Loudly, first: if the route ever starts ending the loop, this test stops testing the
        # archived clause and must be re-staged rather than silently keep passing.
        assert archived.ending_state is None
        assert archived.archived_at is not None

    assert DEV in await _free()


async def test_a_loop_id_naming_no_loop_holds_nobody(app, auth_headers, bind_runner):
    """1.5. `Task.loop_id` is not a foreign key. An outer join would read the missing row's
    `ending_state` as NULL -- "not ended" -- and hold the agent forever."""
    await _roster(app, auth_headers, bind_runner, DEV)
    async with async_session_factory() as db:
        await _holding(db, loop_id="loop-that-does-not-exist")

    assert DEV in await _free()


@pytest.mark.parametrize("field", ["task_id", "review_task_id"])
async def test_a_turn_queued_for_the_assignee_holds_its_task(app, auth_headers, bind_runner, field):
    """1.6. Outside every loop, the one other thing that moves a task: a turn coming for its
    assignee on it."""
    await _roster(app, auth_headers, bind_runner, DEV)
    async with async_session_factory() as db:
        task = await _holding(db)
        await _entry(db, agent=DEV, **{field: task.id})

    assert DEV not in await _free()


async def test_input_past_the_hop_budget_does_not_hold_until_released(
    app, auth_headers, bind_runner
):
    """1.6b, Round 2. `_attempt_turn` never selects an entry past the budget; only the operator's
    release delivers one. LoopEngine's suspended peer chains (F361) are exactly such entries."""
    await _roster(app, auth_headers, bind_runner, DEV)
    async with async_session_factory() as db:
        budget = (await db.get(Project, PROJECT)).hop_budget
        task = await _holding(db)
        entry = await _entry(db, agent=DEV, task_id=task.id, hop_depth=budget + 1)
        entry_id = entry.id

    assert DEV in await _free(), "input nothing will deliver must not hold its assignee"

    async with async_session_factory() as db:
        released = await release_entry(db, PROJECT, entry_id)
        assert released.refusal is None, released.refusal

    assert DEV not in await _free(), "released, the entry will be delivered, so it holds"


async def test_a_turn_queued_for_somebody_else_does_not_hold_the_assignee(
    app, auth_headers, bind_runner
):
    """1.7. That agent will work the task; the assignee will not be moved by it."""
    await _roster(app, auth_headers, bind_runner, DEV)
    async with async_session_factory() as db:
        task = await _holding(db)
        await _entry(db, agent="other", task_id=task.id)

    assert DEV in await _free()


async def test_input_for_somebody_else_does_not_hide_the_assignees_own(
    app, auth_headers, bind_runner
):
    """1.7b, Round 2, re-staged in Round 3. The F154 helper keeps one agent per task, whichever row
    comes back first. With the assignee's entry between the other two by name *and* by insertion,
    it keeps a non-assignee under any of the four orders a planner could pick -- so a pool that read
    the helper would miss `dev`'s own turn whatever the database does."""
    await _roster(app, auth_headers, bind_runner, DEV)
    async with async_session_factory() as db:
        task = await _holding(db)
        await _entry(db, agent="architect", task_id=task.id)
        await _entry(db, agent=DEV, task_id=task.id)
        await _entry(db, agent="zeta", task_id=task.id)
        helper = await tasks_with_a_turn_pending_or_running(db, PROJECT)

    # The premise the mutation needs, asserted so a change in the helper re-stages this test
    # instead of leaving it asserting over nothing.
    assert helper.get(task.id) in {"architect", "zeta"}, helper
    assert DEV not in await _free()


# ---------------------------------------------------------------------------
# 3.1 - 3.6 — the callers, through the real functions
# ---------------------------------------------------------------------------

B = "bb-bookmark"
C = "cc-bookmark"


async def test_the_loopengine_shape_staffs_its_review(app, auth_headers, bind_runner):
    """3.1. A flow's finished task, its author excluded, and every other agent holding only a task
    the Architect assigned outside the loop. Before: rung 3, "could not staff this step"."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, B, C)
    async with async_session_factory() as db:
        job, loop = await _flow_queue(db, suffix="loopengine", declares_document=True)
        task = await _flow_task(db, loop, suffix="loopengine")
        await _completed_by(db, task)
        await record_review_evidence(db, task.id, suffix="reach-loopengine", actor=AUTHOR)
        await _holding(db, task_id="task-bookmark-b", assignee=B, status="in_progress")
        await _holding(db, task_id="task-bookmark-c", assignee=C, status="pending")

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert [(s.task.id, s.agent, s.is_review) for s in decision.selections] == [(task.id, B, True)]
    assert decision.unstaffed == ()


async def test_new_work_is_given_to_a_bookmark_holder(app, auth_headers, bind_runner):
    """3.2. A bookmark should not cost the project an agent for new work either."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, B)
    async with async_session_factory() as db:
        job, loop = await _flow_queue(db, suffix="newwork", declares_document=True)
        first = await _flow_task(db, loop, suffix="newwork-1")
        second = await _flow_task(db, loop, suffix="newwork-2")
        await _running_turn(db, agent=AUTHOR, suffix="newwork")
        await _holding(db, task_id="task-bookmark-newwork", assignee=B, status="in_progress")

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert [s.agent for s in decision.selections] == [B]
    assert decision.selections[0].task.id in {first.id, second.id}


async def _guard_case(db, *, suffix, bookmark_in_live_loop):
    """3.3's staging: the job's agent mid-turn, one other agent holding one task, and the guard's
    loop holding a startable unassigned task (Round 3: without it the case tests D8 instead)."""
    job, loop, task = await _make_loop_job(db, suffix=suffix, agent="guard-owner")
    await _running_turn(db, agent="guard-owner", suffix=suffix)
    elsewhere = None
    if bookmark_in_live_loop:
        _other_job, elsewhere = await _loop(db, suffix=f"{suffix}-elsewhere")
    await _holding(
        db,
        task_id=f"task-bookmark-{suffix}",
        assignee=B,
        status="in_progress",
        loop_id=elsewhere.id if elsewhere else None,
    )
    return job, loop, task


async def test_the_guard_agrees_with_the_walk(app, auth_headers, bind_runner):
    """3.3. If the guard kept the strict rule while the walk used reachability, it would refuse
    firings the walk could staff: two answers to one question."""
    await _roster(app, auth_headers, bind_runner, B)
    async with async_session_factory() as db:
        job, loop, _task = await _guard_case(db, suffix="guard-out", bookmark_in_live_loop=False)
        assert await _loop_flow_busy_reason(db, loop, job.agent) is None

    async with async_session_factory() as db:
        job, loop, _task = await _guard_case(db, suffix="guard-in", bookmark_in_live_loop=True)
        reason = await _loop_flow_busy_reason(db, loop, job.agent)
    assert reason == "guard-owner is already running a turn"


async def test_run_staffs_the_bookmark_holder_and_answers_success(
    app, auth_headers, bind_runner, live_scheduler
):
    """3.4, the F108 question: what the route *returns*. 200 and the other agent's input queued,
    not the guard's 409."""
    await _roster(app, auth_headers, bind_runner, B)
    async with async_session_factory() as db:
        job, _loop_row, task = await _guard_case(db, suffix="run-out", bookmark_in_live_loop=False)

    with _no_spawn():
        res = await app.post(f"/api/v1/projects/{PROJECT}/jobs/{job.id}/run", headers=auth_headers)

    assert res.status_code == 200, res.text
    assert res.json()["success"] is True
    assert await _entries_for(B, task_id=task.id) == 1
    assert await _entries_for("guard-owner") == 0


async def test_run_still_answers_409_when_the_holding_is_in_a_live_loop(
    app, auth_headers, bind_runner, live_scheduler
):
    """3.4's second case, in its own database: staged after the first case, the first firing's own
    staffing of `B` would be what refused, and the staging here would test nothing."""
    await _roster(app, auth_headers, bind_runner, B)
    async with async_session_factory() as db:
        job, _loop_row, _task = await _guard_case(db, suffix="run-in", bookmark_in_live_loop=True)

    with _no_spawn():
        res = await app.post(f"/api/v1/projects/{PROJECT}/jobs/{job.id}/run", headers=auth_headers)

    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert "guard-owner is already running a turn" in detail
    assert "no other agent is free to take this loop's work" in detail
    assert "Nothing was started" in detail


async def test_the_board_does_not_read_the_busy_sentence(app, auth_headers, bind_runner):
    """3.5. The board re-asks the guard only on a stalled decision; with the bookmark-holder free,
    the walk staffs it and nothing is stalled."""
    from hub.api.v1.jobs import _batch_loop_summaries

    await _roster(app, auth_headers, bind_runner, B)
    async with async_session_factory() as db:
        job, _loop_row, _task = await _guard_case(db, suffix="board", bookmark_in_live_loop=False)

    async with async_session_factory() as db:
        summary = (await _batch_loop_summaries(db, [job.id]))[job.id]

    assert "is already running a turn" not in (summary.stall_reason or "")


async def test_the_roster_still_counts_a_bookmark(app, auth_headers, bind_runner):
    """3.6. The roster answers *what does this agent hold*, which is still every live task. Pins a
    spec scenario this change must not break, not code it writes."""
    await _roster(app, auth_headers, bind_runner, DEV)
    async with async_session_factory() as db:
        await _holding(db)

    res = await app.get(f"/api/v1/projects/{PROJECT}/agents", headers=auth_headers)
    assert res.status_code == 200, res.text
    dev = next(agent for agent in res.json() if agent["name"] == DEV)
    assert dev["active_task_count"] == 1
    assert DEV in await _free(), "and the pool, asked the other question, answers the other way"


# ---------------------------------------------------------------------------
# 3b — the guard's queue half (design D8, F372)
# ---------------------------------------------------------------------------

OWNER = "busy-agent"
FREE = "free-agent"


async def _empty_loop(db, *, suffix):
    """`_make_loop_job`'s loop with its staged task deleted: a queue that holds nothing."""
    job, loop, task = await _make_loop_job(db, suffix=suffix, agent=OWNER)
    await db.delete(task)
    await db.commit()
    return job, loop


async def _fire(job_id, times=1):
    scheduler = JobScheduler()
    outcomes = []
    with _no_spawn():
        for _ in range(times):
            async with async_session_factory() as db:
                fresh_job = await db.get(AIJob, job_id)
                outcomes.append(
                    await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)
                )
    return outcomes


async def test_a_busy_agents_empty_loop_queues_nothing_whoever_is_free(
    app, auth_headers, bind_runner
):
    """3b.2. Measured by R3 against the code before D8: three firings, three briefings queued for
    the busy agent, three `JobRun`s."""
    await _roster(app, auth_headers, bind_runner, OWNER, FREE)
    async with async_session_factory() as db:
        job, _loop_row = await _empty_loop(db, suffix="empty-free")
        await _running_turn(db, agent=OWNER, suffix="empty-free")

    outcomes = await _fire(job.id, times=3)

    # Counts first, in the order the requirement states them, so a regression names its number.
    assert await _entries_for(OWNER) == 0
    assert await _job_runs(job.id) == 0
    assert outcomes == [False] * 3


async def test_the_same_when_the_free_agent_holds_only_a_bookmark(app, auth_headers, bind_runner):
    """3b.3. The case this change would otherwise have opened: the old holding rule refused it,
    the reachability rule frees the bookmark-holder, and only the queue half refuses now."""
    await _roster(app, auth_headers, bind_runner, OWNER, FREE)
    async with async_session_factory() as db:
        job, _loop_row = await _empty_loop(db, suffix="empty-bookmark")
        await _running_turn(db, agent=OWNER, suffix="empty-bookmark")
        await _holding(db, task_id="task-bookmark-free", assignee=FREE, status="pending")

    await _fire(job.id, times=3)

    assert await _entries_for(OWNER) == 0
    assert await _job_runs(job.id) == 0


async def test_a_held_agents_empty_loop_queues_nothing(app, auth_headers, bind_runner):
    """3b.4. A hold is busy for the guard exactly as a running turn is."""
    await _roster(app, auth_headers, bind_runner, OWNER, FREE)
    async with async_session_factory() as db:
        job, _loop_row = await _empty_loop(db, suffix="empty-held")
    await _hold(OWNER)

    await _fire(job.id, times=2)

    assert await _entries_for(OWNER) == 0


async def test_an_idle_agents_empty_loop_still_fires_its_agent(app, auth_headers, bind_runner):
    """3b.5. The queue half is conjunctive with busy: a never-filled loop still briefs its own
    agent to fill it, which is what a loop is created to do."""
    await _roster(app, auth_headers, bind_runner, OWNER, FREE)
    async with async_session_factory() as db:
        job, _loop_row = await _empty_loop(db, suffix="empty-idle")

    outcomes = await _fire(job.id)

    assert await _entries_for(OWNER) == 1
    assert outcomes == [True]


async def test_run_on_a_busy_agents_empty_loop_names_the_empty_queue(
    app, auth_headers, bind_runner, live_scheduler
):
    """3b.6, the F108 question for D8. Measured by R3 before D8: 200 `{"success": true}` and a
    fourth briefing for the busy agent. The sentence names the half that refused: telling the
    operator nobody else is free, when somebody is, sends them to free an agent for nothing."""
    await _roster(app, auth_headers, bind_runner, OWNER, FREE)
    async with async_session_factory() as db:
        job, _loop_row = await _empty_loop(db, suffix="empty-run")
        await _running_turn(db, agent=OWNER, suffix="empty-run")

    with _no_spawn():
        res = await app.post(f"/api/v1/projects/{PROJECT}/jobs/{job.id}/run", headers=auth_headers)

    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert f"{OWNER} is already running a turn" in detail
    assert "Nothing was started" in detail
    assert "no other agent is free" not in detail
    assert await _entries_for(OWNER) == 0
