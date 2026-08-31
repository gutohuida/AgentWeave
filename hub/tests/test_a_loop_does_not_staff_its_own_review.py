"""F161 — a loop staffs a review it structurally cannot fill, and says so forever.

**The defect.** `decide_firing`'s finished-work arm was applied to every loop, not only to a flow.
A loop has one agent and no second party, so every reviewer the ladder could resolve for it is the
agent that completed the work, whom `_guard_reviewer_is_not_the_author` refuses on arrival. What
the operator saw was a firing that reported *"there is no commit to review"* on every tick, for
work that was finished, with no move available to anybody.

**And it was a breach, not merely a waste.** Reviewer resolution, review dispatch and its handover
briefings are `agent-flows`' property, and `agent-flows:13` requires that a loop declaring no
document *"SHALL be unaffected by [those requirements] and SHALL behave exactly as it does today"*.
So the repair restores the corpus rather than trimming behaviour the corpus never covered, and it
goes at the **selection** site — the operator's answer to D21 was that a loop should not staff
reviews at all, which teaching `commit_for_task_review` about branch tips would have entrenched.

**What it does not remove.** Two things reach the same code and stay (design D5, round 3): the
operator's by-hand dispatch, which `task-lifecycle-governance:1481` requires to staff the task, and
the F70 recovery of a task already in `under_review` under its own author's name, which
`task-lifecycle-governance:317` calls a reassignment that must not move status. The exclusion is on
the fresh-review branch only, because the recovery path deliberately records no `in_flight` entry
(`scheduler.py:1349`) and a wholesale exclusion would drop such a row out of the walk in silence.

**And it does not mean saying nothing.** Removing the arm leaves a loop whose only open task is
`completed` falling to `_stall_reason_from_walk`'s *"no claimable task among 1 open (1 completed)"*
— word for word the sentence the review arm's own comment records as measured-live-and-wrong on
2026-08-30. This change would have re-earned it for loops on the day it removed it for flows. The
firing says what is actually true instead: the work is finished and the next move is the
operator's.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.api.v1.agent_trigger import trigger_agent_directly
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, SpecDocument, Task
from hub.scheduler import DECISION_CLAIM, DECISION_STALLED, decide_firing
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

from .review_evidence import record_review_evidence
from .test_review_dispatch_staffs_the_task import _init_repo
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

AUTHOR = "f161-author"
REVIEWER = "f161-reviewer"
NOW = datetime.now(timezone.utc)


async def _queue(db, *, suffix, declares_document=False):
    """A job and its loop. `declares_document` is the whole distinction under test.

    A flow is a loop that declares a specification document (`agent-flows:13`), and after this
    change that declaration is what `decide_firing` reads to decide whether the review arm applies.
    Both shapes are built by one helper deliberately: the two tests that matter here differ in
    exactly one column, and a reader should be able to see that.
    """
    job = AIJob(
        id=f"job-f161-{suffix}",
        project_id="proj-test",
        name=f"F161 {suffix}",
        agent=AUTHOR,
        message="work the queue",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    if declares_document:
        db.add(
            SpecDocument(
                id=f"doc-f161-{suffix}",
                project_id="proj-test",
                path=f"spec/f161-{suffix}.html",
                title=f"F161 {suffix}",
                phase="current",
                kind="capability",
            )
        )
    await db.commit()
    loop = Loop(
        id=f"loop-f161-{suffix}",
        project_id="proj-test",
        job_id=job.id,
        purpose=f"f161 {suffix}",
        spec_document_id=f"doc-f161-{suffix}" if declares_document else None,
    )
    db.add(loop)
    await db.commit()
    return job, loop


async def _task(db, loop, *, suffix, status="pending", assignee=None):
    task = Task(
        id=f"task-f161-{suffix}",
        project_id="proj-test",
        title=f"work {suffix}",
        status=status,
        assignee=assignee,
        loop_id=loop.id,
    )
    db.add(task)
    await db.commit()
    return task


async def _completed_by(db, task, agent=AUTHOR):
    """Walked through the transition machine, never constructed at `completed`.

    `completion_attribution` reads the history. A row built directly at `completed` names no author,
    which is a *different* arm of the code under test, and every assertion below would pass for the
    wrong reason.
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
# 5.1 / 5.3 — the loop stops entering the arm, and stays quiet about it
# ---------------------------------------------------------------------------


