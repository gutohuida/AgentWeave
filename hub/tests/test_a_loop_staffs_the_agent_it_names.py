"""`a-loop-staffs-the-agent-it-names` — F128: a documentless loop's firing may staff only the
agent its job names, or nobody.

**The defect.** `agent-flows:14-15` says a loop declaring no document "SHALL be unaffected" by
flow behaviour and "SHALL behave exactly as it does today" — unconditionally, naming the agent
fired. `loop-becomes-a-flow`'s D12 narrowed the whole-firing busy guard project-wide so a *flow*
could staff a second agent while its job's agent was mid-turn, and shipped it for every loop: a
documentless loop whose agent was busy could hand its next pending task to a free sibling,
substituting an agent with a different `charter_id`, `runner_id` and authority flags with nobody
told (`AIJob.agent` is what the job form and loop list present as who runs this loop).

**The repair, design D1/D2.** `_agents_a_loop_may_staff(session, loop)` narrows
`_agents_that_are_free`'s pool: empty for a documentless loop (the job's own agent never comes
from this pool — `decide_firing`'s default-agent branch reaches it on its own), unfiltered for a
flow. `decide_firing`'s fresh-work draw and `_loop_flow_busy_reason`'s pool check both read it
(design D3); the reviewer ladder (`resolve_reviewer`) reads none of it and stays project-scoped
by design (D5) — the F70 wedged-review recovery and `run_divergence`'s silent-reviewer
substitution are both exceptions to "one agent only", stated and tested, not accidents of scope.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, InboundQueueEntry, JobRun, Loop, Run, SpecDocument, Task
from hub.run_divergence import evaluate_run_end
from hub.scheduler import JobScheduler, decide_firing
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _loop_job(db, *, suffix, agent="gamma", declares_document=False):
    """A job and its loop. `declares_document` is D7's whole discriminator."""
    job = AIJob(
        id=f"job-alsn-{suffix}",
        project_id="proj-test",
        name=f"ALSN {suffix}",
        agent=agent,
        message="work the queue",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    if declares_document:
        db.add(
            SpecDocument(
                id=f"doc-alsn-{suffix}",
                project_id="proj-test",
                path=f"spec/alsn-{suffix}.html",
                title=f"ALSN {suffix}",
                phase="current",
                kind="capability",
            )
        )
    await db.commit()
    loop = Loop(
        id=f"loop-alsn-{suffix}",
        project_id="proj-test",
        job_id=job.id,
        purpose=f"alsn {suffix}",
        spec_document_id=f"doc-alsn-{suffix}" if declares_document else None,
    )
    db.add(loop)
    await db.commit()
    return job, loop


async def _task(db, loop, *, suffix, status="pending", assignee=None):
    task = Task(
        id=f"task-alsn-{suffix}",
        project_id="proj-test",
        title=f"work {suffix}",
        status=status,
        assignee=assignee,
        loop_id=loop.id,
    )
    db.add(task)
    await db.commit()
    return task


async def _fresh_loop(db, loop_id):
    return (await db.execute(select(Loop).where(Loop.id == loop_id))).scalar_one()


async def _fresh_task(db, task_id):
    return (await db.execute(select(Task).where(Task.id == task_id))).scalar_one()


async def _running_turn(db, *, agent, suffix):
    run = Run(id=f"run-alsn-{suffix}", project_id="proj-test", agent=agent, status="running")
    db.add(run)
    await db.commit()
    return run


# ---------------------------------------------------------------------------
# 1. The scope filter (design D1, D2, D7)
# ---------------------------------------------------------------------------


async def test_a_documentless_loop_does_not_hand_its_task_to_a_free_sibling(
    app, auth_headers, bind_runner
):
    """1.1 — F128's own reproduction (`scripts/drive/t_run_while_busy.py`), as a unit test.

    `gamma` is the job's own agent and is mid-turn; `alpha` is free and idle; one pending task has
    no assignee. `decide_firing` must select nobody, and the task must keep its status and gain no
    assignee. *Mutation (measured):* deleting `_agents_a_loop_may_staff`'s `if loop.spec_document_id
    is None: return []` guard (so the pool falls straight through to the unfiltered
    `_agents_that_are_free` call) makes this fail by selecting `alpha` — observed, then reverted.
    """
    await _roster(app, auth_headers, bind_runner, "gamma", "alpha")
    async with async_session_factory() as db:
        job, loop = await _loop_job(db, suffix="scope1", agent="gamma")
        task = await _task(db, loop, suffix="scope1")
        await _running_turn(db, agent="gamma", suffix="scope1")

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert (
        decision.selections == ()
    ), "a documentless loop must not hand an unassigned task to a free sibling while its own agent is busy"
    async with async_session_factory() as db:
        fresh = await _fresh_task(db, task.id)
        assert fresh.status == "pending"
        assert fresh.assignee is None


async def test_a_flow_still_hands_the_task_to_a_free_sibling(app, auth_headers, bind_runner):
    """1.2 — the flow-width control for 1.1. Same shape, a specification document declared:
    `alpha` **is** selected. This is what keeps the change from being a project-wide regression,
    and it must fail if the filter is applied unconditionally."""
    await _roster(app, auth_headers, bind_runner, "gamma", "alpha")
    async with async_session_factory() as db:
        job, loop = await _loop_job(db, suffix="scope2", agent="gamma", declares_document=True)
        task = await _task(db, loop, suffix="scope2")
        await _running_turn(db, agent="gamma", suffix="scope2")

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert [(s.task.id, s.agent) for s in decision.selections] == [
        (task.id, "alpha")
    ], "a flow must still staff a free sibling while its job's agent is busy (design D12, unaffected)"


async def test_a_documentless_loop_starts_only_one_task_for_its_own_agent(
    app, auth_headers, bind_runner
):
    """1.6 — no width for a loop. Two startable, unassigned tasks, `gamma` (the job's own agent)
    and `alpha` (a sibling) both free: exactly one selection, for `gamma`.

    The task's own mutation — `_agents_a_loop_may_staff` returning `[default_agent]` instead of
    `[]` for a documentless loop — is **inert against this fixture, measured**: `free` is only
    consulted once `default_taken` is true or the default agent is unavailable, and by the time
    either holds, `gamma` is already in `taken` from the branch above, so a pool of `[gamma]` and a
    pool of `[]` filter to the same candidate set. Confirmed by hand-applying the mutation and
    observing the assertion below still pass, then reverting. The width claim this test makes
    (exactly one selection, not two) is still real and still worth guarding — `alpha` must not be
    handed the second task — so the test stays; the named mutation just is not what falsifies it.
    `test_a_documentless_loop_does_not_hand_its_task_to_a_free_sibling` (1.1) is what a pool
    returning `[default_agent]` while `default_agent` is genuinely busy and not yet `taken` would
    falsify, and does.
    """
    await _roster(app, auth_headers, bind_runner, "gamma", "alpha")
    async with async_session_factory() as db:
        job, loop = await _loop_job(db, suffix="width1", agent="gamma")
        task1 = await _task(db, loop, suffix="width1a")
        await _task(db, loop, suffix="width1b")

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert [(s.task.id, s.agent) for s in decision.selections] == [
        (task1.id, "gamma")
    ], "a documentless loop must start exactly one task, for its own agent, never a sibling"


# ---------------------------------------------------------------------------
# 2. Staffing is not resumption (design D6 — R2-2)
# ---------------------------------------------------------------------------


async def test_a_documentless_loop_resumes_a_sibling_while_staffing_its_own_agent(
    app, auth_headers, bind_runner
):
    """2.1 — the arm that falsified R1's requirement. `task1` is already assigned to `alpha`
    (resumed, not staffed); `task2` is pending and unassigned; `gamma` (the job's own agent) is
    idle. The firing resumes `task1` for `alpha` and starts `task2` for `gamma` — two selections,
    one of them an agent the job does not name, correct and unchanged by this scope filter because
    resumption never reads `free`.

    *Mutation (measured):* applying the loop filter to the resumption arm as well — i.e. having
    the `task.assignee` branch also require the assignee to appear in `_agents_a_loop_may_staff`'s
    pool — drops `alpha`'s selection entirely. Observed failing, reverted.
    """
    await _roster(app, auth_headers, bind_runner, "gamma", "alpha")
    async with async_session_factory() as db:
        job, loop = await _loop_job(db, suffix="resume1", agent="gamma")
        task1 = await _task(db, loop, suffix="resume1a", assignee="alpha")
        task2 = await _task(db, loop, suffix="resume1b")

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert sorted((s.task.id, s.agent) for s in decision.selections) == sorted(
        [(task1.id, "alpha"), (task2.id, "gamma")]
    ), "resumption of an existing assignee must survive the scope filter untouched"


async def test_a_documentless_loop_resumes_nothing_while_its_agent_runs(
    app, auth_headers, bind_runner
):
    """2.2 — and D6 is conditional on the named agent being idle (R2-6). Same shape as 2.1, but
    `gamma` is running a turn: the whole firing is refused before the walk
    (`_loop_flow_busy_reason`), so `task1` is **not** resumed for `alpha` either — including work
    held by a free agent. This is part of the accepted cost (design D3/D6), asserted as a fact
    rather than a sentence."""
    await _roster(app, auth_headers, bind_runner, "gamma", "alpha")
    async with async_session_factory() as db:
        job, loop = await _loop_job(db, suffix="resume2", agent="gamma")
        await _task(db, loop, suffix="resume2a", assignee="alpha")
        await _task(db, loop, suffix="resume2b")
        await _running_turn(db, agent="gamma", suffix="resume2")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        assert await scheduler._fire_job_internal(fresh_job, "scheduled", session=db) is False

    async with async_session_factory() as db:
        runs = (
            (
                await db.execute(
                    select(Run).where(Run.project_id == "proj-test", Run.agent == "alpha")
                )
            )
            .scalars()
            .all()
        )
        assert runs == [], "a refused firing must start nothing for the free sibling either"
        entries = (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == "alpha")))
            .scalars()
            .all()
        )
        assert entries == [], "a refused firing must queue nothing for the free sibling either"


