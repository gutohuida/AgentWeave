"""`loop-becomes-a-flow` group 5 — a firing starts every task it can staff, not the first one.

Design D5: *"A firing starts every task whose dependencies are met and for which an agent resolved,
bounded by available agents. No cap, no configuration."* The bound is the shape of the decomposition
the operator approved, not a dial they turn afterwards — which is why the *Rejected* clause of D5
names serial firing as the thing that "makes the graph decorative: a DAG walked in a valid order
that never uses its width".

Three rules constrain the widening, and there is a test here for each:

* **D6** — one agent, one task, per firing. An agent selected twice would be started twice and
  `schedule_agent` would refuse the second *silently*; deciding it here makes the drop visible.
* **D12** — who works the second ordinary task, and the rule that an already-assigned task resumes
  with its own assignee rather than being handed to the job's default agent.
* **D13** — a wide firing records one `JobRun` per selection, because `conversation_id` is the only
  correlation a `JobRun` has back to the `Run` it started.

**5.2 is the test with the sharpest edge.** Running out of agents is the bound working, not a
failure, and the tasks that did not start must be left *completely* alone — status and assignee
both. A widening that marked them `assigned` "ready for next time" would hand three tasks to one
agent and call it parallelism.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    InboundQueueEntry,
    JobRun,
    Loop,
    Project,
    Run,
    Task,
    TaskDependency,
    TurnUsage,
)
from hub.scheduler import JobScheduler, _compose_loop_briefing, decide_firing
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

OWNER = "width-owner"
SECOND = "width-second"
THIRD = "width-third"


async def _flow(db, *, suffix, agent=OWNER, stop_at=None):
    job = AIJob(
        id=f"job-width-{suffix}",
        project_id="proj-test",
        name=f"Width {suffix}",
        agent=agent,
        message="work the queue",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(
        id=f"loop-width-{suffix}",
        project_id="proj-test",
        job_id=job.id,
        purpose=f"width {suffix}",
        stop_at=stop_at,
    )
    db.add(loop)
    await db.commit()
    return job, loop


async def _task(db, loop, key, *, status="pending", assignee=None, title=None):
    task = Task(
        id=f"task-width-{key}",
        project_id="proj-test",
        title=title or f"work {key}",
        status=status,
        loop_id=loop.id,
        assignee=assignee,
    )
    db.add(task)
    await db.commit()
    return task


async def _depend(db, task_id, depends_on_id):
    """`TaskDependency` has no autoincrement and no `project_id` default — both are explicit."""
    db.add(
        TaskDependency(
            id=f"dep-{task_id}-{depends_on_id}",
            project_id="proj-test",
            task_id=task_id,
            depends_on_task_id=depends_on_id,
        )
    )
    await db.commit()


async def _decide(job_id, loop_id, agent=OWNER):
    async with async_session_factory() as db:
        loop = (await db.execute(select(Loop).where(Loop.id == loop_id))).scalar_one()
        return await decide_firing(db, loop, default_agent=agent)


def _pairs(decision):
    """`(task_id, agent)` for each selection, in the order the walk produced them."""
    return [(s.task.id, s.agent) for s in decision.selections]


# ---------------------------------------------------------------------------
# 5.1 — two startable tasks and two eligible agents start both
# ---------------------------------------------------------------------------


async def test_two_startable_tasks_and_two_eligible_agents_start_both(
    app, auth_headers, bind_runner
):
    """The assertion group 5 exists for. Before it, the walk returned on its first staffable
    candidate and the second task waited a whole cron interval for no reason."""
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="two")
        await _task(db, loop, "two-a")
        await _task(db, loop, "two-b")

    decision = await _decide(job.id, loop.id)

    assert len(decision.selections) == 2
    # The job's own agent takes the first (design D2's default is still first in line); the second
    # is recruited from the free pool.
    assert _pairs(decision) == [("task-width-two-a", OWNER), ("task-width-two-b", SECOND)]
    assert decision.deferred == ()


async def test_the_pairing_is_deterministic_across_reruns(app, auth_headers, bind_runner):
    """D5 requires a firing to select "a task and an agent, both deterministically". Two free
    agents and two tasks is the smallest case where a set-valued walk could answer differently
    twice — `_loop_queue_order` and `_agents_that_are_free`'s name ordering are what stop it."""
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND, THIRD)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="stable")
        await _task(db, loop, "stable-a")
        await _task(db, loop, "stable-b")

    first = _pairs(await _decide(job.id, loop.id))
    second = _pairs(await _decide(job.id, loop.id))
    assert first == second
    assert len({agent for _task_id, agent in first}) == 2


