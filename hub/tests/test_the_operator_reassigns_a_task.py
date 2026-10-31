"""F1114: the operator gives any open task to any open agent, and is told what happens next.

On 2026-10-31 `task-5a9efc6d2670` was stranded with its holder in an ended flow and the app had no
way to move it. Each test drives `POST /tasks/{id}/reassign` and reads the queue the turn starts from.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from hub import assigned_task_start
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, InboundQueueEntry, Loop, Run, Task, TaskTransition

from .test_review_turn import _roster

P = "proj-test"
TASKS = f"/api/v1/projects/{P}/tasks"

STARTED = MagicMock(waiting_reason=None, terminal_failure=False)


def _scheduling(result=STARTED):
    return patch("hub.turn_scheduler.schedule_agent", AsyncMock(return_value=result))


async def _task(task_id="task-move", **fields):
    fields.setdefault("status", "pending")
    fields.setdefault("assignee", "dev")
    async with async_session_factory() as db:
        db.add(Task(id=task_id, project_id=P, title="Move me", **fields))
        await db.commit()
    return task_id


async def _flow(*, ended: bool) -> str:
    async with async_session_factory() as db:
        job = AIJob(
            id="job-move",
            project_id=P,
            name="flow",
            agent="dev",
            message="work",
            cron="*/5 * * * *",
            session_mode="new",
            enabled=not ended,
        )
        loop = Loop(
            id="loop-move",
            project_id=P,
            job_id=job.id,
            spec_document_id="spdoc-move",
            purpose="",
            ending_state="completed" if ended else None,
        )
        db.add_all([job, loop])
        await db.commit()
    return "loop-move"


async def _reassign(app, auth_headers, task_id, agent):
    with _scheduling():
        response = await app.post(
            f"{TASKS}/{task_id}/reassign", json={"agent": agent}, headers=auth_headers
        )
        await assigned_task_start.settled()
    return response


async def _entries(agent):
    async with async_session_factory() as db:
        return (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == agent)))
            .scalars()
            .all()
        )


async def _row(task_id="task-move"):
    async with async_session_factory() as db:
        return await db.get(Task, task_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "assigned"])
async def test_a_task_outside_any_flow_starts_for_its_new_holder(
    app, auth_headers, bind_runner, status
):
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _task(status=status)

    response = await _reassign(app, auth_headers, "task-move", "qa")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["assignee"], body["status"]) == ("qa", "assigned")
    assert "qa" in body["next_turn"]
    (entry,) = await _entries("qa")
    assert entry.task_id == "task-move"


@pytest.mark.asyncio
async def test_sent_back_work_in_an_ended_flow_starts_with_why_it_came_back(
    app, auth_headers, bind_runner
):
    """The stranded case itself: the flow is over, so nothing else will ever brief the new holder."""
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    loop_id = await _flow(ended=True)
    await _task(status="revision_needed", loop_id=loop_id, notes="The probe still fails.")

    response = await _reassign(app, auth_headers, "task-move", "qa")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["assignee"], body["status"]) == ("qa", "revision_needed")
    (entry,) = await _entries("qa")
    assert entry.task_id == "task-move"
    assert "The probe still fails." in entry.content


@pytest.mark.asyncio
async def test_a_task_in_a_live_flow_is_left_to_the_flows_firing(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    loop_id = await _flow(ended=False)
    await _task(status="revision_needed", loop_id=loop_id)

    with patch("hub.flow_advance.request") as firing:
        response = await _reassign(app, auth_headers, "task-move", "qa")

    assert response.status_code == 200, response.text
    assert "flow" in response.json()["next_turn"]
    firing.assert_called_once_with(loop_id)
    assert await _entries("qa") == []


@pytest.mark.asyncio
async def test_a_build_task_keeps_its_new_builder(app, auth_headers, bind_runner):
    """A later send-back or cleared holder goes to `builder`, so that moves with the holder."""
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _task(builder="dev")

    assert (await _reassign(app, auth_headers, "task-move", "qa")).status_code == 200

    assert (await _row()).builder == "qa"


@pytest.mark.asyncio
async def test_dead_in_progress_work_returns_to_assigned_for_its_new_holder(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _task(status="in_progress")

    response = await _reassign(app, auth_headers, "task-move", "qa")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "assigned"
    assert len(await _entries("qa")) == 1
    async with async_session_factory() as db:
        moves = (
            (await db.execute(select(TaskTransition).where(TaskTransition.task_id == "task-move")))
            .scalars()
            .all()
        )
    assert [(m.from_status, m.to_status) for m in moves] == [("in_progress", "assigned")]


@pytest.mark.asyncio
async def test_a_live_run_on_the_task_refuses(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _task(status="in_progress")
    async with async_session_factory() as db:
        db.add(
            Run(
                id="run-live",
                project_id=P,
                agent="dev",
                status="running",
                turn_depth=0,
                task_id="task-move",
            )
        )
        await db.commit()

    turn = MagicMock(agent="dev", run_id="run-live", started_at=None)
    with patch("hub.run_liveness.live_turn_for_task", AsyncMock(return_value=turn)):
        response = await _reassign(app, auth_headers, "task-move", "qa")

    assert response.status_code == 409
    assert "run-live" in response.json()["detail"]
    assert (await _row()).assignee == "dev"


@pytest.mark.asyncio
async def test_a_read_only_agent_is_refused_with_its_reason(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _task()

    with patch("hub.api.v1.tasks.is_read_only_agent", AsyncMock(return_value=True)):
        response = await _reassign(app, auth_headers, "task-move", "qa")

    assert response.status_code == 422
    assert "qa" in response.json()["detail"]
    assert (await _row()).assignee == "dev"


@pytest.mark.asyncio
async def test_an_agent_who_is_not_open_is_refused(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "dev")
    await _task()

    response = await _reassign(app, auth_headers, "task-move", "ghost")

    assert response.status_code == 422
    assert (await _row()).assignee == "dev"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["approved", "rejected"])
async def test_a_closed_task_is_refused(app, auth_headers, bind_runner, status):
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _task(status=status)

    response = await _reassign(app, auth_headers, "task-move", "qa")

    assert response.status_code == 409
    assert (await _row()).assignee == "dev"


@pytest.mark.asyncio
async def test_finished_work_goes_to_review_and_never_to_its_author(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _task(status="completed")
    async with async_session_factory() as db:
        db.add(
            TaskTransition(
                id="tt-done",
                task_id="task-move",
                project_id=P,
                from_status="in_progress",
                to_status="completed",
                actor_kind="run",
                actor_agent="dev",
            )
        )
        await db.commit()

    refused = await _reassign(app, auth_headers, "task-move", "dev")
    assert refused.status_code == 403, refused.text
    assert await _entries("dev") == []

    with patch(
        "hub.task_integration.review_target", AsyncMock(return_value=MagicMock(resolved=True))
    ):
        response = await _reassign(app, auth_headers, "task-move", "qa")
    assert response.status_code == 200, response.text
    assert "review" in response.json()["next_turn"]
    (entry,) = await _entries("qa")
    assert entry.review_task_id == "task-move"


@pytest.mark.asyncio
async def test_a_turn_that_must_wait_says_so(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _task()
    waiting = MagicMock(waiting_reason="qa is running another turn", terminal_failure=False)

    with _scheduling(waiting):
        response = await app.post(
            f"{TASKS}/task-move/reassign", json={"agent": "qa"}, headers=auth_headers
        )

    assert response.status_code == 200, response.text
    assert "qa is running another turn" in response.json()["next_turn"]
