"""Finding F832 -- a refused Land says "send the task back (revision_needed)", and the operator
could not: `completed` reached only `under_review` and `rejected`, and `under_review` was refused
with "Land it". The gate's remedy named a move the machine never offered.

The operator may now send completed work back in one move. An agent still may not: a send-back is a
judgement on work somebody else did, and the author reaches it only through a review.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.task_transitions import ACTOR_OPERATOR, ACTOR_RUN, allowed_targets, is_allowed

from .test_review_leaves_the_pool import _completed_by, _flow_with_task, _fresh_task
from .test_review_turn import _roster

TASKS = "/api/v1/projects/proj-test/tasks"
AUTHOR = "f832-author"


def test_the_operator_may_send_completed_work_back_and_an_agent_may_not():
    assert is_allowed("completed", "revision_needed", ACTOR_OPERATOR)
    assert "revision_needed" in allowed_targets("completed", ACTOR_OPERATOR)
    assert not is_allowed("completed", "revision_needed", ACTOR_RUN)


@pytest.mark.asyncio
async def test_completed_work_is_sent_back_to_its_author_in_one_patch(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        _job, _loop, task = await _flow_with_task(db, suffix="f832-send-back")
        await _completed_by(db, task, AUTHOR)

    resp = await app.patch(
        f"{TASKS}/{task.id}", json={"status": "revision_needed"}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "revision_needed"
    assert resp.json()["assignee"] == AUTHOR, "F495: the rework returns to its author"

    async with async_session_factory() as db:
        assert (await _fresh_task(db, task.id)).status == "revision_needed"