# ---------------------------------------------------------------------------
# 5.2 — three startable tasks and one eligible agent start one, the rest untouched
# ---------------------------------------------------------------------------


async def test_three_startable_tasks_and_one_agent_start_one_and_touch_nothing_else(
    app, auth_headers, bind_runner
):
    """Running out of agents is D5's bound working, not a failure — so the two tasks that did not
    start keep their status **and** their assignee. Asserting both matters: a widening that marked
    the leftovers `assigned` to have them "ready" would put three tasks on one agent, which is the
    pile-up D4 rung 2 was written to avoid, reached from the other end."""
    await _roster(app, auth_headers, bind_runner, OWNER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="one")
        await _task(db, loop, "one-a")
        await _task(db, loop, "one-b")
        await _task(db, loop, "one-c")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    async with async_session_factory() as db:
        rows = {
            t.id: (t.status, t.assignee)
            for t in (
                (await db.execute(select(Task).where(Task.loop_id == loop.id))).scalars().all()
            )
        }
        entries = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.origin_type == "job")
                )
            )
            .scalars()
            .all()
        )

    assert rows["task-width-one-a"] == ("assigned", OWNER)
    assert rows["task-width-one-b"] == ("pending", None)
    assert rows["task-width-one-c"] == ("pending", None)
    assert len(entries) == 1


# ---------------------------------------------------------------------------
# 5.3 — a dependent task does not start alongside its prerequisite
# ---------------------------------------------------------------------------


async def test_a_dependent_task_does_not_start_alongside_its_prerequisite(
    app, auth_headers, bind_runner
):
    """Width comes from the graph (D5), so the graph still bounds it. Two free agents are available
    and deliberately so: without the gate the walk would happily staff the second one here, which is
    the failure mode a naive widening ships — parallelism that ignores the ordering the operator
    decomposed the work into in the first place."""
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="dep")
        prereq = await _task(db, loop, "dep-prereq")
        dependent = await _task(db, loop, "dep-dependent")
        await _depend(db, dependent.id, prereq.id)

    decision = await _decide(job.id, loop.id)

    assert _pairs(decision) == [("task-width-dep-prereq", OWNER)]
    # Gated, not deferred and not unstaffed: an unmet prerequisite is a statement about the graph,
    # and it belongs in the stall reason's vocabulary rather than in D6's.
    assert decision.deferred == ()
    assert decision.unstaffed == ()


# ---------------------------------------------------------------------------
# 5.4 — design D6: one agent, one task, and the drop is visible
# ---------------------------------------------------------------------------


async def test_one_agent_resolving_for_two_tasks_is_started_for_one_only(
    app, auth_headers, bind_runner
):
    """Two tasks already assigned to the same agent both resolve to it under D12 step 1. Exactly
    one selection survives, and the other is *recorded* — `schedule_agent` would have refused the
    second start with "agent is already running" and dropped it with no trace that the firing ever
    wanted it, which is the silence D6 exists to break."""
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="d6")
        await _task(db, loop, "d6-a", status="assigned", assignee=SECOND)
        await _task(db, loop, "d6-b", status="assigned", assignee=SECOND)

    decision = await _decide(job.id, loop.id)

    assert len(decision.selections) == 1
    assert decision.selections[0].agent == SECOND
    started, dropped = decision.selections[0].task.id, decision.deferred[0][0]
    assert {started, dropped} == {"task-width-d6-a", "task-width-d6-b"}
    assert SECOND in decision.deferred[0][1]


async def test_a_deferred_selection_names_no_remedy_because_there_is_none(
    app, auth_headers, bind_runner
):
    """The distinction `FiringDecision` keeps between `deferred` and `unstaffed`. Unstaffed asks the
    operator for something — add an agent, free one, fix a name in a document. Deferred asks for
    nothing at all and resolves itself on the next tick, which is why it is logged and never
    surfaced: a flow with more ready work than agents defers on every tick by design, and an event
    for that would bury the one that does need them."""
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="quiet")
        await _task(db, loop, "quiet-a", status="assigned", assignee=SECOND)
        await _task(db, loop, "quiet-b", status="assigned", assignee=SECOND)

    decision = await _decide(job.id, loop.id)

    assert decision.unstaffed == ()
    assert "next firing" in decision.deferred[0][1] or "one at a time" in decision.deferred[0][1]


