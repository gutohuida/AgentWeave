"""`run-id-in-an-event-always-names-a-run` — an event's `run_id` names a `Run`; a `JobRun` id
travels as `job_run_id`, in the SSE broadcast, the persisted payload and the Run route's answer.

Tasks 1.1-1.4. Each fails on the code before the rename (the key was `run_id`).
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Agent, AIJob, EventLog, JobRun, Run
from hub.scheduler import JobScheduler

from .test_a_task_nothing_will_move_holds_nobody import _no_spawn
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"


@pytest.fixture
def live_scheduler(monkeypatch):
    import hub.scheduler as scheduler_module

    instance = JobScheduler()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: instance)
    return instance


async def _job(suffix, agent):
    async with async_session_factory() as db:
        job = AIJob(
            id=f"job-runid-{suffix}",
            project_id=PROJECT,
            name=f"RunId {suffix}",
            agent=agent,
            message="do the thing",
            cron="*/5 * * * *",
            session_mode="new",
            enabled=True,
        )
        db.add(job)
        await db.commit()
        return job


async def _press(app, auth_headers, job):
    return await app.post(f"/api/v1/projects/{PROJECT}/jobs/{job.id}/run", headers=auth_headers)


async def _events(event_type):
    async with async_session_factory() as db:
        rows = await db.execute(
            select(EventLog).where(
                EventLog.project_id == PROJECT, EventLog.event_type == event_type
            )
        )
        return [row.data for row in rows.scalars().all()]


async def _job_run_ids(job_id):
    async with async_session_factory() as db:
        rows = await db.execute(select(JobRun.id).where(JobRun.job_id == job_id))
        return list(rows.scalars().all())


async def test_a_fired_job_names_its_job_run(
    app, auth_headers, bind_runner, live_scheduler, monkeypatch
):
    """1.1 — the answer, the persisted `job_fired` and its broadcast."""
    from hub.sse import sse_manager

    seen = []
    real = sse_manager.broadcast

    async def capture(project_id, event_type, data, *args, **kwargs):
        seen.append((event_type, data))
        return await real(project_id, event_type, data, *args, **kwargs)

    monkeypatch.setattr(sse_manager, "broadcast", capture)
    await _roster(app, auth_headers, bind_runner, "runid-a")
    job = await _job("fired", "runid-a")
    with _no_spawn():
        res = await _press(app, auth_headers, job)
    assert res.status_code == 200, res.text
    (job_run_id,) = await _job_run_ids(job.id)
    body = res.json()
    assert body["job_run_id"] == job_run_id
    assert "run_id" not in body
    (persisted,) = [d for d in await _events("job_fired") if d.get("job_id") == job.id]
    assert persisted["job_run_id"] == job_run_id
    assert "run_id" not in persisted
    broadcast = [d for t, d in seen if t == "job_fired" and d.get("id") == job.id]
    assert broadcast and all(d["job_run_id"] == job_run_id and "run_id" not in d for d in broadcast)


async def test_a_skipped_job_names_its_job_run(app, auth_headers, live_scheduler):
    """1.2."""
    async with async_session_factory() as db:
        db.add(
            Agent(
                project_id=PROJECT,
                id="agent-runid-poll",
                name="runid-poll",
                self_registered=True,
                contact_mode="poll",
            )
        )
        await db.commit()
    job = await _job("skipped", "runid-poll")
    await _press(app, auth_headers, job)
    (job_run_id,) = await _job_run_ids(job.id)
    (persisted,) = [d for d in await _events("job_run_skipped") if d["job_id"] == job.id]
    assert persisted["job_run_id"] == job_run_id
    assert "run_id" not in persisted


async def test_a_failed_press_names_its_job_run(app, auth_headers, live_scheduler):
    """1.3 — `_record_job_run_failure`, reached when the scheduler raises."""
    job = await _job("failed", "runid-boom")
    with patch.object(JobScheduler, "_fire_job_internal", AsyncMock(side_effect=RuntimeError("x"))):
        res = await _press(app, auth_headers, job)
    assert res.status_code == 500, res.text
    (job_run_id,) = await _job_run_ids(job.id)
    (persisted,) = [d for d in await _events("job_run_failed") if d["job_id"] == job.id]
    assert persisted["job_run_id"] == job_run_id
    assert "run_id" not in persisted


async def test_every_run_id_in_the_stream_names_a_run(
    app, auth_headers, bind_runner, live_scheduler
):
    """1.4 — the stream rule, after a job firing."""
    await _roster(app, auth_headers, bind_runner, "runid-b")
    job = await _job("stream", "runid-b")
    with _no_spawn():
        await _press(app, auth_headers, job)
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(EventLog).where(EventLog.project_id == PROJECT)))
            .scalars()
            .all()
        )
        named = {
            r.data["run_id"] for r in rows if isinstance(r.data, dict) and r.data.get("run_id")
        }
        real = set((await db.execute(select(Run.id).where(Run.id.in_(named)))).scalars().all())
    assert named == real


async def test_a_wide_firing_names_a_job_run_on_every_job_fired(app, auth_headers, bind_runner):
    """1.5 — the primary's `job_fired` and the extra selection's."""
    from .test_flow_width import OWNER, SECOND, _flow, _task

    await _roster(app, auth_headers, bind_runner, OWNER, SECOND)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="runid-wide")
        await _task(db, loop, "runid-wide-a")
        await _task(db, loop, "runid-wide-b")
    async with async_session_factory() as db:
        await JobScheduler()._fire_job_internal(
            await db.get(AIJob, job.id), trigger="scheduled", session=db
        )
    job_run_ids = set(await _job_run_ids(job.id))
    fired = [d for d in await _events("job_fired") if d["job_id"] == job.id]
    assert len(fired) == 2
    assert {d["job_run_id"] for d in fired} == job_run_ids
    assert all("run_id" not in d for d in fired)
