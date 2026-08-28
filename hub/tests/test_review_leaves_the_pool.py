"""Finding F45 — a dispatched review takes the task out of the reviewable pool.

**The defect this pins.** `decide_firing`'s ordinary-work arm checks `task.assignee`, so a task
already staffed is *resumed* rather than re-staffed. The finished-work arm had no equivalent: it
resolved the author, walked the reviewer ladder, and selected, with nothing anywhere asking whether
this task had already been reviewed. The task's own status was meant to be that marker — a reviewer
is expected to move `completed -> under_review` — and nothing enforced it or noticed when it did
not happen.

Measured live before the fix, on the trial Hub: `critic` was staffed to review
`task-23a0986e7fe9`, ran to completion, wrote a note recording its verdict, and moved the task
nowhere. The task stayed `completed`, which is exactly `REVIEWABLE_STATUSES`, so the ladder
resolved `critic` for it again — and the board was already displaying that decision. Nothing could
end it: `stop_when_queue_empties` never fires while a non-terminal task sits in the queue, and the
project had no token budget. Every tick looked healthy.

The second half of the same defect is why no reviewer ever transitioned. `TRANSITIONS` offers
`completed` exactly one agent-legal edge — `under_review` — while the review turn's own context
told the reviewer to report through `revision_needed`, which is not reachable from `completed`. A
reviewer that followed the instruction was refused; one that found the work correct had no stated
exit at all. Across this Hub's whole history no flow-dispatched review had recorded a single
transition.

Both halves close the same way: the firing enters the review at `under_review`, so the task leaves
the pool and both verdict edges become legal.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, Task
from hub.scheduler import (
    DECISION_CLAIM,
    REVIEWABLE_LOOP_TASK_STATUSES,
    WITH_REVIEWER_LOOP_TASK_STATUSES,
    decide_firing,
    enter_selected_task,
)
from hub.task_transition_service import apply_transition
from hub.task_transitions import TRANSITIONS, run_actor

from .review_evidence import record_review_evidence
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

AUTHOR = "f45-author"
REVIEWER = "f45-reviewer"


async def _loop_with_task(db, *, suffix):
    job = AIJob(
        id=f"job-f45-{suffix}",
        project_id="proj-test",
        name=f"F45 {suffix}",
        agent=AUTHOR,
        message="work the queue",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(
        id=f"loop-f45-{suffix}", project_id="proj-test", job_id=job.id, purpose=f"f45 {suffix}"
    )
    db.add(loop)
    await db.commit()
    task = Task(
        id=f"task-f45-{suffix}",
        project_id="proj-test",
        title=f"work {suffix}",
        status="pending",
        loop_id=loop.id,
    )
    db.add(task)
    await db.commit()
    return job, loop, task


async def _completed_by(db, task, agent):
    """Walk the task to `completed` through the transition machine, as `agent`.

    Never constructed directly: `_agent_that_completed` reads the history, so a row built at
    `completed` would leave the author unknown and the reviewer ladder would decline to staff
    anybody — the test would pass while proving nothing.
    """
    actor = run_actor(run_id=f"run-{agent}-{task.id}", agent=agent)
    for status in ("assigned", "in_progress", "completed"):
        await apply_transition(db, task, status, actor)
    await db.commit()
    return task


async def _fresh_loop(db, loop_id):
    return (await db.execute(select(Loop).where(Loop.id == loop_id))).scalar_one()


async def _fresh_task(db, task_id):
    return (await db.execute(select(Task).where(Task.id == task_id))).scalar_one()


# ---------------------------------------------------------------------------
# The status sets themselves
# ---------------------------------------------------------------------------


async def test_with_reviewer_and_reviewable_are_disjoint():
    """The whole mechanism rests on this: entering a review must *remove* the task from the set the
    ladder draws from. If these ever overlap, the fix silently stops working."""
    assert set(WITH_REVIEWER_LOOP_TASK_STATUSES).isdisjoint(REVIEWABLE_LOOP_TASK_STATUSES)
    assert "under_review" in WITH_REVIEWER_LOOP_TASK_STATUSES
    assert "completed" in REVIEWABLE_LOOP_TASK_STATUSES


async def test_a_review_verdict_is_reachable_only_from_under_review():
    """The second half of F45, asserted against the transition table directly.

    `revision_needed` — the edge the review context names — is not reachable from `completed`. This
    is why entering the review at `under_review` is what makes the instruction true, rather than a
    wording change being enough.
    """
    assert set(TRANSITIONS["completed"]) == {"under_review", "rejected"}
    assert "revision_needed" not in TRANSITIONS["completed"]
    assert {"approved", "revision_needed"} <= set(TRANSITIONS["under_review"])


# ---------------------------------------------------------------------------
# Entering the task
# ---------------------------------------------------------------------------


async def test_entering_a_review_moves_the_task_out_of_the_pool(app):
    async with async_session_factory() as db:
        _job, _loop, task = await _loop_with_task(db, suffix="enter")
        await _completed_by(db, task, AUTHOR)
        await enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await db.commit()

    async with async_session_factory() as db:
        moved = await _fresh_task(db, task.id)
        assert moved.status == "under_review"
        assert moved.assignee == REVIEWER


async def test_entering_ordinary_work_is_unchanged(app):
    """The other half of `enter_selected_task` must keep behaving exactly as it did — this is the
    path every non-flow loop in the product takes."""
    async with async_session_factory() as db:
        _job, _loop, task = await _loop_with_task(db, suffix="ordinary")
        await enter_selected_task(db, task, agent=AUTHOR, is_review=False)
        await db.commit()

    async with async_session_factory() as db:
        moved = await _fresh_task(db, task.id)
        assert moved.status == "assigned"
        assert moved.assignee == AUTHOR


async def test_entering_a_review_twice_is_not_an_illegal_transition(app):
    """Reachable when an entry is queued but its turn never starts and the firing re-stages the
    selection. `under_review -> under_review` is not an edge, so this must be a no-op rather than
    a refusal that takes the firing down with it."""
    async with async_session_factory() as db:
        _job, _loop, task = await _loop_with_task(db, suffix="twice")
        await _completed_by(db, task, AUTHOR)
        await enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await db.commit()

    async with async_session_factory() as db:
        assert (await _fresh_task(db, task.id)).status == "under_review"


# ---------------------------------------------------------------------------
# The firing decision — the loop F45 actually was
# ---------------------------------------------------------------------------


async def test_a_review_in_flight_is_not_staffed_again(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    """The regression itself. Before the fix this returned a fresh review selection on every call,
    which is what made it a spend loop with no stop condition."""
    async with async_session_factory() as db:
        job, loop, task = await _loop_with_task(db, suffix="restaff")
        await _completed_by(db, task, AUTHOR)
        # The firing only staffs a review it could provision, so the task needs a commit before
        # "staffed once, not twice" is a question that can be asked of it at all.
        await record_review_evidence(db, task.id, suffix="f45-restaff", actor=AUTHOR)

        first = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)
        assert first.kind == DECISION_CLAIM
        assert [(s.task.id, s.agent, s.is_review) for s in first.selections] == [
            (task.id, REVIEWER, True)
        ], "the ladder should staff the non-author for the review"

        await enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await db.commit()

    async with async_session_factory() as db:
        again = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)
        assert again.selections == (), "a review already in flight must not be staffed again"


async def test_a_review_in_flight_still_appears_on_the_board(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    """Finding F23's rule, applied to the new branch. Removing the row instead of recording it
    would make a flow whose reviews are all running read as having nothing to do — and would hide
    a review that ended without a verdict, which is the state F45 leaves behind."""
    async with async_session_factory() as db:
        job, loop, task = await _loop_with_task(db, suffix="board")
        await _completed_by(db, task, AUTHOR)
        await enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await db.commit()

    async with async_session_factory() as db:
        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)
        assert (task.id, REVIEWER) in decision._cannot_staff
        assert decision.selections == ()


async def test_a_review_in_flight_is_never_restaffed_as_ordinary_work(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    """`under_review` is absent from `REVIEWABLE_LOOP_TASK_STATUSES`, so without an explicit branch
    the walk falls into the *ordinary work* arm, finds the reviewer in `assignee`, and re-fires it
    with no `is_review` — which means no checkout of the commit under review. That is finding F10
    arriving by a new route, and it is a worse outcome than the loop this change set out to fix.
    """
    async with async_session_factory() as db:
        job, loop, task = await _loop_with_task(db, suffix="notordinary")
        await _completed_by(db, task, AUTHOR)
        await enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await db.commit()

    async with async_session_factory() as db:
        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)
        assert all(
            s.task.id != task.id for s in decision.selections
        ), "the task must not be selected at all, as review or as ordinary work"


async def test_the_author_still_cannot_be_staffed_for_its_own_review(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    """Unchanged by this fix, and asserted here because `enter_selected_task` now writes an
    assignee onto finished work — which must not become a route back to the author."""
    async with async_session_factory() as db:
        job, loop, task = await _loop_with_task(db, suffix="author")
        await _completed_by(db, task, AUTHOR)

    async with async_session_factory() as db:
        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)
        assert all(s.agent != AUTHOR for s in decision.selections)
