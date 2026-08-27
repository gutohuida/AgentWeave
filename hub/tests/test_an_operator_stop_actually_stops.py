"""A loop the operator stops must stop firing, not merely read as stopped.

Measured on the trial Hub, 2026-08-28. `PATCH /jobs/{id}` with a `stop_reason` set
`loop.ending_state = "stopped"` and nothing else. From that second the loop reported itself
stopped, refused new queue items with *"This loop stopped … and its queue is closed"* — and went
on firing once a minute, twelve more real agent turns over seventeen minutes, every one recorded
`completed`. The one fact that decides whether a loop runs, `job.enabled`, was the one the ending
did not touch.

`stopped_at` was the same omission's quieter half: left NULL, so both refusals that quote it fell
back to the literal `"an unknown time"` for an ending the Hub had itself performed a minute before.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop

pytestmark = pytest.mark.asyncio


async def _loop_job(app, auth_headers, **overrides):
    payload = {
        "name": "Nightly Loop",
        "agent": "kimi",
        "message": "work the queue",
        "cron": "*/5 * * * *",
        "enabled": True,
        "purpose": "keep developing",
        "stop_when_queue_empties": True,
    }
    payload.update(overrides)
    resp = await app.post("/api/v1/projects/proj-test/jobs", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _rows(job_id):
    async with async_session_factory() as session:
        job = await session.get(AIJob, job_id)
        loop = (
            await session.execute(select(Loop).where(Loop.job_id == job_id))
        ).scalar_one_or_none()
        return job, loop


async def test_an_operator_stop_disables_the_job(app, auth_headers):
    """The assertion that separates this fix from doing nothing."""
    job_id = await _loop_job(app, auth_headers)

    stopped = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"stop_reason": "I am done with this one"},
        headers=auth_headers,
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["enabled"] is False

    job, loop = await _rows(job_id)
    assert job.enabled is False
    assert loop.ending_state == "stopped"
    assert loop.stop_reason == "I am done with this one"


async def test_an_operator_stop_records_when_it_happened(app, auth_headers):
    """`stopped_at` is what two separate refusals print; NULL made them say "an unknown time"."""
    job_id = await _loop_job(app, auth_headers)

    stopped = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"stop_reason": "enough"},
        headers=auth_headers,
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["loop"]["stopped_at"] is not None

    _, loop = await _rows(job_id)
    assert loop.stopped_at is not None


async def test_a_stopped_loop_names_the_time_when_it_refuses_new_work(app, auth_headers):
    """The refusal's own text, which is where an operator meets this fact."""
    job_id = await _loop_job(app, auth_headers)
    _, loop = await _rows(job_id)
    loop_id = loop.id

    await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"stop_reason": "enough"},
        headers=auth_headers,
    )

    refused = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "one more thing", "loop_id": loop_id},
        headers=auth_headers,
    )
    assert refused.status_code == 403, refused.text
    detail = refused.json()["detail"]
    assert detail["stopped_at"] is not None
    assert "an unknown time" not in detail["message"]


async def test_editing_a_loop_without_stopping_it_leaves_it_running(app, auth_headers):
    """Ending is what `stop_reason` means; the other loop fields must not imply one."""
    job_id = await _loop_job(app, auth_headers)

    edited = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"purpose": "keep developing, but better"},
        headers=auth_headers,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["enabled"] is True

    job, loop = await _rows(job_id)
    assert job.enabled is True
    assert loop.ending_state is None
    assert loop.stopped_at is None


async def test_a_second_stop_reason_does_not_overwrite_the_recorded_ending_state(app, auth_headers):
    """Editing the prose afterwards is not a new governance fact."""
    job_id = await _loop_job(app, auth_headers)
    await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"stop_reason": "enough"},
        headers=auth_headers,
    )
    async with async_session_factory() as session:
        loop = (await session.execute(select(Loop).where(Loop.job_id == job_id))).scalar_one()
        loop.ending_state = "completed"
        await session.commit()

    await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"stop_reason": "actually, it finished"},
        headers=auth_headers,
    )
    _, loop = await _rows(job_id)
    assert loop.ending_state == "completed"
    assert loop.stop_reason == "actually, it finished"


async def test_a_bare_job_with_no_loop_is_untouched_by_the_ending_path(app, auth_headers):
    """`stop_reason` on a job that is not a loop is a 400, not a silent disable."""
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Plain Job",
            "agent": "kimi",
            "message": "ping",
            "cron": "0 9 * * *",
            "enabled": True,
        },
        headers=auth_headers,
    )
    job_id = resp.json()["id"]

    attempted = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"stop_reason": "stop"},
        headers=auth_headers,
    )
    assert attempted.status_code == 400, attempted.text

    job, _ = await _rows(job_id)
    assert job.enabled is True