# ---------------------------------------------------------------------------
# 3. The busy guard (design D3)
# ---------------------------------------------------------------------------


async def test_a_busy_documentless_loop_is_refused_even_with_a_free_sibling(
    app, auth_headers, bind_runner
):
    """3.1 — `_loop_flow_busy_reason` (reached through `_fire_job_internal`) now refuses a
    documentless loop whose agent is busy even though another agent is free and the queue holds an
    open task. Before this change it returned `None` (F128).

    *Mutation (measured):* reverting the busy-reason pool read from `_agents_a_loop_may_staff`
    back to `_agents_that_are_free` reproduces F128 — the firing proceeds and stages `alpha` for
    the open task instead of refusing outright. Observed, reverted.
    """
    await _roster(app, auth_headers, bind_runner, "gamma", "alpha")
    async with async_session_factory() as db:
        job, _loop = await _loop_job(db, suffix="busy1", agent="gamma")
        task = await _task(db, _loop, suffix="busy1")
        await _running_turn(db, agent="gamma", suffix="busy1")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        assert await scheduler._fire_job_internal(fresh_job, "scheduled", session=db) is False

    async with async_session_factory() as db:
        fresh_task = await _fresh_task(db, task.id)
        assert fresh_task.status == "pending"
        assert fresh_task.assignee is None
        runs = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
        assert runs == [], "a busy refusal writes no execution record (design D4)"


