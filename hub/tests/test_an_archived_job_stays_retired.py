"""F222: an archived job cannot be switched back on, or fired.

Archiving hides a job and its loop from the default listings. `PATCH {"enabled": true}` on one used
to answer 200 and register it with the scheduler while it stayed hidden, and the archived loop then
claimed a task and spent a real turn on it — measured live, 0.4 s after the archive.
"""

from __future__ import annotations

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import AIJob

JOBS = "/api/v1/projects/proj-test/jobs"


async def _archived_loop_job(app, auth_headers, name: str) -> str:
    created = await app.post(
        JOBS,
        json={
            "name": name,
            "agent": "kimi",
            "message": "Work the queue",
            "cron": "0 9 * * *",
            "purpose": "F222 retired loop",
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]
    archived = await app.post(f"{JOBS}/{job_id}/archive", headers=auth_headers)
    assert archived.status_code == 200, archived.text
    return job_id


@pytest.mark.asyncio
async def test_re_enabling_an_archived_job_is_refused(app, auth_headers):
    job_id = await _archived_loop_job(app, auth_headers, "F222 Re-enable")

    refused = await app.patch(f"{JOBS}/{job_id}", json={"enabled": True}, headers=auth_headers)

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "job_archived"
    assert "new job" in detail["message"]
    after = await app.get(f"{JOBS}/{job_id}", headers=auth_headers)
    assert after.json()["enabled"] is False


@pytest.mark.asyncio
async def test_firing_an_archived_job_is_refused_as_archived(app, auth_headers):
    """Not "Job is disabled": that names a remedy the guard above refuses."""
    job_id = await _archived_loop_job(app, auth_headers, "F222 Run")

    refused = await app.post(f"{JOBS}/{job_id}/run", headers=auth_headers)

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "job_archived"


@pytest.mark.asyncio
async def test_a_row_left_enabled_and_archived_does_not_fire(app, auth_headers):
    """A Hub before this fix could leave both set; the manual-fire route refuses that row too."""
    job_id = await _archived_loop_job(app, auth_headers, "F222 Legacy Row")
    async with async_session_factory() as db:
        row = await db.get(AIJob, job_id)
        row.enabled = True
        await db.commit()

    refused = await app.post(f"{JOBS}/{job_id}/run", headers=auth_headers)

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "job_archived"


@pytest.mark.asyncio
async def test_a_paused_job_that_is_not_archived_still_re_enables(app, auth_headers):
    created = await app.post(
        JOBS,
        json={"name": "F222 Control", "agent": "kimi", "message": "x", "cron": "0 9 * * *"},
        headers=auth_headers,
    )
    job_id = created.json()["id"]
    paused = await app.patch(f"{JOBS}/{job_id}", json={"enabled": False}, headers=auth_headers)
    assert paused.status_code == 200, paused.text

    resumed = await app.patch(f"{JOBS}/{job_id}", json={"enabled": True}, headers=auth_headers)

    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["enabled"] is True


@pytest.mark.asyncio
async def test_a_restart_does_not_register_a_row_left_enabled_and_archived(app, auth_headers):
    from hub.scheduler import JobScheduler

    job_id = await _archived_loop_job(app, auth_headers, "F222 Restart")
    async with async_session_factory() as db:
        row = await db.get(AIJob, job_id)
        row.enabled = True
        await db.commit()

    scheduler = JobScheduler()
    loaded: list[str] = []

    async def record(job: AIJob) -> bool:
        loaded.append(job.id)
        return True

    scheduler.add_job = record  # type: ignore[method-assign]
    await scheduler.start()
    try:
        assert job_id not in loaded
    finally:
        await scheduler.shutdown()
