"""`task-dependencies` section 9 — the loop's claim must consult the dependency gate, or the
change deadlocks every loop (design D10).

Before this section, `_claim_loop_task` claimed the oldest/most-recently-active queue item without
asking whether the dependency gate (section 5) would let it start. A dependent task with an unmet
prerequisite would be claimed, then refused the moment its agent tried `-> in_progress`, and the
next firing would re-claim the very same task forever — startable work further down the queue was
never reached. These tests reproduce that failure first (9.1), then the surrounding cases (9.2-9.5,
9.9), and confirm the board's own "current item" derivation (`_batch_loop_summaries`) agrees with
the firing's (9.10).
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, Task, TaskDependency
from hub.dependency_gate import evaluate
from hub.scheduler import _claim_loop_task, _loop_stall_reason
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator

pytestmark = pytest.mark.asyncio


async def _claim_one(db, loop):
    """`loop-becomes-a-flow` group 1 made `_claim_loop_task` set-valued. These tests were written
    against the scalar it used to return and assert exactly the same facts about exactly the same
    claim; unwrapping here keeps each assertion about *the claim* rather than about its container,
    so group 1's bar -- the existing loop suite passing unmodified -- is tested rather than edited
    around.
    """
    claimed = await _claim_loop_task(db, loop)
    return claimed[0] if claimed else None


async def _make_job(db, *, suffix, agent):
    job = AIJob(
        id=f"job-depgate-{suffix}",
        project_id="proj-test",
        name=f"Test Job {suffix}",
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
    loop = Loop(id=f"loop-depgate-{job_id}", project_id="proj-test", job_id=job_id, **fields)
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


async def _depend(db, task_id, on_task_id):
    db.add(
        TaskDependency(
            id=f"tdep-{task_id}-{on_task_id}",
            project_id="proj-test",
            task_id=task_id,
            depends_on_task_id=on_task_id,
        )
    )


# ---------------------------------------------------------------------------
# 9.1 — the deadlock, reproduced first, then fixed
# ---------------------------------------------------------------------------


async def test_a_dependent_task_with_an_unapproved_prerequisite_is_never_claimed(app):
    """Task A -> B, A unapproved: B must not be claimed, on this firing or the next.

    Reproduces the deadlock shape from `openspec/explorations/2026-08-20-the-loop-under-
    dependencies.md` §2: without a gate-aware claim, this exact setup claims B, the agent's
    attempted `-> in_progress` is refused, and the next firing re-claims the same B forever.

    `dependent_b` is created BEFORE `prereq_a` deliberately: `_loop_queue_order` breaks ties among
    pending tasks by `created_at.asc()`, so a naive claim (no gate check) would pick the *older*
    task regardless of the edge between them. Mutation-checked directly against the pre-section-9
    `_claim_loop_task` (a plain `.limit(1)` over `_loop_queue_order()` with no gate check): with
    this ordering it claims `dependent_b`, exactly the deadlock this test exists to catch. An
    earlier draft of this test happened to create the prerequisite first, which passed against the
    old code by coincidence of insertion order rather than by exercising the gate at all.
    """
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="9-1", agent="loop-agent-9-1")
        loop = await _make_loop(db, job_id=job.id, purpose="deadlock check")
        dependent_b = await _make_task(db, "task-9-1-b", status="pending", loop_id=loop.id)
        prereq_a = await _make_task(db, "task-9-1-a", status="pending", loop_id=loop.id)
        await _depend(db, dependent_b.id, prereq_a.id)
        await db.commit()

    async with async_session_factory() as db:
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        # B is gated behind A, so A — not B — is what the claim must return.
        claimed = await _claim_one(db, fresh_loop)
        assert claimed is not None
        assert claimed.id == prereq_a.id

    # And firing again after "claiming" A (still pending, nothing changed) must not suddenly
    # surface B either — the gate's answer does not depend on how many times it is asked.
    async with async_session_factory() as db:
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        claimed_again = await _claim_one(db, fresh_loop)
        assert claimed_again.id == prereq_a.id


# ---------------------------------------------------------------------------
# 9.2 — an older gated task is skipped for a newer startable one
# ---------------------------------------------------------------------------


async def test_an_older_gated_task_is_skipped_for_a_newer_startable_one(app):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="9-2", agent="loop-agent-9-2")
        loop = await _make_loop(db, job_id=job.id, purpose="skip the gated one")
        # Outside the loop's own queue, so it does not itself compete in `_loop_queue_order` --
        # only its `pending` status (unapproved) is what makes `older_gated` gated.
        prereq = await _make_task(db, "task-9-2-prereq", status="pending", loop_id=None)
        older_gated = await _make_task(
            db,
            "task-9-2-older-gated",
            status="pending",
            loop_id=loop.id,
            created_at=now - timedelta(minutes=10),
        )
        newer_startable = await _make_task(
            db,
            "task-9-2-newer-startable",
            status="pending",
            loop_id=loop.id,
            created_at=now - timedelta(minutes=1),
        )
        await _depend(db, older_gated.id, prereq.id)
        await db.commit()

    async with async_session_factory() as db:
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        claimed = await _claim_one(db, fresh_loop)
        assert claimed.id == newer_startable.id

    async with async_session_factory() as db:
        older = await db.get(Task, "task-9-2-older-gated")
        assert older.status == "pending"
        assert older.assignee is None


# ---------------------------------------------------------------------------
# 9.3 — every candidate gated: claims nothing, no stop reason
# ---------------------------------------------------------------------------


async def test_a_queue_where_every_task_is_gated_claims_nothing_and_stays_enabled(app):
    from hub.scheduler import _loop_stop_reason

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="9-3", agent="loop-agent-9-3")
        loop = await _make_loop(
            db, job_id=job.id, purpose="all gated", stop_when_queue_empties=True
        )
        prereq = await _make_task(db, "task-9-3-prereq", status="pending", loop_id=loop.id)
        gated = await _make_task(db, "task-9-3-gated", status="pending", loop_id=loop.id)
        await _depend(db, gated.id, prereq.id)
        # prereq itself has no dependency, so it is what gets claimed -- to make the whole queue
        # gated, also gate the prerequisite behind a third, rejected task (permanently unmet).
        blocker = await _make_task(db, "task-9-3-blocker", status="rejected", loop_id=loop.id)
        await _depend(db, prereq.id, blocker.id)
        await db.commit()

    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        assert await _claim_one(db, fresh_loop) is None
        # Gated, not drained -- the job must not be stopped over this.
        assert await _loop_stop_reason(db, fresh_job) is None
        stall = await _loop_stall_reason(db, fresh_loop)
        assert stall is not None
        assert "gated on a rejected prerequisite" in stall


# ---------------------------------------------------------------------------
# 9.4 — approving the prerequisite makes the gated task claimable, no other action
# ---------------------------------------------------------------------------


async def test_approving_the_prerequisite_makes_the_dependent_claimable(app):
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="9-4", agent="loop-agent-9-4")
        loop = await _make_loop(db, job_id=job.id, purpose="clears once approved")
        prereq = await _make_task(db, "task-9-4-prereq", status="pending", loop_id=loop.id)
        dependent = await _make_task(db, "task-9-4-dependent", status="pending", loop_id=loop.id)
        await _depend(db, dependent.id, prereq.id)
        await db.commit()

    async with async_session_factory() as db:
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        claimed = await _claim_one(db, fresh_loop)
        assert claimed.id == prereq.id

    # Walk the prerequisite all the way to approved -- no action on the dependent at all.
    async with async_session_factory() as db:
        prereq_row = await db.get(Task, "task-9-4-prereq")
        for target in ("in_progress", "completed", "under_review", "approved"):
            await apply_transition(db, prereq_row, target, operator())
        await db.commit()

    async with async_session_factory() as db:
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        claimed = await _claim_one(db, fresh_loop)
        assert claimed.id == "task-9-4-dependent"


# ---------------------------------------------------------------------------
# 9.5 — the agreement, asserted directly: what the claim returns, the gate accepts
# ---------------------------------------------------------------------------


async def test_every_claimed_task_would_be_accepted_by_the_dependency_gate(app):
    """The whole property in one assertion, rather than inferred from the surrounding cases: for
    any queue shape, whatever `_claim_loop_task` hands back is a task the gate would let move to
    `in_progress` (or one already running, which needs no fresh check)."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="9-5", agent="loop-agent-9-5")
        loop = await _make_loop(db, job_id=job.id, purpose="agreement")
        blocker = await _make_task(db, "task-9-5-blocker", status="pending", loop_id=loop.id)
        gated = await _make_task(db, "task-9-5-gated", status="pending", loop_id=loop.id)
        await _make_task(db, "task-9-5-startable", status="pending", loop_id=loop.id)
        await _depend(db, gated.id, blocker.id)
        await db.commit()

    async with async_session_factory() as db:
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        claimed = await _claim_one(db, fresh_loop)
        assert claimed is not None
        if claimed.status != "in_progress":
            refusal = await evaluate(db, claimed)
            assert not refusal.refuses


