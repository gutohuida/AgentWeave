"""A hand-started task sent back by its review restarts its author (F1196).

`review_on_completion` finds a reviewer for finished work outside a build; the way back was missing:
when that review sent the task to `revision_needed`, nothing started the author, so the task sat
until the operator re-sent it (AW-146, 2026-11-16). These drive the reviewer's own move through the
agent route and read the inbound queue the turn scheduler starts from.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub import send_back_restart, turn_scheduler
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AIJob, EventLog, InboundQueueEntry, Loop, Run, Task, TaskTransition

pytestmark = pytest.mark.asyncio

TASKS = "/api/v1/projects/proj-test/tasks"
AGENT_TASKS = "/api/v1/agent-actions/tasks/{}"
AUTHOR = "dev"
REVIEWER = "qa"
TASK = "task-f11960000001"
SECRET = "aw_run_qa-secret"


@pytest.fixture
def scheduled(monkeypatch):
    asked: list = []

    async def record(project_id, agent):
        asked.append(agent)

    monkeypatch.setattr(turn_scheduler, "schedule_accepted", record)
    return asked


async def _under_review(task_id=TASK, *, loop_id=None, sent_back_before=0) -> None:
    """A task its author completed and the reviewer holds, `sent_back_before` rounds in."""
    async with async_session_factory() as session:
        for name in (AUTHOR, REVIEWER):
            if await session.get(Agent, f"ag-{name}") is None:
                session.add(Agent(id=f"ag-{name}", project_id="proj-test", name=name))
        session.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title="Fix the timing test",
                description="It fails under the full suite.",
                status="under_review",
                assignee=REVIEWER,
                loop_id=loop_id,
            )
        )
        await session.flush()
        moves = [
            ("in_progress", "completed", AUTHOR),
            ("completed", "under_review", REVIEWER),
        ]
        for _ in range(sent_back_before):
            moves += [
                ("under_review", "revision_needed", REVIEWER),
                ("revision_needed", "completed", AUTHOR),
                ("completed", "under_review", REVIEWER),
            ]
        for index, (before, after, agent) in enumerate(moves):
            session.add(
                TaskTransition(
                    id=f"ttr-{task_id[-6:]}{index:02d}",
                    project_id="proj-test",
                    task_id=task_id,
                    from_status=before,
                    to_status=after,
                    actor_kind="run",
                    actor_agent=agent,
                    origin="actor",
                )
            )
        if not await session.get(Run, "run-qa"):
            session.add(
                Run(
                    id="run-qa",
                    project_id="proj-test",
                    agent=REVIEWER,
                    status="running",
                    task_id=task_id,
                    capability_token_hash=hash_run_token(SECRET),
                )
            )
        await session.commit()


async def _send_back(app, task_id=TASK):
    response = await app.patch(
        AGENT_TASKS.format(task_id),
        json={
            "status": "revision_needed",
            "notes": "The retry is not bounded.",
            "reason_class": "defect",
        },
        headers={"Authorization": f"Bearer {SECRET}"},
    )
    assert response.status_code == 200, response.text
    await send_back_restart.settled()


async def _entries(task_id=TASK) -> list:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.task_id == task_id)
                )
            )
            .scalars()
            .all()
        )


async def _held_events(task_id=TASK) -> list:
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == send_back_restart.HELD_EVENT)
                )
            )
            .scalars()
            .all()
        )
    return [row for row in rows if (row.data or {}).get("task_id") == task_id]


async def test_a_review_send_back_queues_the_authors_turn(app, scheduled):
    await _under_review()
    await _send_back(app)

    [entry] = await _entries()
    assert (entry.agent, entry.state, entry.task_id) == (AUTHOR, "queued", TASK)
    assert "The retry is not bounded." in entry.content, "the author is pointed at the notes"
    assert scheduled == [AUTHOR]


async def test_a_task_in_a_live_flow_is_left_to_the_flow(app, scheduled):
    async with async_session_factory() as session:
        session.add(
            AIJob(
                id="job-flow",
                project_id="proj-test",
                name="flow",
                agent=AUTHOR,
                message="work",
                cron="*/5 * * * *",
                session_mode="new",
                enabled=True,
            )
        )
        await session.flush()
        session.add(Loop(id="loop-flow", project_id="proj-test", job_id="job-flow", purpose="x"))
        await session.commit()
    await _under_review(loop_id="loop-flow")
    await _send_back(app)

    assert await _entries() == [] and scheduled == []


async def test_the_operators_send_back_does_not_queue_the_author(app, auth_headers, scheduled):
    await _under_review()
    response = await app.patch(
        f"{TASKS}/{TASK}",
        json={"status": "revision_needed", "notes": "No.", "reason_class": "defect"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    await send_back_restart.settled()

    assert await _entries() == [] and scheduled == []


async def test_the_third_consecutive_send_back_is_held_for_the_operator(app, scheduled):
    await _under_review(sent_back_before=2)
    await _send_back(app)

    assert await _entries() == [] and scheduled == []
    [held] = await _held_events()
    assert "3" in held.data["reason"]


async def test_the_second_send_back_still_restarts_the_author(app, scheduled):
    await _under_review(sent_back_before=1)
    await _send_back(app)

    assert [e.agent for e in await _entries()] == [AUTHOR]
    assert await _held_events() == []