async def test_a_busy_flow_still_staffs_the_free_sibling(app, auth_headers, bind_runner):
    """3.2 — the flow control for 3.1. Same shape, a specification document declared: the guard
    returns `None` and the firing proceeds to staff `alpha`."""
    await _roster(app, auth_headers, bind_runner, "gamma", "alpha")
    async with async_session_factory() as db:
        job, _loop = await _loop_job(db, suffix="busy2", agent="gamma", declares_document=True)
        task = await _task(db, _loop, suffix="busy2")
        await _running_turn(db, agent="gamma", suffix="busy2")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        assert await scheduler._fire_job_internal(fresh_job, "scheduled", session=db) is True

    async with async_session_factory() as db:
        fresh_task = await _fresh_task(db, task.id)
        assert fresh_task.assignee == "alpha", "a flow must still staff its free sibling while busy"


async def test_a_busy_documentless_loop_advances_its_schedule_without_starting_a_second_agent(
    app, auth_headers, bind_runner
):
    """3.4 — the cron path. A documentless loop whose agent is busy and whose sibling is free
    writes no `JobRun` and no event, and still advances `job.next_run` — refused, not stopped."""
    await _roster(app, auth_headers, bind_runner, "gamma", "alpha")
    async with async_session_factory() as db:
        job, _loop = await _loop_job(db, suffix="busy4", agent="gamma")
        await _task(db, _loop, suffix="busy4")
        await _running_turn(db, agent="gamma", suffix="busy4")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        assert await scheduler._fire_job_internal(fresh_job, "scheduled", session=db) is False

    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        assert fresh_job.enabled is True
        assert fresh_job.next_run is not None, "the schedule must still advance on a refusal"
        assert fresh_job.run_count == 0
        runs = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
        assert runs == []