# ---------------------------------------------------------------------------
# 5.5 — design D12: resumption keeps its agent, and the busy guard is per selection
# ---------------------------------------------------------------------------


async def test_an_assigned_task_resumes_with_its_own_assignee_not_the_jobs_default(
    app, auth_headers, bind_runner
):
    """`design.md`'s own open question, closed by D12 step 1.

    Before it, `decide_firing` paired every ordinary task with the job's agent and `_do_fire_job`
    then wrote that back over `assignee` — so a task another agent was working got reassigned to
    the job's own agent and briefed to them. Harmless while a loop had one agent; under width it
    hands one agent's running work to another."""
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="resume")
        await _task(db, loop, "resume-a", status="in_progress", assignee=SECOND)

    decision = await _decide(job.id, loop.id)

    assert _pairs(decision) == [("task-width-resume-a", SECOND)]


async def test_a_busy_agent_does_not_stop_the_firing_from_staffing_a_free_one(
    app, auth_headers, bind_runner
):
    """The other half of D12, and the reason width is reachable at all after the first tick.

    `_loop_agent_busy_reason` refused the *whole* firing when the job's agent was mid-turn. In a
    flow that is wrong: `job.agent` is only the default, and an independent task with a free agent
    for it has nothing to do with whether the default agent is busy. Left as it was, a flow that
    staffed its own job's agent refused every subsequent tick for the length of that turn."""
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="busy")
        await _task(db, loop, "busy-a")
        db.add(Run(id="run-width-busy", project_id="proj-test", agent=OWNER, status="running"))
        await db.commit()

    decision = await _decide(job.id, loop.id)

    assert _pairs(decision) == [("task-width-busy-a", SECOND)]


async def test_a_single_agent_loop_whose_agent_is_busy_still_records_nothing(
    app, auth_headers, bind_runner
):
    """The property the old guard's docstring argues for at length, preserved exactly.

    A `JobRun` per refused tick evicts real history through `_prune_job_history`'s 100-row window,
    which is the problem the guard exists to prevent. The narrowing must not cost that: with one
    agent and nobody else free, the firing is still refused before any row is written."""
    await _roster(app, auth_headers, bind_runner, OWNER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="lonely")
        await _task(db, loop, "lonely-a")
        db.add(Run(id="run-width-lonely", project_id="proj-test", agent=OWNER, status="running"))
        await db.commit()

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        fired = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert fired is False
    async with async_session_factory() as db:
        runs = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
    assert runs == []


# ---------------------------------------------------------------------------
# 5.5 — design D13: one `JobRun` per selection
# ---------------------------------------------------------------------------


async def test_a_wide_firing_records_one_job_run_per_selection(app, auth_headers, bind_runner):
    """D13. `finalize_job_run_for_conversation` correlates a run back to its `Run` **only** by
    `conversation_id`, so each selection needs its own row or the correlation has nothing to work
    with. Asserting the conversations are distinct is the part that matters — two rows sharing one
    conversation would satisfy a naive count and break the finalize path just the same."""
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="rows")
        await _task(db, loop, "rows-a")
        await _task(db, loop, "rows-b")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    async with async_session_factory() as db:
        runs = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
        entries = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.origin_type == "job")
                )
            )
            .scalars()
            .all()
        )
        fresh_job = await db.get(AIJob, job.id)
        run_count = fresh_job.run_count

    assert len(runs) == 2
    assert len({r.conversation_id for r in runs}) == 2
    assert {e.agent for e in entries} == {OWNER, SECOND}
    # `run_count` keeps counting `JobRun`s, so the two stay in step (finding F11).
    assert run_count == 2


# ---------------------------------------------------------------------------
# 5.6 — `token_budget` and `stop_at` still bound a wide flow
# ---------------------------------------------------------------------------


