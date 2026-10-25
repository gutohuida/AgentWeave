"""A completed task its author holds always has a way to review without the operator.

Measured on the operator's Hub (2026-10-25): task-0759b1b3aa12 sat `completed`, held by the agent
recorded as its author. The author may not take it to `under_review` (403), the reviewer may not
while the author holds it (403), `completed -> approved` is no edge (409), and the mender's
`mend_reset_task` offered only `assigned`/`pending` -- refused 409 from `completed`. The same wall
held side task task-146c7b264917, which no flow staffs, until the operator stepped in.

`mend_reset_task(task, "under_review", reviewer)` now queues the reviewer's review turn, and the
dispatch stages the review as it does for the flow and the operator.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import Agent, InboundQueueEntry, RequirementEvidence, Task

from .test_a_stalled_project_wakes_the_mender import builder, mender_run  # noqa: F401
from .test_task_integration import (
    accept_evidence,
    commit_on_branch,
    drive_to,
    git,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)

RESET = "/api/v1/agent-actions/mender/tasks/{}/reset"


async def _completed_task_its_author_holds(app, auth_headers, run_headers, root):
    make_repo(root)
    await make_document(app, auth_headers, run_headers)
    await set_main_branch("main")
    task = await linked_task(app, auth_headers)
    commit_on_branch(root, worktrees.task_branch_name(task), "README2.md", "the change\n")
    evidence = await accept_evidence(app, auth_headers, run_headers)
    git(root, "checkout", "-q", "main")
    moved = await drive_to(app, auth_headers, task, "assigned", "in_progress", "completed")
    assert moved.status_code == 200, moved.text
    async with async_session_factory() as session:
        # Recorded by the author's turn on the task, as a bound run records it.
        (await session.get(RequirementEvidence, evidence)).task_id = task
        (await session.get(Task, task)).assignee = "builder"
        session.add(Agent(id="ag-qa", project_id="proj-test", name="QA"))
        await session.commit()
    return task


@pytest.mark.asyncio
async def test_the_mender_hands_a_completed_task_to_its_reviewer(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task = await _completed_task_its_author_holds(app, auth_headers, builder, tmp_path)
    mender = await mender_run()

    with patch("hub.turn_scheduler.schedule_accepted", AsyncMock()) as started:
        handed = await app.post(
            RESET.format(task), json={"status": "under_review", "assignee": "QA"}, headers=mender
        )
    assert handed.status_code == 200, handed.text
    assert handed.json()["review_queued_for"] == "QA"
    started.assert_awaited_once_with("proj-test", "QA")
    async with async_session_factory() as session:
        entry = (
            await session.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.review_task_id == task)
            )
        ).scalar_one()
        assert entry.agent == "QA"
        assert entry.state == "queued"
        # The dispatch stages the review; until it does the task is as it was.
        assert (await session.get(Task, task)).status == "completed"


@pytest.mark.asyncio
async def test_the_mender_cannot_hand_work_to_its_own_author_for_review(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    task = await _completed_task_its_author_holds(app, auth_headers, builder, tmp_path)
    mender = await mender_run()

    with patch("hub.turn_scheduler.schedule_accepted", AsyncMock()) as started:
        refused = await app.post(
            RESET.format(task),
            json={"status": "under_review", "assignee": "builder"},
            headers=mender,
        )
        missing = await app.post(
            RESET.format(task), json={"status": "under_review"}, headers=mender
        )
    assert refused.status_code == 403, refused.text
    assert "evidence" in refused.json()["detail"]
    assert missing.status_code == 400, missing.text
    started.assert_not_awaited()
    async with async_session_factory() as session:
        queued = (
            await session.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.review_task_id == task)
            )
        ).all()
    assert queued == []
