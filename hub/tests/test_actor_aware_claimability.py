"""`loop-becomes-a-flow` group 3 — claimability becomes a question about *(task, agent)*.

Design D3. A task in `completed` is claimable by an agent that did not complete it, and that is the
entire review mechanism: no handoff message the finishing agent could forget to send, no review task
row whose own completion would need reviewing, nothing asked of the author at all.

**The property that matters is not "completed became claimable".** It is that the set of tasks the
Hub offers an agent and the set that agent is permitted to sign off are the same set. Two
implementations of "who finished this" would be free to drift apart into a loop that fires an agent
at work it is structurally unable to approve — forever, since the refusal changes nothing about the
queue. So `task_is_claimable_by` calls `_agent_that_completed`, the same determination
`_guard_author_is_not_reviewer` reads, and `test_every_offered_task_can_be_carried_to_a_review_outcome`
below asserts the property directly rather than inferring it from the cases either side of it.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, Task
from hub.scheduler import (
    CLAIMABLE_LOOP_TASK_STATUSES,
    REVIEWABLE_LOOP_TASK_STATUSES,
    _claim_loop_task,
    task_is_claimable_by,
)
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

pytestmark = pytest.mark.asyncio

AUTHOR = "flow-author"
REVIEWER = "flow-reviewer"


async def _loop_with_one_task(db, *, suffix, status="pending"):
    job = AIJob(
        id=f"job-actor-{suffix}",
        project_id="proj-test",
        name=f"Actor {suffix}",
        agent=AUTHOR,
        message="work the queue",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(
        id=f"loop-actor-{suffix}", project_id="proj-test", job_id=job.id, purpose=f"actor {suffix}"
    )
    db.add(loop)
    await db.commit()
    task = Task(
        id=f"task-actor-{suffix}",
        project_id="proj-test",
        title=f"work {suffix}",
        status=status,
        loop_id=loop.id,
    )
    db.add(task)
    await db.commit()
    return job, loop, task


async def _completed_by(db, task, agent):
    """Walk a task to `completed` *through the transition machine*, as `agent`.

    Constructing the row at `completed` directly is what most of the older loop tests do, and it is
    exactly wrong here: it leaves no `TaskTransition`, so `_agent_that_completed` answers `None` and
    every one of these tests would pass for the wrong reason. The history row is the fact under
    test.
    """
    actor = run_actor(run_id=f"run-{agent}-{task.id}", agent=agent)
    for status in ("assigned", "in_progress", "completed"):
        if task.status != status:
            await apply_transition(db, task, status, actor)
    await db.commit()
    return task


async def _fresh(db, loop_id):
    return (await db.execute(select(Loop).where(Loop.id == loop_id))).scalar_one()


# ---------------------------------------------------------------------------
# 3.1 — offered to an agent that did not complete it, and not to the one that did
# ---------------------------------------------------------------------------


async def test_a_completed_task_is_offered_to_an_agent_that_did_not_complete_it(app):
    async with async_session_factory() as db:
        _job, loop, task = await _loop_with_one_task(db, suffix="offered")
        await _completed_by(db, task, AUTHOR)

    async with async_session_factory() as db:
        claimed = await _claim_loop_task(db, await _fresh(db, loop.id), agent=REVIEWER)
        assert [t.id for t in claimed] == [task.id]


async def test_a_completed_task_is_not_offered_to_the_agent_that_completed_it(app):
    """The author cannot take its own finished work back, and the queue reads as having nothing
    for it — which is the same answer it gave before this group existed, and is what keeps a
    single-agent loop's behaviour unchanged by the widening."""
    async with async_session_factory() as db:
        _job, loop, task = await _loop_with_one_task(db, suffix="author")
        await _completed_by(db, task, AUTHOR)

    async with async_session_factory() as db:
        assert await _claim_loop_task(db, await _fresh(db, loop.id), agent=AUTHOR) == []


async def test_the_two_answers_come_from_one_queue_and_differ_only_by_who_asks(app):
    """Same task, same instant, two agents, two answers. The point of D3 stated as a single
    assertion: nothing about the *task* decides this."""
    async with async_session_factory() as db:
        _job, loop, task = await _loop_with_one_task(db, suffix="both")
        await _completed_by(db, task, AUTHOR)

    async with async_session_factory() as db:
        fresh_task = await db.get(Task, task.id)
        assert await task_is_claimable_by(db, fresh_task, REVIEWER) is True
        assert await task_is_claimable_by(db, fresh_task, AUTHOR) is False


