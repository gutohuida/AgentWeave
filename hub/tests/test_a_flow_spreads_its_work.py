# ruff: noqa: F811 -- `author_headers` is a fixture imported to be requested by name
"""F1112: a fix task the Hub files does not take the build's builder from the build's own work.

On 2026-10-31 a critical fix task went to Developer as the flow's own agent, and QA's send-back of
the build's task then waited for Developer for over half an hour with QA2 free on the builders list.
"""

from datetime import datetime, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Run, Task

from .test_a_build_has_a_driver_a_level_and_its_people import (
    P,
    _approved,
    _build,
    _document,
    _rows,
    _tasks_by_key,
    author_headers,  # noqa: F401 -- a fixture
)
from .test_a_finished_build_leaves_its_flow_working import SCHEDULING, _fire
from .test_review_turn import _roster

TASKS = f"/api/v1/projects/{P}/tasks"


async def _flow(app, auth_headers, author_headers, bind_runner, tasks, builders=("dev", "free")):
    from hub.db.models import Loop

    await _roster(app, auth_headers, bind_runner, "dev", "free", "qa")
    await _approved(app, auth_headers, author_headers, _document(tasks))
    with SCHEDULING:
        built = await _build(
            app, auth_headers, driver="flow", level="fast", builders=list(builders)
        )
    assert built.status_code == 200, built.text
    (loop,) = await _rows(Loop)
    return loop


async def _fix_task(loop, **fields) -> str:
    fields.setdefault("status", "pending")
    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-fix",
                project_id=P,
                title="Fix a flaky test",
                priority="critical",
                loop_id=loop.id,
                **fields,
            )
        )
        await db.commit()
    return "task-fix"


async def _busy(agent: str) -> None:
    async with async_session_factory() as db:
        db.add(
            Run(
                id=f"run-{agent}-busy",
                project_id=P,
                agent=agent,
                status="running",
                turn_depth=0,
            )
        )
        await db.commit()


async def _set(task_id: str, **fields) -> None:
    async with async_session_factory() as db:
        row = await db.get(Task, task_id)
        for key, value in fields.items():
            setattr(row, key, value)
        await db.commit()


async def _assignee(task_id: str):
    async with async_session_factory() as db:
        return (await db.get(Task, task_id)).assignee


@pytest.mark.asyncio
async def test_a_fix_task_goes_to_the_agent_the_build_does_not_need(
    app, auth_headers, author_headers, bind_runner
):
    tasks = [
        {"key": "t1", "description": "Build alpha", "requirements": ["alpha"], "builder": "dev"},
        {"key": "t2", "description": "Build beta", "requirements": ["beta"], "builder": "dev"},
    ]
    loop = await _flow(app, auth_headers, author_headers, bind_runner, tasks)
    await _fix_task(loop)

    await _fire(loop.job_id)

    assert await _assignee("task-fix") == "free"
    assert {t.assignee for t in (await _tasks_by_key()).values()} == {"dev"}


@pytest.mark.asyncio
async def test_a_fix_task_takes_a_builder_when_nobody_else_is_free(
    app, auth_headers, author_headers, bind_runner
):
    """It prefers; a red main still gets somebody rather than waiting on an idle agent."""
    tasks = [
        {"key": "t1", "description": "Build alpha", "requirements": ["alpha"], "builder": "dev"},
        {"key": "t2", "description": "Build beta", "requirements": ["beta"], "builder": "dev"},
    ]
    loop = await _flow(app, auth_headers, author_headers, bind_runner, tasks, builders=("dev",))
    await _fix_task(loop)

    await _fire(loop.job_id)

    assert await _assignee("task-fix") == "dev"


@pytest.mark.asyncio
async def test_a_send_back_outranks_a_fix_task_for_the_same_agent(
    app, auth_headers, author_headers, bind_runner
):
    tasks = [
        {"key": "t1", "description": "Build alpha", "requirements": ["alpha"], "builder": "dev"},
        {"key": "t2", "description": "Build beta", "requirements": ["beta"], "builder": "free"},
    ]
    loop = await _flow(app, auth_headers, author_headers, bind_runner, tasks)
    by_key = await _tasks_by_key()
    await _set(by_key["t1"].id, status="revision_needed", assignee="dev")
    await _set(by_key["t2"].id, status="approved")
    # Touched after the send-back, so the queue's own order reads the fix task first.
    await _fix_task(loop, assignee="dev", status="assigned", updated=datetime.now(timezone.utc))

    await _fire(loop.job_id)

    from hub.db.models import InboundQueueEntry

    briefed = {e.task_id for e in await _rows(InboundQueueEntry)}
    assert by_key["t1"].id in briefed
    assert "task-fix" not in briefed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("declared", "expected"), [(True, "free"), (False, "dev")], ids=["preference", "required"]
)
async def test_an_unstarted_task_moves_only_when_its_builder_is_a_preference(
    app, auth_headers, author_headers, bind_runner, declared, expected
):
    own = {"key": "t1", "description": "Build alpha", "requirements": ["alpha"], "builder": "dev"}
    other = {"key": "t2", "description": "Build beta", "requirements": ["beta"], "builder": "qa"}
    if declared:
        own["builder_is_preference"] = True
    loop = await _flow(app, auth_headers, author_headers, bind_runner, [own, other])
    await _set((await _tasks_by_key())["t2"].id, status="approved")
    await _busy("dev")

    await _fire(loop.job_id)

    assert await _assignee((await _tasks_by_key())["t1"].id) == expected


@pytest.mark.asyncio
async def test_started_work_never_moves_to_a_stand_in(
    app, auth_headers, author_headers, bind_runner
):
    own = {
        "key": "t1",
        "description": "Build alpha",
        "requirements": ["alpha"],
        "builder": "dev",
        "builder_is_preference": True,
    }
    other = {"key": "t2", "description": "Build beta", "requirements": ["beta"], "builder": "qa"}
    loop = await _flow(app, auth_headers, author_headers, bind_runner, [own, other])
    by_key = await _tasks_by_key()
    await _set(by_key["t1"].id, status="revision_needed")
    await _set(by_key["t2"].id, status="approved")
    await _busy("dev")

    await _fire(loop.job_id)

    assert await _assignee(by_key["t1"].id) == "dev"


@pytest.mark.asyncio
async def test_the_board_says_who_a_task_waits_on_and_since_when(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "dev")
    async with async_session_factory() as db:
        db.add_all(
            [
                Task(
                    id="task-waits",
                    project_id=P,
                    title="Waits",
                    status="revision_needed",
                    assignee="dev",
                ),
                Task(
                    id="task-runs",
                    project_id=P,
                    title="Runs",
                    status="in_progress",
                    assignee="dev",
                ),
                Task(id="task-fresh", project_id=P, title="Idle", status="pending", assignee="dev"),
                Run(
                    id="run-on-it",
                    project_id=P,
                    agent="dev",
                    status="running",
                    turn_depth=0,
                    task_id="task-runs",
                ),
            ]
        )
        await db.commit()

    body = (await app.get(TASKS, headers=auth_headers)).json()
    rows = {t["id"]: t for t in (body["tasks"] if isinstance(body, dict) else body)}

    assert rows["task-waits"]["waiting_on"] == "dev"
    assert rows["task-waits"]["waiting_since"] is not None
    assert rows["task-runs"]["waiting_on"] is None
    assert rows["task-fresh"]["waiting_on"] is None