async def test_stop_at_refuses_a_wide_firing_before_any_selection_is_made(
    app, auth_headers, bind_runner
):
    """`stop_at` is checked in `_loop_stop_reason`, above the decision, so width never enters into
    it: the firing is refused whole. Two agents and two ready tasks is the case where a per-selection
    check would have let one through."""
    from datetime import datetime, timedelta, timezone

    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(
            db, suffix="stop", stop_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        await _task(db, loop, "stop-a")
        await _task(db, loop, "stop-b")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        fired = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert fired is False
    async with async_session_factory() as db:
        entries = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.origin_type == "job")
                )
            )
            .scalars()
            .all()
        )
        fresh_job = await db.get(AIJob, job.id)
    assert entries == []
    assert fresh_job.enabled is False


async def test_an_exhausted_token_budget_starts_no_turn_for_any_selection(
    app, auth_headers, bind_runner
):
    """`token_budget` is enforced per turn inside `schedule_agent`, which every selection goes
    through — the primary one on the firing's own path and each extra one in
    `_fire_additional_selection`. So a wide firing is bounded by exactly the same check a narrow one
    is, N times, and no additional plumbing was needed for it.

    The entries are still *queued*: budget exhaustion holds an autonomous turn rather than
    discarding it, which is `test_accounting_budget.py`'s own shipped behaviour. What must not
    happen is a `Run` starting."""
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.token_budget = 100
        historical = Run(
            id="run-width-budget-history",
            project_id="proj-test",
            agent="history",
            status="completed",
        )
        db.add(historical)
        db.add(
            TurnUsage(
                id="usage-width-budget",
                run_id=historical.id,
                project_id="proj-test",
                agent="history",
                status="measured",
                input_tokens=500,
                output_tokens=0,
                total_tokens=500,
            )
        )
        await db.commit()
        job, loop = await _flow(db, suffix="budget")
        await _task(db, loop, "budget-a")
        await _task(db, loop, "budget-b")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    async with async_session_factory() as db:
        entries = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.origin_type == "job")
                )
            )
            .scalars()
            .all()
        )
        started = (
            (
                await db.execute(
                    select(Run).where(Run.project_id == "proj-test", Run.agent.in_((OWNER, SECOND)))
                )
            )
            .scalars()
            .all()
        )

    assert {e.agent for e in entries} == {OWNER, SECOND}
    assert started == []


async def test_a_review_left_over_after_the_agents_are_taken_is_deferred_not_unstaffed(
    app, auth_headers, bind_runner
):
    """The false alarm this distinction exists to prevent.

    Rung 3's message asks the operator for something — add an agent, free one, fix a name. A firing
    that merely used up the free agents on its earlier selections has none of those problems, and
    surfacing `review_unstaffed` for it would fire most often on exactly the flows working hardest.
    `resolve_reviewer` separates "nobody could ever take this" from "everybody is spoken for by this
    same tick", and only the first reaches the operator.

    Three finished tasks and three agents, one of which authored all of them: the first two reviews
    take the other two agents and the third has nobody left. Reviews are what this needs rather than
    ordinary work, because `_loop_queue_order` puts every non-pending row ahead of every pending one
    (design D10) — a review can only be *left over* behind other reviews.
    """
    from hub.task_transition_service import apply_transition
    from hub.task_transitions import run_actor

    await _roster(app, auth_headers, bind_runner, OWNER, SECOND, THIRD)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="usedup")
        for key in ("a", "b", "c"):
            task = await _task(db, loop, f"usedup-{key}")
            actor = run_actor(run_id=f"run-usedup-{key}", agent=THIRD)
            for status in ("assigned", "in_progress", "completed"):
                await apply_transition(db, task, status, actor)
            task.assignee = None
            await db.commit()

    decision = await _decide(job.id, loop.id)

    assert len(decision.selections) == 2, "two other agents exist, so two reviews are staffed"
    assert {s.agent for s in decision.selections} == {OWNER, SECOND}
    assert all(s.is_review for s in decision.selections)
    # The third is deferred, not unstaffed: nothing is wrong and the operator has nothing to fix.
    assert len(decision.deferred) == 1
    assert decision.unstaffed == ()
    assert "next firing" in decision.deferred[0][1]


# ---------------------------------------------------------------------------
# 8.1 / 8.2 — the briefing states the tier, and says nothing false about a loop
# ---------------------------------------------------------------------------