async def test_repeated_firings_of_a_busy_documentless_loop_queue_nothing(
    app, auth_headers, bind_runner
):
    """3.5 — repeated firings in the busy-with-a-free-sibling state create zero inbound queue
    entries, for either agent."""
    await _roster(app, auth_headers, bind_runner, "gamma", "alpha")
    async with async_session_factory() as db:
        job, _loop = await _loop_job(db, suffix="busy5", agent="gamma")
        await _task(db, _loop, suffix="busy5")
        await _running_turn(db, agent="gamma", suffix="busy5")

    scheduler = JobScheduler()
    for _ in range(3):
        async with async_session_factory() as db:
            fresh_job = await db.get(AIJob, job.id)
            assert await scheduler._fire_job_internal(fresh_job, "scheduled", session=db) is False

    async with async_session_factory() as db:
        entries = (await db.execute(select(InboundQueueEntry))).scalars().all()
        assert entries == [], "three refused firings must queue nothing for anybody"


# ---------------------------------------------------------------------------
# 4. The F70 exception (design D5 — R2-1, the blocking finding)
# ---------------------------------------------------------------------------


async def test_a_documentless_loops_silent_review_still_recovers_a_project_wide_reviewer(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """4.2 — `run_divergence.py`'s silent-reviewer substitution still resolves a project-wide
    reviewer for a **loop's** task after a verdict-less review turn, unaffected by the scope
    filter: `resolve_reviewer` (called from `_answer_failed_review`) reads no loop and no
    `_agents_a_loop_may_staff` narrowing (design D5). `critic` reviewed and said nothing; `auditor`
    is free and is not the author; the loop declares no document. `auditor` must still be resolved
    — narrowing this path would leave the row wedged permanently, which design D5 rejects.
    """
    from .test_agent_trigger import _init_repo
    from .test_review_divergence import _review_run_that_said_nothing

    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, "gamma", "critic", "auditor")

    async with async_session_factory() as db:
        _job, loop = await _loop_job(db, suffix="f70b", agent="gamma")
        task = await _task(db, loop, suffix="f70b")
        actor = run_actor(run_id=f"run-author-{task.id}", agent="gamma")
        for status in ("assigned", "in_progress", "completed"):
            await apply_transition(db, task, status, actor)
        fresh_task = await _fresh_task(db, task.id)
        # Staffed for review, then ends without a verdict — exactly the shape this helper builds
        # for a flow's task; here the task's `loop_id` is a documentless loop's instead.
        await _review_run_that_said_nothing(db, "run-f70b-critic", fresh_task, reviewer="critic")

    assert await evaluate_run_end("run-f70b-critic") is not None

    async with async_session_factory() as db:
        fresh_task = await _fresh_task(db, task.id)
        assert fresh_task.assignee == "auditor", (
            "the silent-review recovery must still resolve a project-wide reviewer for a "
            "documentless loop's task"
        )
        assert fresh_task.status == "under_review"
