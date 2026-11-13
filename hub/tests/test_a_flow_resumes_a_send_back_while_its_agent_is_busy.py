"""F1171 (AW-123) — a flow fires for a sent-back task while its job's agent is busy.

**The defect.** `_loop_flow_busy_refusal` refuses a flow's whole firing when the job's agent is
running and `_agents_a_loop_may_staff` is empty. That pool is `_agents_that_are_free`'s, which
counts an agent holding a live task in a live loop as not free -- including a task in *this* loop,
the very one this firing would resume. Seen live 2026-11-13: QA2's flow had one task, sent back to
Developer at landing; Developer was idle, QA2 was mid-review, and every tick was refused with no
record until QA2 went idle.

**The rule now.** The busy guard also proceeds when an open task in this loop is held by an idle
assignee the walk would resume: not running, not held, with a runner, and holding nothing another
loop or a queued turn will move. A holding in this loop does not count against its own resumption.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Build, JobRun, Loop, Run
from hub.scheduler import JobScheduler, _loop_flow_busy_reason, decide_firing

from .test_a_held_agent_is_busy import _hold
from .test_a_task_nothing_will_move_holds_nobody import _entries_for, _no_spawn
from .test_flow_width import _flow, _task
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

OWNER = "sendback-owner"
BUILDER = "sendback-builder"


async def _busy_flow_with_a_send_back(db, *, suffix, build_state=None):
    """A flow whose job agent is mid-turn and whose only open task came back to an idle builder."""
    job, loop = await _flow(db, suffix=suffix, agent=OWNER)
    await _task(db, loop, f"{suffix}-a", status="revision_needed", assignee=BUILDER)
    db.add(Run(id=f"run-sendback-{suffix}", project_id="proj-test", agent=OWNER, status="running"))
    if build_state is not None:
        db.add(
            Build(
                id=f"build-sendback-{suffix}",
                project_id="proj-test",
                document_id=loop.spec_document_id,
                state=build_state,
                driver="flow",
                level="build",
                builders=[BUILDER],
                reviewers=[OWNER],
                loop_id=loop.id,
            )
        )
    await db.commit()
    return job, loop


async def _guard(loop_id):
    async with async_session_factory() as db:
        loop = await db.get(Loop, loop_id)
        return await _loop_flow_busy_reason(db, loop, OWNER)


async def _fire(job_id):
    with _no_spawn():
        async with async_session_factory() as db:
            job = await db.get(AIJob, job_id)
            return await JobScheduler()._fire_job_internal(job, trigger="scheduled", session=db)


async def _job_runs(job_id):
    async with async_session_factory() as db:
        return (await db.execute(select(JobRun).where(JobRun.job_id == job_id))).scalars().all()


@pytest.mark.parametrize("build_state", [None, "running", "finished"])
async def test_a_busy_flow_briefs_the_idle_builder_of_its_send_back(
    app, auth_headers, bind_runner, build_state
):
    """The measured case: one tick briefs the builder on its own sent-back task."""
    await _roster(app, auth_headers, bind_runner, OWNER, BUILDER)
    suffix = f"sb-{build_state or 'none'}"
    async with async_session_factory() as db:
        job, loop = await _busy_flow_with_a_send_back(db, suffix=suffix, build_state=build_state)

    assert await _guard(loop.id) is None

    fired = await _fire(job.id)

    assert fired is True
    assert await _entries_for(BUILDER, task_id=f"task-width-{suffix}-a") == 1
    assert await _entries_for(OWNER) == 0
    assert len(await _job_runs(job.id)) == 1


async def test_an_assigned_task_not_yet_started_is_the_same(app, auth_headers, bind_runner):
    """The other shape the rule names: work handed to an idle agent and not yet begun."""
    await _roster(app, auth_headers, bind_runner, OWNER, BUILDER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="sb-assigned", agent=OWNER)
        await _task(db, loop, "sb-assigned-a", status="assigned", assignee=BUILDER)
        db.add(
            Run(id="run-sendback-assigned", project_id="proj-test", agent=OWNER, status="running")
        )
        await db.commit()

    assert await _guard(loop.id) is None
    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=OWNER)
    assert [(s.task.id, s.agent) for s in decision.selections] == [
        ("task-width-sb-assigned-a", BUILDER)
    ]


async def test_a_holding_in_another_live_loop_still_excludes_the_builder(
    app, auth_headers, bind_runner
):
    """The rule keeps its meaning elsewhere: another loop's walk will move that task, so the
    builder is spoken for and this firing is still refused, recording nothing."""
    await _roster(app, auth_headers, bind_runner, OWNER, BUILDER)
    async with async_session_factory() as db:
        job, loop = await _busy_flow_with_a_send_back(db, suffix="sb-other")
        _other_job, other = await _flow(db, suffix="sb-elsewhere", agent=BUILDER)
        await _task(db, other, "sb-elsewhere-a", status="in_progress", assignee=BUILDER)

    assert await _guard(loop.id) is not None
    assert await _fire(job.id) is False
    assert await _job_runs(job.id) == []
    assert await _entries_for(BUILDER, task_id="task-width-sb-other-a") == 0


async def test_a_running_builder_is_still_not_resumed(app, auth_headers, bind_runner):
    """An assignee mid-turn cannot be started again: refused, nothing recorded."""
    await _roster(app, auth_headers, bind_runner, OWNER, BUILDER)
    async with async_session_factory() as db:
        job, loop = await _busy_flow_with_a_send_back(db, suffix="sb-running")
        db.add(
            Run(id="run-sendback-builder", project_id="proj-test", agent=BUILDER, status="running")
        )
        await db.commit()

    assert await _guard(loop.id) is not None
    assert await _fire(job.id) is False
    assert await _job_runs(job.id) == []


async def test_a_held_builder_is_still_not_resumed(app, auth_headers, bind_runner):
    """A usage hold is busy for the guard exactly as a running turn is."""
    await _roster(app, auth_headers, bind_runner, OWNER, BUILDER)
    async with async_session_factory() as db:
        job, loop = await _busy_flow_with_a_send_back(db, suffix="sb-held")
    await _hold(BUILDER)

    assert await _guard(loop.id) is not None
    assert await _fire(job.id) is False
    assert await _job_runs(job.id) == []
