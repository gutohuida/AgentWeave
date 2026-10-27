"""A finished task is not offered for review while the turn that finished it is still running
(task-1d2e8ad5d79a).

An author marks its task `completed` mid-turn; its work reaches the task branch only when the turn
ends and the Hub commits it. Measured on slice 2 of the red thread (task-9df7ad59d0e6): completed
22:59:57, the flow fired 23:00:00, the author's snapshot landed 23:00:08 -- and the reviewer was
checked out at the branch's base, master's previous integrate, so it reviewed nothing.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Run
from hub.scheduler import DECISION_CLAIM, DECISION_IN_FLIGHT, decide_firing

from .review_evidence import record_review_evidence
from .test_review_leaves_the_pool import (
    AUTHOR,
    REVIEWER,
    _completed_by,
    _flow_with_task,
    _fresh_loop,
)
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio


async def _author_run(db, task_id, status):
    db.add(
        Run(
            id=f"run-author-{task_id}",
            project_id="proj-test",
            agent=AUTHOR,
            task_id=task_id,
            status=status,
            turn_depth=0,
        )
    )
    await db.commit()


async def test_a_review_waits_while_the_authors_turn_is_still_running(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop, task = await _flow_with_task(db, suffix="midturn")
        await _completed_by(db, task, AUTHOR)
        await record_review_evidence(db, task.id, suffix="midturn", actor=AUTHOR)
        await _author_run(db, task.id, "running")

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

        # In flight, not deferred and not a stall (F1049): the author's turn is on the task, and
        # the end of that turn requests the firing that offers the review.
        assert decision.selections == ()
        assert decision.kind == DECISION_IN_FLIGHT
        assert decision.stall_reason is None
        assert decision._cannot_staff == ((task.id, AUTHOR),)


async def test_the_review_is_offered_once_that_turn_has_ended(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop, task = await _flow_with_task(db, suffix="ended")
        await _completed_by(db, task, AUTHOR)
        await record_review_evidence(db, task.id, suffix="ended", actor=AUTHOR)
        await _author_run(db, task.id, "completed")

        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)

        assert decision.kind == DECISION_CLAIM
        assert [(s.task.id, s.agent, s.is_review) for s in decision.selections] == [
            (task.id, REVIEWER, True)
        ]
