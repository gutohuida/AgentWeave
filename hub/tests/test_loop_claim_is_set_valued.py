"""`loop-becomes-a-flow` group 1 — the claim becomes set-valued, and nothing else moves.

A flow may staff several tasks at once; a loop staffs one. Group 1 changes only the *shape* of
the answer, never the answer itself: `_claim_loop_task` returns a collection, and for every case
that exists today that collection holds exactly the task the single-valued version returned.

The bar for this group is stated in `tasks.md` 1.1 — the existing loop suite passes unmodified.
These tests are the narrower complement: they pin the shape, the ordering, and the three cases
1.2 names (pending, resuming, empty), so that a later group widening the selection cannot quietly
change what a *single*-selection loop does. That equivalence is both the migration story and the
regression bar (proposal, "What Changes").

**Ordering is asserted deliberately, and it is why the return is a list rather than a Python
`set`.** `tasks.md` 1.3 says "set", meaning set-valued as opposed to scalar. Taken as the type it
would be wrong: iteration order over a `set` of ORM rows follows identity hashes, so a width-2
flow would hand task and agent to each other in an order that varies run to run — and the
proposal requires a firing to select "a task and an agent, both deterministically". The queue
order (`_loop_queue_order`) is the determinism, so the collection has to keep it.
"""

import pytest
from sqlalchemy import select

from hub.checkpoints import latest_checkpoint_for_loop
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, Task
from hub.scheduler import _claim_loop_task, _compose_loop_briefing

pytestmark = pytest.mark.asyncio


async def _make_job(db, *, suffix, agent="loop-agent"):
    job = AIJob(
        id=f"job-setclaim-{suffix}",
        project_id="proj-test",
        name=f"Set Claim {suffix}",
        agent=agent,
        message="hello from a scheduled job",
        cron="0 9 * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    return job


async def _make_loop(db, *, job_id, **fields):
    loop = Loop(id=f"loop-setclaim-{job_id}", project_id="proj-test", job_id=job_id, **fields)
    db.add(loop)
    await db.commit()
    return loop


async def _make_task(db, task_id, *, status, loop_id, created_at=None):
    task = Task(
        id=task_id,
        project_id="proj-test",
        title=task_id,
        status=status,
        loop_id=loop_id,
        **({"created_at": created_at} if created_at is not None else {}),
    )
    db.add(task)
    await db.flush()
    return task


async def _fresh_loop(db, job_id):
    return (await db.execute(select(Loop).where(Loop.job_id == job_id))).scalar_one()


# ---------------------------------------------------------------------------
# 1.2 — the three cases that exist today, each returning a collection of one
# ---------------------------------------------------------------------------


async def test_a_pending_queue_claims_a_collection_holding_exactly_that_task(app):
    """The `pending` case: one startable task, claimed, and nothing else in the answer."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="pending")
        loop = await _make_loop(db, job_id=job.id, purpose="a pending queue")
        await _make_task(db, "task-setclaim-pending", status="pending", loop_id=loop.id)
        await db.commit()

    async with async_session_factory() as db:
        claimed = await _claim_loop_task(db, await _fresh_loop(db, job.id), agent="claim-probe")
        assert [task.id for task in claimed] == ["task-setclaim-pending"]


async def test_a_resuming_queue_claims_the_active_task_and_leaves_its_status_alone(app):
    """The resume case: `in_progress` is returned as-is, and `_claim_loop_task` does not transition
    it. Only `_do_fire_job` transitions, and only a `pending` task (design D3)."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="resuming")
        loop = await _make_loop(db, job_id=job.id, purpose="a resuming queue")
        await _make_task(db, "task-setclaim-active", status="in_progress", loop_id=loop.id)
        await _make_task(db, "task-setclaim-waiting", status="pending", loop_id=loop.id)
        await db.commit()

    async with async_session_factory() as db:
        claimed = await _claim_loop_task(db, await _fresh_loop(db, job.id), agent="claim-probe")
        assert [task.id for task in claimed] == ["task-setclaim-active"]
        assert claimed[0].status == "in_progress"


async def test_an_empty_queue_claims_an_empty_collection_not_a_none(app):
    """The empty case. The distinction matters to every caller: `if not claimed` has to keep
    meaning "nothing to work on" once the answer is a collection, and a `None` would make an
    innocent `len()` or iteration raise instead."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="empty")
        await _make_loop(db, job_id=job.id, purpose="an empty queue")

    async with async_session_factory() as db:
        claimed = await _claim_loop_task(db, await _fresh_loop(db, job.id), agent="claim-probe")
        assert claimed == []
        assert len(claimed) == 0


async def test_a_queue_of_many_still_claims_one_in_this_group(app):
    """Width arrives in group 5, not here. Until then a queue offering several startable tasks
    must still yield exactly one, or group 1 has smuggled in the behaviour change it exists to
    avoid."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="many")
        loop = await _make_loop(db, job_id=job.id, purpose="several startable tasks")
        await _make_task(db, "task-setclaim-1", status="pending", loop_id=loop.id)
        await _make_task(db, "task-setclaim-2", status="pending", loop_id=loop.id)
        await _make_task(db, "task-setclaim-3", status="pending", loop_id=loop.id)
        await db.commit()

    async with async_session_factory() as db:
        claimed = await _claim_loop_task(db, await _fresh_loop(db, job.id), agent="claim-probe")
        assert len(claimed) == 1


async def test_the_claim_is_ordered_and_repeatable(app):
    """The determinism the proposal requires of a firing. Asked twice against unchanged state, the
    claim answers the same thing in the same order — which a Python `set` of ORM rows would not
    guarantee once the collection holds more than one."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="ordered")
        loop = await _make_loop(db, job_id=job.id, purpose="determinism")
        await _make_task(db, "task-setclaim-o1", status="pending", loop_id=loop.id)
        await _make_task(db, "task-setclaim-o2", status="pending", loop_id=loop.id)
        await db.commit()

    async with async_session_factory() as db:
        first = [
            task.id
            for task in await _claim_loop_task(
                db, await _fresh_loop(db, job.id), agent="claim-probe"
            )
        ]
    async with async_session_factory() as db:
        second = [
            task.id
            for task in await _claim_loop_task(
                db, await _fresh_loop(db, job.id), agent="claim-probe"
            )
        ]

    assert first == second
    assert isinstance(first, list)


# ---------------------------------------------------------------------------
# 1.2 — the briefing a collection of one composes is the briefing composed today
# ---------------------------------------------------------------------------


async def test_the_briefing_for_a_collection_of_one_is_unchanged(app):
    """`_compose_loop_briefing` still takes the single claimed task. Group 1 does not touch it, and
    this test is what will notice if a later group changes a *single*-selection briefing while
    reaching for a multi-selection one — task 8.2's regression, caught one group early."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="briefing")
        loop = await _make_loop(db, job_id=job.id, purpose="brief me")
        await _make_task(db, "task-setclaim-brief", status="pending", loop_id=loop.id)
        await db.commit()

    async with async_session_factory() as db:
        fresh_loop = await _fresh_loop(db, job.id)
        claimed = await _claim_loop_task(db, fresh_loop, agent="claim-probe")
        prior = await latest_checkpoint_for_loop(db, fresh_loop.id)
        briefing = await _compose_loop_briefing(db, fresh_loop, claimed[0], prior, is_review=False)

    assert briefing.startswith("# Loop briefing")
    assert "Purpose: brief me" in briefing
    assert "## Current task: task-setclaim-brief" in briefing
