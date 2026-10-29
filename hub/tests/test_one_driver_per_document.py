# ruff: noqa: F401, F811
"""F1083: a document whose build is running takes no second driver.

`ac-one-driver`: with a running hand build, `create_flow` on the document is refused 409 naming the
build and its driver, creates no job or loop, and leaves the tasks without a loop.
`ac-build-flow-still-made`: the build's own flow is still created, and its tasks carry its loop.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, Project

from .test_a_build_has_a_driver_a_level_and_its_people import (
    PATH,
    _approved,
    _build,
    _document,
    _roster_rows,
    _rows,
    _tasks_by_key,
    author_headers,
)

JOBS = "/api/v1/agent-actions/jobs"


def _flow_request(document_id):
    return {
        "name": "second driver",
        "agent": "dev",
        "message": "Work the queue",
        "cron": "*/10 * * * *",
        "spec_document_id": document_id,
        "stop_when_queue_empties": True,
    }


@pytest.mark.asyncio
async def test_a_second_driver_is_refused_while_a_build_runs(app, auth_headers, author_headers):
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    built = await _build(app, auth_headers, driver="hand", level="fast")
    assert built.status_code == 200, built.text
    build_id = built.json()["build_outcome"]["build"]["id"]
    tasks = await _tasks_by_key()
    assert {t.loop_id for t in tasks.values()} == {None}

    async with async_session_factory() as db:
        (await db.get(Project, "proj-test")).allow_agent_jobs = True
        await db.commit()

    refused = await app.post(JOBS, json=_flow_request(PATH), headers=author_headers)

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert build_id in detail and "hand" in detail
    assert await _rows(Loop) == []
    assert await _rows(AIJob) == []
    assert {t.loop_id for t in (await _tasks_by_key()).values()} == {None}


@pytest.mark.asyncio
async def test_the_builds_own_flow_is_still_created(app, auth_headers, author_headers):
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    built = await _build(app, auth_headers, driver="flow", level="reviewed")
    assert built.status_code == 200, built.text

    (loop,) = await _rows(Loop)
    tasks = await _tasks_by_key()
    assert tasks and {t.loop_id for t in tasks.values()} == {loop.id}
    async with async_session_factory() as db:
        assert (await db.execute(select(AIJob))).scalars().first() is not None