async def test_a_completed_task_with_no_recorded_completer_is_offered_to_nobody(app):
    """Constructed at `completed` with no history — a task from before the transition table, or one
    written straight into the status.

    **The one place claimability deliberately disagrees with the guard**, and the reason is that
    they are different kinds of decision. `_guard_author_is_not_reviewer` permits an unattributable
    move, which is right for a refusal: blocking every action it could not attribute would stop
    legitimate work over a missing row. Offering is the opposite case. Hand this task to an agent
    the Hub cannot rule out as its author, and the guard will then also fail to rule it out — two
    permissive defaults agreeing is author/reviewer separation bypassed entirely, for exactly the
    tasks whose provenance is unknown.

    Refuse to offer, permit to act. The cost is that such a task stalls the queue for the operator
    to review, which is what happens today.

    The first implementation had this the other way round, on the argument that the guard permits.
    `test_scheduler.py`'s spin test found it as a hang — the firing claimed a directly-constructed
    completed task and spawned an agent the fixture had no reads queued for.
    """
    async with async_session_factory() as db:
        _job, loop, task = await _loop_with_one_task(db, suffix="nohistory", status="completed")

    async with async_session_factory() as db:
        fresh_task = await db.get(Task, task.id)
        assert await task_is_claimable_by(db, fresh_task, AUTHOR) is False
        assert await task_is_claimable_by(db, fresh_task, REVIEWER) is False
        assert await _claim_loop_task(db, await _fresh(db, loop.id), agent=REVIEWER) == []


async def test_the_guard_still_permits_what_the_queue_will_not_offer(app):
    """The asymmetry asserted from both sides at once, so that "make them consistent" has to
    confront what consistency would cost.

    An operator — or an agent acting on a task it reached some other way — may still approve work
    whose completer is unrecorded. Only the *offer* is withheld.
    """
    from hub.task_transitions import operator

    async with async_session_factory() as db:
        _job, _loop, task = await _loop_with_one_task(db, suffix="guardgap", status="completed")

    async with async_session_factory() as db:
        unattributed = await db.get(Task, task.id)
        assert await task_is_claimable_by(db, unattributed, REVIEWER) is False
        await apply_transition(db, unattributed, "under_review", operator())
        await apply_transition(db, unattributed, "approved", operator())
        await db.commit()
        assert (await db.get(Task, task.id)).status == "approved"


# ---------------------------------------------------------------------------
# 3.2 — the correctness property, asserted rather than inferred
# ---------------------------------------------------------------------------


async def test_every_offered_task_can_be_carried_to_a_review_outcome(app):
    """Design D3's actual requirement: a task the Hub offers an agent is never one that agent is
    then refused for approving.

    Driven end to end rather than by comparing two functions' return values — the offer comes from
    the claim, and the permission from `apply_transition` itself raising or not. A future change
    that reimplemented either side would have to keep them agreeing to pass this, which is the
    whole reason it is written as a property instead of as two more cases.
    """
    async with async_session_factory() as db:
        _job, loop, task = await _loop_with_one_task(db, suffix="property")
        await _completed_by(db, task, AUTHOR)

    async with async_session_factory() as db:
        claimed = await _claim_loop_task(db, await _fresh(db, loop.id), agent=REVIEWER)
        assert [t.id for t in claimed] == [task.id]

    # The offer stands. Now the reviewer signs it off, and the guard must not refuse.
    async with async_session_factory() as db:
        offered = await db.get(Task, task.id)
        reviewer_actor = run_actor(run_id="run-review-1", agent=REVIEWER)
        await apply_transition(db, offered, "under_review", reviewer_actor)
        await apply_transition(db, offered, "approved", reviewer_actor)
        await db.commit()
        assert (await db.get(Task, task.id)).status == "approved"


async def test_the_agent_the_queue_refuses_is_the_agent_the_guard_refuses(app):
    """The property's other half, and the one that would catch a drift in either direction: the
    author is refused by both, for the same reason, read from the same row."""
    from hub.task_transition_service import ActorNotPermittedError

    async with async_session_factory() as db:
        _job, loop, task = await _loop_with_one_task(db, suffix="mirror")
        await _completed_by(db, task, AUTHOR)

    async with async_session_factory() as db:
        assert await _claim_loop_task(db, await _fresh(db, loop.id), agent=AUTHOR) == []

    async with async_session_factory() as db:
        finished = await db.get(Task, task.id)
        author_actor = run_actor(run_id="run-author-2", agent=AUTHOR)
        await apply_transition(db, finished, "under_review", author_actor)
        with pytest.raises(ActorNotPermittedError):
            await apply_transition(db, finished, "approved", author_actor)


# ---------------------------------------------------------------------------
# 3.3 — the obvious wrong fix, refused
# ---------------------------------------------------------------------------


async def test_the_claimable_tuple_does_not_gain_completed(app):
    """Widening `CLAIMABLE_LOOP_TASK_STATUSES` is the fix this group exists not to make.

    It would be actor-blind — the one property the whole group is about — and it would say "any
    agent may claim finished work", which is false for exactly the agent the rule exists to stop.
    The reviewable statuses are their own set for that reason, and the two do not overlap.
    """
    assert "completed" not in CLAIMABLE_LOOP_TASK_STATUSES
    assert "completed" in REVIEWABLE_LOOP_TASK_STATUSES
    assert set(CLAIMABLE_LOOP_TASK_STATUSES) & set(REVIEWABLE_LOOP_TASK_STATUSES) == set()