# ---------------------------------------------------------------------------
# 9.9 — a rejected-gated queue does not stop, and reversing the rejection revives it
# ---------------------------------------------------------------------------


async def test_reversing_a_rejection_revives_a_stalled_loop_with_no_further_action(app):
    from hub.scheduler import _loop_stop_reason

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="9-9", agent="loop-agent-9-9")
        loop = await _make_loop(
            db, job_id=job.id, purpose="revive after reopening", stop_when_queue_empties=True
        )
        prereq = await _make_task(db, "task-9-9-prereq", status="rejected", loop_id=loop.id)
        dependent = await _make_task(db, "task-9-9-dependent", status="pending", loop_id=loop.id)
        await _depend(db, dependent.id, prereq.id)
        await db.commit()

    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        assert await _claim_one(db, fresh_loop) is None
        assert await _loop_stop_reason(db, fresh_job) is None
        stall = await _loop_stall_reason(db, fresh_loop)
        assert stall is not None and "rejected" in stall

    # The operator's only way back: reopen the rejected prerequisite to pending. No action at all
    # on the dependent task.
    async with async_session_factory() as db:
        prereq_row = await db.get(Task, "task-9-9-prereq")
        prereq_row.status = "pending"
        await db.commit()

    async with async_session_factory() as db:
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        claimed = await _claim_one(db, fresh_loop)
        assert claimed is not None
        assert claimed.id == "task-9-9-prereq"