async def test_a_loops_completed_task_is_not_selected_for_review(app, auth_headers, bind_runner):
    """The requirement's first scenario, with the roster that used to make it fire.

    `REVIEWER` is on the roster and is not the author, so before this change the ladder resolved it
    and the firing selected a review. The exclusion is what makes the selection empty now — not an
    absence of anybody to staff, which would prove nothing about the arm.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _queue(db, suffix="notselected")
        task = await _task(db, loop, suffix="notselected")
        await _completed_by(db, task)
        await record_review_evidence(db, task.id, suffix="f161-notselected", actor=AUTHOR)

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert decision.selections == (), "a loop must not staff a review of its own agent's work"
    async with async_session_factory() as db:
        assert (await _fresh_task(db, task.id)).status == "completed", "and must not move the task"


async def test_the_unstaffed_report_stays_empty_for_a_loops_completed_work(
    app, auth_headers, bind_runner
):
    """Task 5.3. `unstaffed` entries surface to the operator as steps the flow could not take; a
    loop's finished work is not a step anything failed at, so it must not appear there.

    **Deliberately the no-evidence shape**, which is the one that used to fill `unstaffed`. With
    evidence recorded the arm resolved a reviewer and selected, so `unstaffed` was empty before this
    change too and the test would have passed against the defect it exists to pin.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _queue(db, suffix="quiet")
        task = await _task(db, loop, suffix="quiet")
        await _completed_by(db, task)

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert decision.unstaffed == ()
    assert decision.deferred == ()
    assert decision._cannot_staff == ()


async def test_no_firing_asks_a_loop_for_a_commit_to_review(app, auth_headers, bind_runner):
    """F161 as the operator met it: a task finished **without evidence**, and a firing that asked
    for a commit on every tick.

    The gate that produced that sentence sits inside the arm, so removing the arm removes the
    sentence. Asserted against everything the firing says rather than against `unstaffed` alone —
    the sentence reached the operator through the stall reason, which is a different field.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _queue(db, suffix="nocommit")
        task = await _task(db, loop, suffix="nocommit")
        await _completed_by(db, task)
        # Deliberately no evidence: this is the shape that used to produce the refusal.
        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    said = " ".join(
        [decision.stall_reason or ""] + [reason for _, reason in decision.unstaffed]
    ).lower()
    assert "commit" not in said and "evidence" not in said, said


# ---------------------------------------------------------------------------
# 5.4 — quiet is not the same as absent
# ---------------------------------------------------------------------------


async def test_the_firing_says_the_work_is_waiting_for_the_operator(app, auth_headers, bind_runner):
    """Task 5.4. Without this the firing falls to `_stall_reason_from_walk`'s generic sentence —
    the one measured live on 2026-08-30 as stating a fact and withholding the remedy."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _queue(db, suffix="waiting")
        task = await _task(db, loop, suffix="waiting")
        await _completed_by(db, task)

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert decision.kind == DECISION_STALLED
    assert "no claimable task" not in (decision.stall_reason or "")
    assert decision.stall_reason == (
        "loop queue is stalled: 1 finished task is waiting for you to land it. A loop does not "
        "review its own agent's work, so approving is what puts it in the product."
    )


async def test_the_sentence_counts_the_work_it_is_naming(app, auth_headers, bind_runner):
    """Two finished tasks, and the sentence says two. A count fixed at one would be a sentence the
    operator has to distrust the moment a second task finishes."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _queue(db, suffix="two")
        for suffix in ("twoa", "twob"):
            await _completed_by(db, await _task(db, loop, suffix=suffix))

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert decision.stall_reason == (
        "loop queue is stalled: 2 finished tasks are waiting for you to land them. A loop does "
        "not review its own agent's work, so approving is what puts it in the product."
    )


async def test_ordinary_work_is_still_claimed_alongside_finished_work(
    app, auth_headers, bind_runner
):
    """The exclusion drops the task out of the *review* arm and out of nothing else. A queue
    holding one finished task and one pending one still does the pending one."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _queue(db, suffix="mixed")
        await _completed_by(db, await _task(db, loop, suffix="mixeddone"))
        pending = await _task(db, loop, suffix="mixedtodo")

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert decision.kind == DECISION_CLAIM
    assert [(s.task.id, s.is_review) for s in decision.selections] == [(pending.id, False)]