async def test_a_non_reviewable_unclaimable_status_is_still_refused_for_everyone(app):
    """`blocked` is the control. It is also outside the claimable tuple, and it must *not* have
    acquired an actor-dependent answer — the person holding the unanswered question is who unblocks
    it, and no agent is a candidate.
    """
    async with async_session_factory() as db:
        _job, _loop, task = await _loop_with_one_task(db, suffix="blocked", status="blocked")

    async with async_session_factory() as db:
        fresh_task = await db.get(Task, task.id)
        assert await task_is_claimable_by(db, fresh_task, AUTHOR) is False
        assert await task_is_claimable_by(db, fresh_task, REVIEWER) is False


# ---------------------------------------------------------------------------
# 3.5 — the board and the firing still agree, now with an actor in it
# ---------------------------------------------------------------------------


async def test_the_board_and_the_firing_agree_about_a_completed_task(
    app, auth_headers, bind_runner
):
    """Human-only check 13.1 of `task-dependencies`, made mechanical for the review case.

    The board takes both its answers from `decide_firing`, so this is not a comparison of two
    derivations — it is a check that widening the firing did not leave the board's *query* behind
    it. It would have: `CURRENT_ITEM_TASK_STATUSES` gates which rows the board's candidate query can
    return at all, and a claimed `completed` task outside that set produces a loop actively
    reviewing with **no current item shown** — the 2026-08-21 blocked defect, mirrored.

    Staffed by adding an agent rather than by renaming the job's, which is the part worth reading:
    for a reviewable task the ladder decides, and the job's own agent has no privilege in it. With
    only the author on the roster the board shows nothing — not because the author is the job's
    agent, but because rung 3 could not staff the step.
    """
    from hub.api.v1.jobs import _batch_loop_summaries

    from .review_evidence import record_review_evidence
    from .test_review_turn import _roster

    await _roster(app, auth_headers, bind_runner, AUTHOR)

    async with async_session_factory() as db:
        job, loop, task = await _loop_with_one_task(db, suffix="board")
        await _completed_by(db, task, AUTHOR)
        # A reviewer needs a commit to be shown. Without one the firing declines the step for a
        # different reason entirely and this test would pass on the wrong evidence — the subject
        # here is whether the board keeps up with the firing, not whether the work is reviewable.
        await record_review_evidence(db, task.id, suffix="actor-board", actor=AUTHOR)
        summaries = await _batch_loop_summaries(db, [job.id])
        assert summaries[job.id].current_tasks == [], (
            "with only the author on the roster there is nobody to review, and the board must not "
            "show work no firing will take"
        )

    # A second agent joins. Nothing else changes — not the job, not the task, not the queue.
    await _roster(app, auth_headers, bind_runner, REVIEWER)

    async with async_session_factory() as db:
        summaries = await _batch_loop_summaries(db, [job.id])
        current = summaries[job.id].current_tasks
        assert [entry["id"] for entry in current] == [task.id]
        assert current[0]["status"] == "completed"

    async with async_session_factory() as db:
        from hub.scheduler import decide_firing

        decision = await decide_firing(db, await _fresh(db, loop.id), default_agent=AUTHOR)
        assert [s.task.id for s in decision.selections] == [task.id]
        assert (
            decision.selections[0].agent == REVIEWER
        ), "the ladder staffs a review, not the job's own agent — which here is the author"
        assert decision.selections[0].is_review is True


# ---------------------------------------------------------------------------
# The finding that came out of reviewing the spec against the code
# ---------------------------------------------------------------------------


async def test_a_completed_task_is_reviewable_even_with_an_unapproved_prerequisite(app):
    """`candidate_is_startable` gates every other non-`in_progress` candidate on the dependency
    gate, because they are one `apply_transition` away from `in_progress` — the edge that gate
    guards. A `completed` task claimed for review is one move away from a *review outcome*, which
    the gate says nothing about.

    Left ungated, finished work would be skipped from review because its own prerequisite had not
    been approved, and the stall would name a remedy nobody can act on: approving the prerequisite
    is not what the queue is waiting for. Caught by reviewing the spec against this function rather
    than by a failure, so it is pinned here.
    """
    from hub.db.models import TaskDependency

    async with async_session_factory() as db:
        _job, loop, task = await _loop_with_one_task(db, suffix="gated")
        await _completed_by(db, task, AUTHOR)
        prereq = Task(
            id="task-actor-gated-prereq",
            project_id="proj-test",
            title="an unapproved prerequisite",
            status="pending",
            loop_id=loop.id,
        )
        db.add(prereq)
        await db.commit()
        db.add(
            TaskDependency(
                id=f"tdep-{task.id}-{prereq.id}",
                project_id="proj-test",
                task_id=task.id,
                depends_on_task_id=prereq.id,
            )
        )
        await db.commit()

    async with async_session_factory() as db:
        claimed = await _claim_loop_task(db, await _fresh(db, loop.id), agent=REVIEWER)
        assert [t.id for t in claimed] == [task.id], (
            "a finished task's own prerequisite has nothing to do with whether the work may be "
            "reviewed; gating it on the `-> in_progress` edge asks the wrong question"
        )
