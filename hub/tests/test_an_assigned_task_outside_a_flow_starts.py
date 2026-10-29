"""An assigned task outside a flow starts (`a-red-main-does-not-hold-the-night`, FR-9, FR-10).

2026-10-27 on the operator's Hub: task-eecc162f6e1d was moved to `assigned` at 01:24 and nothing
was queued for its assignee until the mender messaged it at 02:55; the fix took 15 minutes, the
wait 91. These drive the real routes (the operator's PATCH, an agent's run through the agent
route) and the real stall sweep, and read the inbound queue the turn scheduler starts from.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from hub import stalls, turn_scheduler
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AIJob,
    InboundQueueEntry,
    Loop,
    Run,
    Task,
    TaskTransition,
)

pytestmark = pytest.mark.asyncio

TASKS = "/api/v1/projects/proj-test/tasks"
AGENT_TASKS = "/api/v1/agent-actions/tasks/{}"
WORKER = "worker"
TASK = "task-a55a00000001"


@pytest.fixture
def scheduled(monkeypatch):
    """The agents a turn start was asked for; no turn is really started."""
    asked: list = []

    async def record(project_id, agent):
        asked.append(agent)

    monkeypatch.setattr(turn_scheduler, "schedule_accepted", record)
    return asked


async def _settle() -> None:
    try:
        from hub import assigned_task_start
    except ImportError:  # master: nothing starts an assigned task
        return
    await assigned_task_start.settled()


async def _roster(*names) -> None:
    async with async_session_factory() as session:
        for name in names:
            session.add(Agent(id=f"ag-{name}", project_id="proj-test", name=name))
        await session.commit()


async def _pending(task_id=TASK, *, assignee=WORKER, loop_id=None, status="pending") -> str:
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title="Fix the timing test",
                description="It fails under the full suite.",
                status=status,
                assignee=assignee,
                loop_id=loop_id,
            )
        )
        await session.commit()
    return task_id


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


async def test_the_operator_moving_a_task_to_assigned_starts_it(app, auth_headers, scheduled):
    await _roster(WORKER)
    await _pending()

    moved = await app.patch(f"{TASKS}/{TASK}", json={"status": "assigned"}, headers=auth_headers)
    assert moved.status_code == 200, moved.text
    await _settle()

    [entry] = await _entries()
    assert (entry.agent, entry.state, entry.task_id) == (WORKER, "queued", TASK)
    assert entry.origin_type == "operator" and entry.origin_agent is None
    assert TASK in entry.content and 'update_task("' in entry.content
    assert scheduled == [WORKER]

    again = await app.patch(f"{TASKS}/{TASK}", json={"status": "assigned"}, headers=auth_headers)
    assert again.status_code == 200, again.text
    from hub import assigned_task_start

    await assigned_task_start.start(TASK)
    await _settle()
    assert len(await _entries()) == 1, "a turn already queued for it since it entered assigned"


async def test_a_task_created_assigned_starts_and_a_new_assignee_starts_it_again(
    app, auth_headers, scheduled
):
    await _roster(WORKER, "other")
    created = await app.post(
        TASKS,
        json={"id": TASK, "title": "Fix it", "status": "assigned", "assignee": WORKER},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    await _settle()
    assert [e.agent for e in await _entries()] == [WORKER]

    handed = await app.patch(f"{TASKS}/{TASK}", json={"assignee": "other"}, headers=auth_headers)
    assert handed.status_code == 200, handed.text
    await _settle()
    assert sorted(e.agent for e in await _entries()) == ["other", WORKER]


async def test_an_agents_run_moving_a_task_to_assigned_starts_it_as_the_agents(
    app, auth_headers, scheduled
):
    await _roster(WORKER, "lead")
    await _pending()
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-lead",
                project_id="proj-test",
                agent="lead",
                status="running",
                turn_depth=2,
                capability_token_hash=hash_run_token("aw_run_lead-secret"),
            )
        )
        await session.commit()

    moved = await app.patch(
        AGENT_TASKS.format(TASK),
        json={"status": "assigned"},
        headers={"Authorization": "Bearer aw_run_lead-secret"},
    )
    assert moved.status_code == 200, moved.text
    await _settle()

    [entry] = await _entries()
    assert (entry.agent, entry.origin_type, entry.origin_agent) == (WORKER, "agent", "lead")
    assert entry.hop_depth == 3, "an agent's message is one hop past its run"
    assert scheduled == [WORKER]


async def test_a_pending_task_and_a_flows_task_are_untouched(app, auth_headers, scheduled):
    await _roster(WORKER)
    created = await app.post(
        TASKS, json={"id": TASK, "title": "Later", "assignee": WORKER}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    async with async_session_factory() as session:
        session.add(
            AIJob(
                id="job-flow",
                project_id="proj-test",
                name="flow",
                agent=WORKER,
                message="work",
                cron="*/5 * * * *",
                session_mode="new",
                enabled=False,
            )
        )
        await session.flush()
        session.add(Loop(id="loop-flow", project_id="proj-test", job_id="job-flow", purpose="x"))
        await session.commit()
    await _pending("task-a55a00000002", loop_id="loop-flow")
    moved = await app.patch(
        f"{TASKS}/task-a55a00000002", json={"status": "assigned"}, headers=auth_headers
    )
    assert moved.status_code == 200, moved.text
    await _settle()
    await stalls.sweep()

    assert await _entries() == [] and await _entries("task-a55a00000002") == []
    assert scheduled == []


async def test_the_sweep_starts_what_was_missed_and_not_what_was_delivered(app, scheduled):
    await _roster(WORKER, "second")
    await _pending(status="assigned")  # written straight into assigned: no nudge reached it
    await _pending("task-a55a00000003", assignee="second", status="assigned")
    entered = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with async_session_factory() as session:
        session.add(
            TaskTransition(
                id="ttr-entered",
                project_id="proj-test",
                task_id="task-a55a00000003",
                from_status="pending",
                to_status="assigned",
                actor_kind="operator",
                origin="actor",
                created_at=entered,
            )
        )
        session.add(
            InboundQueueEntry(
                id="entry-delivered",
                project_id="proj-test",
                agent="second",
                origin_type="operator",
                content="work it",
                hop_depth=0,
                task_id="task-a55a00000003",
                state="delivered",
                arrived_at=entered + timedelta(minutes=1),
            )
        )
        await session.commit()

    await stalls.sweep()
    await _settle()

    [entry] = await _entries()
    assert entry.agent == WORKER and entry.state == "queued"
    assert [e.id for e in await _entries("task-a55a00000003")] == ["entry-delivered"]
    assert scheduled == [WORKER]


async def test_a_withdrawn_turn_is_not_queued_again_by_every_sweep(app, auth_headers, scheduled):
    """Review of slice M: the Hub withdraws an entry after its delivery attempts run out (or at once
    on an unretryable failure, F489), and the operator can withdraw one. The sweep re-queued a turn
    and a new conversation every 300 s, forever. A task starts at most once per entry into
    `assigned`; moving it there again starts it again."""
    await _roster(WORKER)
    await _pending()
    moved = await app.patch(f"{TASKS}/{TASK}", json={"status": "assigned"}, headers=auth_headers)
    assert moved.status_code == 200, moved.text
    await _settle()
    async with async_session_factory() as session:
        [entry] = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.task_id == TASK)
                )
            )
            .scalars()
            .all()
        )
        entry.state = "withdrawn"
        entry.withdrawn_at = datetime.now(timezone.utc)
        entry.abandoned_reason = "delivery attempts exhausted"
        await session.commit()

    counts = []
    for _ in range(3):
        await stalls.sweep()
        await _settle()
        counts.append(len(await _entries()))
    assert counts == [1, 1, 1]

    for status in ("pending", "assigned"):
        again = await app.patch(f"{TASKS}/{TASK}", json={"status": status}, headers=auth_headers)
        assert again.status_code == 200, again.text
    await _settle()
    assert sorted(e.state for e in await _entries()) == ["queued", "withdrawn"]
