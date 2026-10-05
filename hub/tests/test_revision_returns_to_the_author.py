"""Finding F495 — a task sent back for revision is reworked by its author, not its reviewer.

**The defect this pins.** A flow staffing a review writes the reviewer into `task.assignee` before it
moves the task to `under_review` (`scheduler.enter_selected_task`, F70's ordering). When the reviewer
then set `revision_needed`, nothing wrote the assignee back, and the next firing's ordinary-work arm
*resumes* a staffed task with `agent = task.assignee` — the reviewer. The reviewer authored the fix,
became the recorded completer, and the original author was staffed to review it: the two swapped
roles on every revision cycle. Measured on `:8000` (read-only) before the fix: in 3 of 7 agent
revision cycles the reviewer did the rework (`task-0ff93faef4ba` swapped twice).

The return happens in `apply_transition`, so every route that sends work back — the reviewer's
`update_task`, the operator's route, a job — returns it the same way.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.scheduler import DECISION_CLAIM, decide_firing, enter_selected_task
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator, run_actor

from .review_evidence import record_review_evidence
from .test_review_leaves_the_pool import (
    _completed_by,
    _flow_with_task,
    _fresh_loop,
    _fresh_task,
)
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

AUTHOR = "f495-author"
REVIEWER = "f495-reviewer"


async def _sent_back_by_reviewer(db, task):
    await enter_selected_task(db, task, agent=REVIEWER, is_review=True)
    await db.commit()
    await apply_transition(
        db, task, "revision_needed", run_actor(run_id=f"run-{REVIEWER}-{task.id}", agent=REVIEWER)
    )
    await db.commit()


async def test_a_task_sent_back_is_assigned_to_its_author(app):
    async with async_session_factory() as db:
        _job, _loop, task = await _flow_with_task(db, suffix="f495-assign")
        await _completed_by(db, task, AUTHOR)
        await _sent_back_by_reviewer(db, task)

    async with async_session_factory() as db:
        back = await _fresh_task(db, task.id)
        assert back.status == "revision_needed"
        assert back.assignee == AUTHOR, "the rework belongs to the agent that did the work"


async def test_the_next_firing_staffs_the_author_for_the_rework(app, auth_headers, bind_runner):
    """The seam the finding names: the firing's ordinary-work arm resumes `task.assignee`."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop, task = await _flow_with_task(db, suffix="f495-fire")
        await _completed_by(db, task, AUTHOR)
        await record_review_evidence(db, task.id, suffix="f495-fire", actor=AUTHOR)
        await _sent_back_by_reviewer(db, task)

    async with async_session_factory() as db:
        decision = await decide_firing(db, await _fresh_loop(db, loop.id), default_agent=job.agent)
        assert decision.kind == DECISION_CLAIM
        assert [(s.task.id, s.agent, s.is_review) for s in decision.selections] == [
            (task.id, AUTHOR, False)
        ], "the reviewer must not be fired to rework what it reviewed"


async def test_an_operator_completion_leaves_the_assignee_alone(app):
    """No agent is recorded as the completer, so there is nobody to return it to: the assignee is
    not guessed at, and not cleared."""
    async with async_session_factory() as db:
        _job, _loop, task = await _flow_with_task(db, suffix="f495-operator")
        for status in ("assigned", "in_progress", "completed"):
            await apply_transition(db, task, status, operator())
        await db.commit()
        await enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await db.commit()
        await apply_transition(db, task, "revision_needed", operator())
        await db.commit()

    async with async_session_factory() as db:
        assert (await _fresh_task(db, task.id)).assignee == REVIEWER
