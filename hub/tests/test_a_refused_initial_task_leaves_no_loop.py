"""F414: a loop whose `initial_tasks` holds a task the Hub refuses is not created at all.

F265 moved the *authorisation* refusal ahead of the first commit, but `create_job` still committed
the job and its loop, enabled, and then created the initial tasks one at a time through
`create_task_for_actor` — which refuses per task (an unknown requirement, an id already taken). A refusal on the second task answered 4xx over an enabled loop holding the first:
the half-created loop F265 described, through a second door.

Each case puts the refused task **second**, so a fix that checks only the first entry, or that
creates tasks as it checks them, still leaves a row behind and fails here.
"""

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, Task

JOBS = "/api/v1/projects/proj-test/jobs"


def _loop_body(second_task: dict) -> dict:
    return {
        "name": "Seeded Loop",
        "agent": "kimi",
        "message": "work the queue",
        "cron": "0 2 * * *",
        "stop_when_queue_empties": True,
        "initial_tasks": [{"title": "First task"}, second_task],
    }


async def _counts() -> dict:
    async with async_session_factory() as session:
        return {
            model.__name__: await session.scalar(select(func.count()).select_from(model))
            for model in (AIJob, Loop, Task)
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("second_task", "expected_status", "names"),
    [
        # `resolve_identifiers`: this project declares no requirements at all.
        ({"title": "Second task", "requirement_ids": ["FR-99"]}, 422, "FR-99"),
        # A task cannot be born `approved`. `TaskCreate`'s own validator refuses this before any
        # row is written, so it never half-created; kept so the refusal keeps naming the entry.
        ({"title": "Second task", "status": "approved"}, 422, "'approved'"),
        # Two entries naming one id: the second insert collides with the first.
        ({"title": "Second task", "id": "task-seed-1"}, 409, "task-seed-1"),
    ],
    ids=["unknown-requirement", "non-entry-status", "duplicate-id"],
)
async def test_a_refused_second_initial_task_creates_no_job_loop_or_task(
    app, auth_headers, second_task, expected_status, names
):
    body = _loop_body(second_task)
    if second_task.get("id"):
        body["initial_tasks"][0]["id"] = second_task["id"]

    refused = await app.post(JOBS, json=body, headers=auth_headers)

    assert refused.status_code == expected_status, refused.text
    assert await _counts() == {"AIJob": 0, "Loop": 0, "Task": 0}
    detail = refused.json()["detail"]
    assert "initial_tasks[1]" in detail and names in detail
    assert "Nothing was created" in detail


@pytest.mark.asyncio
async def test_an_initial_task_id_already_on_the_board_creates_nothing(app, auth_headers):
    taken = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"id": "task-taken", "title": "Already here"},
        headers=auth_headers,
    )
    assert taken.status_code == 201, taken.text

    refused = await app.post(
        JOBS, json=_loop_body({"title": "Second task", "id": "task-taken"}), headers=auth_headers
    )

    assert refused.status_code == 409, refused.text
    assert await _counts() == {"AIJob": 0, "Loop": 0, "Task": 1}
    detail = refused.json()["detail"]
    assert "initial_tasks[1]" in detail and "task-taken" in detail
    assert "Nothing was created" in detail


@pytest.mark.asyncio
async def test_the_same_loop_without_the_refused_task_is_created(app, auth_headers):
    """The refusal is about the one entry: dropping it creates the loop and seeds the rest."""
    refused = await app.post(
        JOBS,
        json=_loop_body({"title": "Second task", "requirement_ids": ["FR-99"]}),
        headers=auth_headers,
    )
    assert refused.status_code == 422, refused.text

    body = _loop_body({"title": "Second task"})
    created = await app.post(JOBS, json=body, headers=auth_headers)

    assert created.status_code == 201, created.text
    assert created.json()["loop"]["queue"] == {"pending": 2}
    assert await _counts() == {"AIJob": 1, "Loop": 1, "Task": 2}