async def _briefing_for(loop, task):
    async with async_session_factory() as db:
        fresh_loop = (await db.execute(select(Loop).where(Loop.id == loop.id))).scalar_one()
        return await _compose_loop_briefing(db, fresh_loop, task, None)


async def test_a_flows_briefing_says_the_flow_routes_the_work_onward(app):
    """Design D8. The agent did not choose to be in a flow and has no reason to ask, so the one
    place it reliably reads has to tell it — and what it most needs to know is that finishing is
    the end of its job, because an agent that helpfully starts the next task defeats both the
    ordering the graph encodes and the review that follows it."""
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="tier-flow")
        loop.spec_document_id = "doc-tier"
        await db.commit()
        task = await _task(db, loop, "tier-flow")

    briefing = await _briefing_for(loop, task)

    assert "flow" in briefing.lower()
    assert "Finish the task below and stop." in briefing
    assert "routing is the flow's job" in briefing
    assert "review" in briefing.lower()


async def test_a_loops_briefing_never_claims_someone_will_review_the_work(app):
    """Task 8.2, on the true split rather than the stated one — see the group 8 review block. A
    document-less loop still gets width and review when other agents exist, so the briefing does not
    pretend the tier is what decides that; what it must never do is tell an agent alone in its
    project that somebody will check its work."""
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="tier-loop")
        assert loop.spec_document_id is None
        task = await _task(db, loop, "tier-loop")

    briefing = await _briefing_for(loop, task)

    assert "Finish the task below and stop." in briefing
    assert "review" not in briefing.lower()
    assert "flow" not in briefing.lower()
    assert "the next firing claims it" in briefing


async def test_the_tier_statement_survives_an_oversized_checkpoint(app):
    """Finding 2 of the review, asserted rather than trusted. §257 truncates *prior checkpoint
    content* in place, so a statement placed after it would survive or not depending on how much the
    previous agent happened to write — which is the one thing an instruction about stopping must not
    depend on. It leads the briefing for exactly that reason."""
    from hub.checkpoints import compute_envelope, create_checkpoint
    from hub.conversations import new_conversation
    from hub.scheduler import _LOOP_BRIEFING_CHECKPOINT_CHARS

    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="tier-big")
        loop.spec_document_id = "doc-tier-big"
        await db.commit()
        task = await _task(db, loop, "tier-big")
        conversation = new_conversation(project_id="proj-test", agent=OWNER, origin="job")
        db.add(conversation)
        await db.commit()
        checkpoint = await create_checkpoint(
            db,
            conversation,
            trigger="task_completion",
            envelope=await compute_envelope(db, conversation),
            body="x" * (_LOOP_BRIEFING_CHECKPOINT_CHARS * 2),
            loop=loop,
        )
        fresh_loop = (await db.execute(select(Loop).where(Loop.id == loop.id))).scalar_one()
        briefing = await _compose_loop_briefing(db, fresh_loop, task, checkpoint)

    assert "Finish the task below and stop." in briefing
    assert briefing.index("routing is the flow's job") < briefing.index("## Prior checkpoint")


# ---------------------------------------------------------------------------
# 9.3 — the board reports every task a firing staffs, each naming its agent
# ---------------------------------------------------------------------------


async def _summary(job_id):
    from hub.api.v1.jobs import _batch_loop_summaries

    async with async_session_factory() as db:
        return (await _batch_loop_summaries(db, [job_id]))[job_id]


async def test_the_board_reports_every_task_a_wide_firing_staffs(app, auth_headers, bind_runner):
    """Design D15, and the under-report group 5 introduced.

    `_batch_loop_summaries` took `selections[0]`, which was right while a firing made at most one
    selection and became a lie the moment the walk widened: a flow working three tasks showed one.
    The field was already a list — group 1 left it that way for exactly this — so what changed is
    that the walk stops after the first match.
    """
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND, THIRD)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="board")
        await _task(db, loop, "board-a")
        await _task(db, loop, "board-b")

    summary = await _summary(job.id)

    assert [t["id"] for t in summary.current_tasks] == ["task-width-board-a", "task-width-board-b"]
    assert [t["agent"] for t in summary.current_tasks] == [OWNER, SECOND]


