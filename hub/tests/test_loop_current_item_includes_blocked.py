"""`agent-loops` §85 — a blocked task is the loop's current item.

**This covers a defect that shipped and was live until 2026-08-24.** §85's second scenario says
*"WHEN a loop's queue holds a task that is in progress or blocked / THEN that task is the loop's
current item"*. On 2026-08-21 `blocked` left `CLAIMABLE_LOOP_TASK_STATUSES`, correctly — a firing
that claims a blocked task spawns an agent every tick against work that cannot move. But
`_batch_loop_summaries` was using that same constant to answer a different question, so the board
lost sight of blocked tasks at the same moment. A loop parked on an unanswered question reported
`queue: {blocked: 1}` and **no current item**: the surface whose whole job is to say what the loop
is waiting for said nothing was happening.

Nothing caught it because no test covered this scenario — the reason it is written now, before the
`loop-notices-and-reacts` vocabulary work refactors these sets. When the bands land,
`CURRENT_ITEM_TASK_STATUSES` should be derived from them and these assertions must still hold.

The three scenarios below are §85's three, in its order.
"""

import pytest
from sqlalchemy import select

from hub.api.v1.jobs import _batch_loop_summaries
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, Task
from hub.scheduler import (
    CLAIMABLE_LOOP_TASK_STATUSES,
    CURRENT_ITEM_TASK_STATUSES,
    REVIEWABLE_LOOP_TASK_STATUSES,
    _claim_loop_task,
)

pytestmark = pytest.mark.asyncio


async def _loop_with(db, suffix, tasks):
    job = AIJob(
        id=f"job-blk-{suffix}",
        project_id="proj-test",
        name=f"Blocked {suffix}",
        agent="loop-agent",
        message="hello",
        cron="0 9 * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(id=f"loop-blk-{suffix}", project_id="proj-test", job_id=job.id, purpose=suffix)
    db.add(loop)
    await db.commit()
    for task_id, status in tasks:
        db.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title=task_id,
                status=status,
                loop_id=loop.id,
                **({"blocked_reason": "needs the API key"} if status == "blocked" else {}),
            )
        )
    await db.commit()
    return job, loop


async def _current(db, job_id):
    summaries = await _batch_loop_summaries(db, [job_id])
    return summaries[job_id].current_tasks


async def test_a_blocked_task_is_the_loops_current_item(app):
    """§85 scenario 2, and the exact shape of the defect: a queue holding only a blocked task."""
    async with async_session_factory() as db:
        job, _ = await _loop_with(db, "only", [("task-blk-only", "blocked")])

    async with async_session_factory() as db:
        current = await _current(db, job.id)

    assert [t["id"] for t in current] == ["task-blk-only"]
    assert current[0]["status"] == "blocked"


async def test_a_blocked_task_outranks_a_pending_one(app):
    """§85 orders in-progress-or-blocked ahead of the oldest pending. The pending task is created
    first, so an ordering that ignored status would pick it."""
    async with async_session_factory() as db:
        job, _ = await _loop_with(
            db, "order", [("task-blk-pending", "pending"), ("task-blk-blocked", "blocked")]
        )

    async with async_session_factory() as db:
        current = await _current(db, job.id)

    assert [t["id"] for t in current] == ["task-blk-blocked"]


async def test_a_queue_of_only_terminal_work_has_no_current_item(app):
    """§85 scenario 3: no in-progress, blocked or pending task means no current item. Guards the
    fix from over-reaching — widening the board's set must not make everything current."""
    async with async_session_factory() as db:
        job, _ = await _loop_with(
            db, "none", [("task-blk-done", "approved"), ("task-blk-rej", "rejected")]
        )

    async with async_session_factory() as db:
        assert await _current(db, job.id) == []


async def test_the_firing_still_refuses_to_claim_a_blocked_task(app):
    """The other half, and the reason these are two sets rather than one.

    The board showing a blocked task must not put it back within reach of the claim: claiming it
    is what produced the 2026-08-20 spin, where a firing spawned an agent every tick against work
    that could not move. This asserts the split holds in the direction that is easy to lose.
    """
    async with async_session_factory() as db:
        job, _ = await _loop_with(db, "claim", [("task-blk-claim", "blocked")])

    async with async_session_factory() as db:
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        assert await _claim_loop_task(db, fresh_loop, agent="claim-probe") == []


async def test_the_two_sets_differ_only_by_blocked(app):
    """Pins the relationship rather than either literal, so the vocabulary refactor can change how
    both are derived without this test having to be rewritten — it only has to keep being true.

    Async purely to sit under this module's `pytestmark`; it touches no database.
    """
    assert set(CURRENT_ITEM_TASK_STATUSES) - set(CLAIMABLE_LOOP_TASK_STATUSES) == {
        "blocked",
        "completed",
    }
    assert set(CLAIMABLE_LOOP_TASK_STATUSES) - set(CURRENT_ITEM_TASK_STATUSES) == set()
    # `completed` is the reviewable set entire, and it is in current-item without being in the
    # claim for the opposite reason `blocked` is: not "no firing may take this", but "only a
    # firing by somebody else may". The claim tuple stays actor-blind and stays without it
    # (`loop-becomes-a-flow` task 3.3); `task_is_claimable_by` is where the actor enters.
    assert set(REVIEWABLE_LOOP_TASK_STATUSES) == {"completed"}
    assert set(REVIEWABLE_LOOP_TASK_STATUSES) & set(CLAIMABLE_LOOP_TASK_STATUSES) == set()