# ---------------------------------------------------------------------------
# 9.10 — the board's derivation agrees with the firing's, for a gated queue
# ---------------------------------------------------------------------------


async def test_the_board_summary_agrees_with_the_firing_for_a_gated_queue(app):
    """`_batch_loop_summaries`'s `current_task` must name the same task `_claim_loop_task` would
    claim, even when the queue's oldest candidate is gated — the same property human-only check
    13.1 already covers for plain ordering, now with a dependency in the queue."""
    from hub.api.v1.jobs import _batch_loop_summaries

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="9-10", agent="loop-agent-9-10")
        loop = await _make_loop(db, job_id=job.id, purpose="board agrees")
        blocker = await _make_task(db, "task-9-10-blocker", status="pending", loop_id=loop.id)
        gated = await _make_task(db, "task-9-10-gated", status="pending", loop_id=loop.id)
        await _depend(db, gated.id, blocker.id)
        await db.commit()

    async with async_session_factory() as db:
        fresh_loop = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalar_one()
        claimed = await _claim_one(db, fresh_loop)

        summaries = await _batch_loop_summaries(db, [job.id])
        # `loop-becomes-a-flow` task 1.5: a list holding the one current item.
        current = summaries[job.id].current_tasks[0]
        assert current is not None
        assert current["id"] == claimed.id == blocker.id