async def test_the_board_still_reports_one_item_for_a_single_agent_loop(
    app, auth_headers, bind_runner
):
    """The regression bar. Every loop that exists today has one agent, and its card must read
    exactly as it did — one line, one agent, no sign that anything widened underneath it."""
    await _roster(app, auth_headers, bind_runner, OWNER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="board-one")
        await _task(db, loop, "board-one-a")
        await _task(db, loop, "board-one-b")

    summary = await _summary(job.id)

    assert [t["id"] for t in summary.current_tasks] == ["task-width-board-one-a"]
    assert summary.current_tasks[0]["agent"] == OWNER


async def test_a_current_item_with_nobody_attributed_omits_the_agent_rather_than_blanking_it(
    app, auth_headers, bind_runner
):
    """A blocked task is nobody's selection — it is waiting on a person — so its attribution is its
    own assignee, and there may not be one. The key is absent rather than empty, so a reader is
    never shown a blank where a name should be."""
    await _roster(app, auth_headers, bind_runner, OWNER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="board-blocked")
        await _task(db, loop, "board-blocked-a", status="blocked")

    summary = await _summary(job.id)

    assert [t["id"] for t in summary.current_tasks] == ["task-width-board-blocked-a"]
    assert "agent" not in summary.current_tasks[0]


async def test_a_blocked_task_carries_its_assignee_when_it_has_one(app, auth_headers, bind_runner):
    """And where the task does name somebody, that is who the operator needs — the agent whose work
    stopped for a question is the one the answer unblocks."""
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="board-assigned")
        await _task(db, loop, "board-assigned-a", status="blocked", assignee=SECOND)

    summary = await _summary(job.id)

    assert summary.current_tasks[0]["agent"] == SECOND


# ---------------------------------------------------------------------------
# F23 — work in flight is current work, and a moving queue is not a stalled one
# ---------------------------------------------------------------------------


async def test_a_task_a_busy_agent_is_working_is_reported_in_flight_not_skipped(
    app, auth_headers, bind_runner
):
    """Finding F23, found on the first live firing of a real flow.

    `decide_firing` has two callers asking two different questions: the firing asks "what can I
    start", the board asks "what is this loop working on". Design D12's resumption branch skipped a
    busy agent's task with a bare `continue` — correct for the first question, and it silently
    deleted the answer to the second.
    """
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="inflight")
        await _task(db, loop, "inflight-a", status="in_progress", assignee=SECOND)
        db.add(Run(id="run-width-inflight", project_id="proj-test", agent=SECOND, status="running"))
        await db.commit()

    decision = await _decide(job.id, loop.id)

    assert decision.selections == (), "nothing can be started — that agent is mid-turn"
    assert decision._cannot_staff == (("task-width-inflight-a", SECOND),)


async def test_a_queue_whose_work_is_all_in_flight_is_not_stalled(app, auth_headers, bind_runner):
    """The half that made F23 an (A) rather than a cosmetic wrong label.

    With the task dropped from the walk, `_stall_reason_from_walk` counted it as open and reported
    *"no claimable task among N open"* — so a flow reported as stalled precisely when every one of
    its agents was working. `loop-notices-and-reacts` exists because a working loop that reads as
    dead invites the operator to restart something that needed nothing.
    """
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND, THIRD)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="notstalled")
        for key, who in (("a", OWNER), ("b", SECOND), ("c", THIRD)):
            await _task(db, loop, f"notstalled-{key}", status="assigned", assignee=who)
        for i, who in enumerate((OWNER, SECOND, THIRD)):
            db.add(Run(id=f"run-width-ns-{i}", project_id="proj-test", agent=who, status="running"))
        await db.commit()

    decision = await _decide(job.id, loop.id)

    assert decision.stall_reason is None, "three agents mid-turn is the opposite of a stall"
    assert len(decision._cannot_staff) == 3
    assert decision.kind == "in_flight"


async def test_a_firing_with_everything_in_flight_records_nothing(app, auth_headers, bind_runner):
    """Same reasoning `_loop_flow_busy_reason` gives for the whole-firing case: the agents' own
    running rows already say they are working, and a `JobRun` per tick would duplicate that and
    evict real history through `_prune_job_history`'s window at a five-minute cadence."""
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="norecord")
        await _task(db, loop, "norecord-a", status="in_progress", assignee=SECOND)
        # OWNER is free, so the whole-firing busy guard does not catch this — the decision must.
        db.add(Run(id="run-width-nr", project_id="proj-test", agent=SECOND, status="running"))
        await db.commit()

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        fired = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert fired is False
    async with async_session_factory() as db:
        runs = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
        entries = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.origin_type == "job")
                )
            )
            .scalars()
            .all()
        )
    assert runs == [], "no row for a tick that correctly did nothing"
    assert entries == [], "and no briefing queued for an agent already working"


