"""A landing send-back proven on the work restarts its author
(`a-landing-failure-is-blamed-on-a-task-only-when-it-reproduces-there`, FR-7, task
restart-after-landing-send-back).

Real git and a real pytest check, through the fixtures of `test_a_failing_batch_is_narrowed`: the
batch's tasks belong to a loop whose job is off, so no flow owns them and they are hand-started work
as far as AW-148's restart (`send_back_restart`) is concerned. Before this, a landing send-back was
the operator's edge and nobody was queued.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from hub import landing_queue, send_back_restart, turn_scheduler
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AIJob, EventLog, InboundQueueEntry, Task, TaskTransition

from .test_a_failing_batch_is_narrowed import (  # noqa: F401 -- the autouse gather window
    _a_long_gather_window,
    _approve,
    _project,
    _repo,
    _status,
    _tasks,
)

pytestmark = pytest.mark.asyncio

AUTHOR = "builder"


@pytest.fixture
def scheduled(monkeypatch):
    asked: list = []

    async def record(project_id, agent):
        asked.append(agent)
        return SimpleNamespace(waiting_reason=None)

    monkeypatch.setattr(turn_scheduler, "schedule_accepted", record)
    return asked


async def _batch_with_a_regression(app, auth_headers, tmp_path, tmp_path_factory, before=None):
    """Three approved tasks, the second of which breaks the suite; *before* runs once the tasks
    exist and before they are approved."""
    _repo(tmp_path, tmp_path_factory.mktemp("ledger") / "runs.txt")
    await _project()
    async with async_session_factory() as session:
        session.add(Agent(id="ag-builder", project_id="proj-test", name=AUTHOR))
        await session.commit()
    ids, _ = await _tasks(
        tmp_path,
        [
            ({"one.py": "x = 1\n"}, None),
            ({"broken.txt": "this breaks the suite\n"}, None),
            ({"three.py": "x = 3\n"}, None),
        ],
    )
    if before is not None:
        await before(ids)
    for task_id in ids:
        await _approve(app, auth_headers, task_id)
    await landing_queue.drain()
    await send_back_restart.settled()
    assert [await _status(task_id) for task_id in ids] == [
        "approved",
        "revision_needed",
        "approved",
    ]
    return ids


async def _entries(task_id: str) -> list:
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


async def _held(task_id: str) -> list:
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


async def test_a_proven_landing_send_back_queues_the_authors_turn(
    app, auth_headers, tmp_path, tmp_path_factory, scheduled
):
    """ac-author-restarts: the task the batch proved broke the suite is sent back, and its author's
    turn is queued with the send-back's proof, with nobody asked to re-send it."""
    ids = await _batch_with_a_regression(app, auth_headers, tmp_path, tmp_path_factory)

    [entry] = await _entries(ids[1])
    assert (entry.agent, entry.state) == (AUTHOR, "queued")
    async with async_session_factory() as session:
        notes = str((await session.get(Task, ids[1])).notes)
    assert (
        notes.startswith("Landing batch") and notes.splitlines()[0] in entry.content
    ), entry.content
    assert scheduled == [AUTHOR]
    assert await _held(ids[1]) == []
    for landed in (ids[0], ids[2]):
        assert await _entries(landed) == []


async def test_two_review_send_backs_and_a_landing_one_hold_the_author(
    app, auth_headers, tmp_path, tmp_path_factory, scheduled
):
    """ac-cap-shared: two review send-backs with no approval since, then the batch's send-back:
    the third in a row, so the author is not queued and the task is surfaced as held."""

    async def two_review_send_backs(ids):
        async with async_session_factory() as session:
            for index, (before, after, who) in enumerate(
                [
                    ("in_progress", "completed", AUTHOR),
                    ("completed", "under_review", "qa"),
                    ("under_review", "revision_needed", "qa"),
                    ("revision_needed", "completed", AUTHOR),
                    ("completed", "under_review", "qa"),
                    ("under_review", "revision_needed", "qa"),
                    ("revision_needed", "completed", AUTHOR),
                    ("completed", "under_review", "qa"),
                ]
            ):
                session.add(
                    TaskTransition(
                        id=f"ttr-cap{index:02d}",
                        project_id="proj-test",
                        task_id=ids[1],
                        from_status=before,
                        to_status=after,
                        actor_kind="run",
                        actor_agent=who,
                        origin="actor",
                    )
                )
            await session.commit()

    ids = await _batch_with_a_regression(
        app, auth_headers, tmp_path, tmp_path_factory, before=two_review_send_backs
    )

    assert await _entries(ids[1]) == [] and scheduled == []
    [held] = await _held(ids[1])
    assert held.data["send_backs"] == 3 and "3" in held.data["reason"]
    async with async_session_factory() as session:
        assert await send_back_restart.consecutive_send_backs(session, ids[1]) == 3


async def test_a_task_in_a_live_flow_is_left_to_the_flow(
    app, auth_headers, tmp_path, tmp_path_factory, scheduled
):
    """The flow restarts its own tasks: the landing send-back queues nobody for one."""

    async def switch_the_flow_on(_ids):
        async with async_session_factory() as session:
            (await session.get(AIJob, "job-narrow")).enabled = True
            await session.commit()

    ids = await _batch_with_a_regression(
        app, auth_headers, tmp_path, tmp_path_factory, before=switch_the_flow_on
    )

    assert await _entries(ids[1]) == [] and await _held(ids[1]) == []
    assert AUTHOR not in scheduled
