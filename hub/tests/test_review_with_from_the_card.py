"""`a-hand-started-task-reaches-review-and-merge`, FR-1 (ac-card-menu), on the Hub's side.

The card's start menu on a `completed` task lists "Review with <agent>" from
`GET /tasks/{id}/moves` (`reviewers`) and posts `/agent/trigger` with `review_task_id`
(`hub/ui/src/api/tasks.ts`, `useStartReviewOfTask`). These pin the two answers that menu relies on:
the list never names the task's author, and the trigger the card sends moves the task to
`under_review` held by the reviewer it named. The component half is
`hub/ui/src/__tests__/taskCardReviewWith.test.tsx`.
"""

from unittest.mock import patch

import pytest

from hub.db.engine import async_session_factory

# AUTHOR is who `_task_completed_by_author` walks the task to `completed` as.
from .test_review_dispatch_staffs_the_task import (
    AUTHOR,
    _evidence_naming_a_commit,
    _init_repo,
    _roster,
    _snapshot,
    _task_completed_by_author,
)

pytestmark = pytest.mark.asyncio

REVIEWER = "rw-reviewer"


async def test_the_menus_reviewers_never_name_the_author(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        task = await _task_completed_by_author(db, suffix="rw-list")

    response = await app.get(
        f"/api/v1/projects/proj-test/tasks/{task.id}/moves", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["reviewers"] == [REVIEWER]


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_review_with_from_the_card_puts_the_task_under_review_held_by_the_reviewer(
    app, auth_headers, bind_runner, tmp_path
):
    _init_repo(tmp_path)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        task = await _task_completed_by_author(db, suffix="rw-card")
        await _evidence_naming_a_commit(db, task.id, suffix="rw-card")
        assert await _snapshot(db, task.id) == ("completed", None)

    # The body `useStartReviewOfTask` posts, as it posts it: no `task_id`, so no work turn.
    with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={
                "agent": REVIEWER,
                "message": f"Review task {task.id}: {task.title}",
                "review_task_id": task.id,
            },
            headers=auth_headers,
        )
    assert response.status_code == 200, response.text

    async with async_session_factory() as db:
        assert await _snapshot(db, task.id) == ("under_review", REVIEWER)