async def test_the_board_shows_in_flight_work_as_the_current_item(app, auth_headers, bind_runner):
    """The symptom an operator actually saw: `current_tasks: []` while three agents worked.

    The board reads `decide_firing` too, so this is the same fix seen from the caller that made it
    a defect rather than an inefficiency.
    """
    from hub.api.v1.jobs import _batch_loop_summaries

    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="boardflight")
        await _task(db, loop, "boardflight-a", status="in_progress", assignee=SECOND)
        db.add(Run(id="run-width-bf", project_id="proj-test", agent=SECOND, status="running"))
        await db.commit()

    async with async_session_factory() as db:
        summary = (await _batch_loop_summaries(db, [job.id]))[job.id]

    assert [t["id"] for t in summary.current_tasks] == ["task-width-boardflight-a"]
    assert summary.current_tasks[0]["agent"] == SECOND
    assert summary.stall_reason is None


# ---------------------------------------------------------------------------
# F64 — a stall caused by having nobody must say so, not blame the queue
# ---------------------------------------------------------------------------


async def _completed_by(db, task, agent):
    """Walk a task to `completed` through real transitions, so the ladder knows who authored it."""
    actor = run_actor(run_id=f"run-author-{task.id}", agent=agent)
    for status in ("assigned", "in_progress", "completed"):
        await apply_transition(db, task, status, actor)
    await db.commit()


async def test_a_queue_nobody_can_staff_says_so_instead_of_blaming_the_queue(
    app, auth_headers, bind_runner
):
    """The assertion that distinguishes this fix from doing nothing.

    Found live by the operator on 2026-08-26 judging group 11's check 11.4. Rung 3's own notice was
    right — *"could not staff this step: no agent is free to take it..."* — and went to the event
    stream. The loop card, the surface an operator actually reads, described the same instant as
    *"no claimable task among 1 open (1 completed)"*: a shortage of **work**, where the truth is a
    shortage of **people**. The remedies are opposite (add tasks / add an agent) and the card named
    the wrong one.

    Deliberately *not* F23's case: nothing here is in flight and nothing is running. This is the
    neighbouring state — neither busy nor short of work, but short of eligible agents — which had
    no branch of its own.
    """
    await _roster(app, auth_headers, bind_runner, OWNER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="nostaff")
        task = await _task(db, loop, "nostaff-a")
        await _completed_by(db, task, OWNER)

    decision = await _decide(job.id, loop.id)

    assert decision.kind == "stalled"
    assert decision.unstaffed, "the author is the only agent, so its review cannot be staffed"
    assert decision.stall_reason is not None
    assert (
        "could not staff" in decision.stall_reason
    ), f"the card must name the staffing cause, not the queue; got {decision.stall_reason!r}"
    assert "no claimable task among" not in decision.stall_reason


async def test_a_genuinely_empty_queue_still_blames_the_queue(app, auth_headers, bind_runner):
    """The other side, so the fix cannot become "always say staffing".

    A queue whose candidates are gated on an unapproved prerequisite has nothing to do with
    staffing, and telling that operator to add an agent would send them somewhere useless. Nothing
    is unstaffed here, so the queue sentence must survive untouched.
    """
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="reallyempty")
        blocker = await _task(db, loop, "reallyempty-a", status="pending")
        gated = await _task(db, loop, "reallyempty-b", status="pending")
        await _depend(db, gated.id, blocker.id)
        await _completed_by(db, blocker, OWNER)
        await apply_transition(
            db, blocker, "under_review", run_actor(run_id="run-re-x", agent=SECOND)
        )
        await db.commit()

    decision = await _decide(job.id, loop.id)

    assert decision.kind == "stalled"
    assert decision.stall_reason is not None
    assert (
        not decision.unstaffed
    ), "SECOND can review the blocker, so nothing is unstaffable and the queue sentence must stand"
