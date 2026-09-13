"""F351: the scheduler's job store must not share the database with the requests it serves.

Operator, 2026-09-13: *"An agent created a flow with a loop it should fire every 5 minutes but it
didn't fire at all."* The store was APScheduler's `SQLAlchemyJobStore` on a second, synchronous
engine pointed at the Hub's SQLite file, driven synchronously on the event loop. Another session
holding a write lock at registration needs one more `await` to commit — which the blocked loop
cannot give it — so registration waited out the 5 s busy timeout and lost the job.

`test_job_reaches_the_scheduler.py` could not see this: its scheduler is a recording stand-in that
takes no lock, so every assertion it makes is about the calling session. These use the real
`JobScheduler.start()` against the suite's file-backed database, with a real concurrent writer —
the stand-in must take the locks the real thing takes (DEAD-ENDS, F328).
"""

import asyncio
import time

import pytest
from sqlalchemy import text

import hub.scheduler as scheduler_module
from hub.api.v1.jobs import _hand_job_to_scheduler
from hub.db.engine import async_session_factory
from hub.db.models import AIJob

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def live_scheduler(app, monkeypatch):
    # `app` builds the schema; it does not run the lifespan, so it starts no scheduler of its own.
    scheduler = scheduler_module.JobScheduler()
    await scheduler.start()
    monkeypatch.setattr(scheduler_module, "_scheduler_instance", scheduler)
    try:
        yield scheduler
    finally:
        await scheduler.shutdown()


async def _enabled_job(job_id: str) -> AIJob:
    async with async_session_factory() as db:
        job = AIJob(
            id=job_id,
            project_id="proj-test",
            name=job_id,
            agent="dev",
            message="work the queue",
            cron="*/5 * * * *",
            session_mode="new",
            enabled=True,
            source="hub",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job


async def test_a_job_registers_while_another_session_holds_the_write_lock(live_scheduler):
    """The reproduction. Before the fix this took 5.5 s and registered nothing."""
    job = await _enabled_job("job-f351-lock")
    writer_holds_lock = asyncio.Event()
    release = asyncio.Event()

    async def other_writer():
        # Any request or run mid-write: it holds the lock and needs the loop again to commit.
        async with async_session_factory() as s:
            await s.execute(text("create table if not exists f351_scratch (x int)"))
            await s.execute(text("insert into f351_scratch values (1)"))
            writer_holds_lock.set()
            await release.wait()
            await s.commit()

    writer = asyncio.create_task(other_writer())
    await writer_holds_lock.wait()
    try:
        async with async_session_factory() as session:
            started = time.perf_counter()
            await _hand_job_to_scheduler(session, job.id, job)
            elapsed = time.perf_counter() - started
    finally:
        release.set()
        await writer

    assert (
        live_scheduler.scheduler.get_job(job.id) is not None
    ), "the job never reached the scheduler"
    assert elapsed < 1.0, f"registration waited {elapsed:.2f}s on a lock it should not need"


async def test_the_scheduler_keeps_its_jobs_out_of_the_database(live_scheduler):
    """Firing writes the store too (`_process_jobs` → `update_job`, unguarded), and a lock there
    stopped the scheduler waking for every job. Only a store with no database access rules out both
    halves, so that is the property pinned — not merely that one call site got luckier."""
    from apscheduler.jobstores.memory import MemoryJobStore

    store = live_scheduler.scheduler._lookup_jobstore("default")
    assert isinstance(store, MemoryJobStore)


async def test_a_restart_re_registers_every_enabled_job_from_the_database(app):
    """What the database store used to provide is kept: `ai_jobs` is the record, and `start()` reads
    it. A job registered before a restart is scheduled after it."""
    job = await _enabled_job("job-f351-restart")
    async with async_session_factory() as db:
        disabled = AIJob(
            id="job-f351-disabled",
            project_id="proj-test",
            name="off",
            agent="dev",
            message="m",
            cron="*/5 * * * *",
            session_mode="new",
            enabled=False,
            source="hub",
        )
        db.add(disabled)
        await db.commit()

    scheduler = scheduler_module.JobScheduler()
    await scheduler.start()
    try:
        assert scheduler.scheduler.get_job(job.id) is not None
        assert scheduler.scheduler.get_job("job-f351-disabled") is None
    finally:
        await scheduler.shutdown()