# ---------------------------------------------------------------------------
# 5.1 — the flow's arm is untouched
# ---------------------------------------------------------------------------


async def test_a_flows_review_leg_is_unaffected(app, auth_headers, bind_runner):
    """The same fixture with one column set. If this ever fails together with the first test in
    this file, the exclusion has stopped keying on the declaration and has become a removal."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _queue(db, suffix="flow", declares_document=True)
        task = await _task(db, loop, suffix="flow")
        await _completed_by(db, task)
        await record_review_evidence(db, task.id, suffix="f161-flow", actor=AUTHOR)

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert [(s.task.id, s.agent, s.is_review) for s in decision.selections] == [
        (task.id, REVIEWER, True)
    ]


# ---------------------------------------------------------------------------
# 5.6 — what D5 does not remove
# ---------------------------------------------------------------------------


async def test_the_operator_can_still_review_a_loops_completed_task_by_hand(
    app, auth_headers, bind_runner, tmp_path
):
    """`task-lifecycle-governance:1481` requires every path that *dispatches* a review to staff the
    task, and names the operator's by-hand dispatch first among its scenarios.

    D5 removes a loop's **selection**, never a person's decision. Without this test, *"a loop does
    not staff a review"* reads as *"a loop's task cannot be reviewed"*, and the next change to touch
    this removes a path the corpus requires.
    """
    _init_repo(tmp_path)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _queue(db, suffix="byhand")
        task = await _task(db, loop, suffix="byhand")
        await _completed_by(db, task)
        await record_review_evidence(db, task.id, suffix="f161-byhand", actor=AUTHOR)

        conversation = new_conversation(project_id="proj-test", agent=REVIEWER, origin="operator")
        db.add(conversation)
        await db.commit()
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            await trigger_agent_directly(
                project_id="proj-test",
                agent=REVIEWER,
                message=f"review {task.id}",
                conversation_id=conversation.id,
                session=db,
                review_task_id=task.id,
            )

    async with async_session_factory() as db:
        fresh = await _fresh_task(db, task.id)
        assert fresh.status == "under_review"
        assert fresh.assignee == REVIEWER


async def test_a_loops_wedged_review_still_recovers(app, auth_headers, bind_runner):
    """The F70 recovery, and the reason the exclusion is on the fresh-review branch only.

    A task in `under_review` still held by its own author is nobody's review: the exits are offered
    to nobody and `_agents_that_are_free` counts the author busy on it forever. The walk carries
    such a row past the ordinary-work arm to the ladder, which excludes the author by construction
    — and it records no `in_flight` entry on the way (`scheduler.py:1349`), so an exclusion written
    at the top of the arm would drop the row out of the walk recording nothing at all.

    `task-lifecycle-governance:317` is what makes this a repair rather than a review: a
    reassignment that does not move the task to another status.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _queue(db, suffix="wedged")
        task = await _task(db, loop, suffix="wedged")
        await _completed_by(db, task)
        await record_review_evidence(db, task.id, suffix="f161-wedged", actor=AUTHOR)
        # Into review under its own author's name — the shape F70 left behind.
        await apply_transition(db, task, "under_review", run_actor(run_id="run-op", agent=AUTHOR))
        task.assignee = AUTHOR
        await db.commit()

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

    assert [(s.task.id, s.agent, s.is_review) for s in decision.selections] == [
        (task.id, REVIEWER, True)
    ], "the wedged row still reaches the ladder, which resolves somebody who is not the author"
    async with async_session_factory() as db:
        assert (await _fresh_task(db, task.id)).status == "under_review", "and it is not moved"
