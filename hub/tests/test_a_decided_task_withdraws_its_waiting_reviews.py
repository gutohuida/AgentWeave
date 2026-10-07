"""`a-decided-task-withdraws-its-waiting-reviews` (F440) -- spec/changes, trial Hub document
`spdoc-3b1585810681`.

A review queued for a task that is then given a verdict used to stay `queued`: delivered, refused
("not a status a review starts from"), counted to the delivery limit and only then given up. Since
the dispatch stages a flow's review, a flow's own review waits as exactly such an entry. A verdict
now withdraws it in the move's own transaction and announces it.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import EventLog, InboundQueueEntry, Task
from hub.run_task_binding import release_bindings_to

pytestmark = pytest.mark.asyncio


async def _task(task_id, *, status, assignee=None):
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title=f"Task {task_id}",
                status=status,
                assignee=assignee,
            )
        )
        await session.commit()


async def _entry(entry_id, *, agent="critic", state="queued", task_id=None, review_task_id=None):
    async with async_session_factory() as session:
        session.add(
            InboundQueueEntry(
                id=entry_id,
                project_id="proj-test",
                agent=agent,
                origin_type="operator",
                content="review it",
                hop_depth=0,
                state=state,
                task_id=task_id,
                review_task_id=review_task_id,
            )
        )
        await session.commit()


async def _row(entry_id):
    async with async_session_factory() as session:
        return (
            await session.execute(select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id))
        ).scalar_one()


async def _withdrawn_events():
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == "queue_entry_withdrawn")
                )
            )
            .scalars()
            .all()
        )
    return [row.data for row in rows]


async def test_approving_a_task_withdraws_its_queued_review(app):
    await _task("task-f440-a", status="approved")
    await _entry("entry-f440-a", review_task_id="task-f440-a")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-f440-a")
        await release_bindings_to(session, task)
        await session.commit()

    entry = await _row("entry-f440-a")
    assert entry.state == "withdrawn"
    assert entry.withdrawn_at is not None
    assert "approved" in (entry.abandoned_reason or "")
    assert entry.review_task_id == "task-f440-a", "the record of what it was for is kept"
    [event] = [e for e in await _withdrawn_events() if e.get("entry_id") == "entry-f440-a"]
    assert event["agent"] == "critic"
    assert event["task_id"] == "task-f440-a"
    assert event["verdict"] == "approved"


async def test_a_verdict_leaves_other_entries_as_they_were(app):
    await _task("task-f440-b", status="rejected")
    await _task("task-f440-elsewhere", status="completed")
    await _entry("entry-f440-delivered", state="delivered", review_task_id="task-f440-b")
    await _entry("entry-f440-other", review_task_id="task-f440-elsewhere")
    await _entry("entry-f440-work", agent="builder", task_id="task-f440-b")

    async with async_session_factory() as session:
        await release_bindings_to(session, await session.get(Task, "task-f440-b"))
        await session.commit()

    assert (await _row("entry-f440-delivered")).state == "delivered"
    assert (await _row("entry-f440-other")).state == "queued"
    work = await _row("entry-f440-work")
    assert (work.state, work.task_id) == ("queued", None), "a work entry keeps today's release"


async def test_revision_needed_over_http_withdraws_a_second_reviewers_waiting_review(
    app, auth_headers
):
    await _task("task-f440-rev", status="under_review", assignee="critic")
    await _entry("entry-f440-second", agent="auditor", review_task_id="task-f440-rev")

    with patch("hub.api.v1.tasks.sse_manager.broadcast", new=AsyncMock()) as broadcast:
        response = await app.patch(
            "/api/v1/projects/proj-test/tasks/task-f440-rev",
            json={"status": "revision_needed"},
            headers=auth_headers,
        )

    assert response.status_code == 200, response.text
    entry = await _row("entry-f440-second")
    assert entry.state == "withdrawn"
    assert "revision_needed" in (entry.abandoned_reason or "")
    announced = [
        call.args[2]
        for call in broadcast.await_args_list
        if call.args[1] == "queue_entry_withdrawn"
    ]
    assert [payload["entry_id"] for payload in announced] == ["entry-f440-second"]


async def test_approving_over_http_withdraws_the_waiting_review(app, auth_headers):
    await _task("task-f440-ok", status="under_review", assignee="critic")
    await _entry("entry-f440-ok", agent="auditor", review_task_id="task-f440-ok")

    response = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-f440-ok",
        json={"status": "approved"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert (await _row("entry-f440-ok")).state == "withdrawn"


async def test_landing_withdraws_the_waiting_review(app, auth_headers):
    await _task("task-f440-land", status="completed", assignee="builder")
    await _entry("entry-f440-land", review_task_id="task-f440-land")

    response = await app.post(
        "/api/v1/projects/proj-test/tasks/task-f440-land/land", headers=auth_headers
    )

    assert response.status_code == 200, response.text
    entry = await _row("entry-f440-land")
    assert entry.state == "withdrawn"
    assert "approved" in (entry.abandoned_reason or "")
