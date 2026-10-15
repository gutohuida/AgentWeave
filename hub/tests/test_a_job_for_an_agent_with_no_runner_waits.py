"""F596: a job fired at an agent with no runner is a wait, not a failure.

The firing queues its message and the inbound queue keeps it for the operator to bind a runner
(F96: binding one delivers it). The job's own record used to say `failed` and the press answered
500 for work that then ran. The firing is now `in_progress` and the press answers 200 with the
reason it waits, resolved by the run that delivers the entry.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, JobRun
from hub.scheduler import JobScheduler

from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/projects/proj-test"
# The roster fixture keeps a legacy runner entry, so the probe has no sentence of its own here; a
# real Hub says "No runner is bound to this agent". Both come from the same `runner_id is None` branch.
WAITS_FOR = ("No runner is bound", "is not currently launchable", "was not found in PATH")


@pytest.fixture
def live_scheduler(monkeypatch):
    import hub.scheduler as scheduler_module

    instance = JobScheduler()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: instance)
    return instance


async def _unbound_agent_job(app, auth_headers, bind_runner, agent):
    await _roster(app, auth_headers, bind_runner, agent)
    created = await app.post(
        f"{BASE}/jobs",
        json={
            "name": f"job-{agent}",
            "agent": agent,
            "cron": "0 0 1 1 *",
            "enabled": True,
            "message": "Reply OK.",
        },
        headers=auth_headers,
    )
    assert created.status_code in (200, 201), created.text
    unbound = await app.patch(
        f"{BASE}/agents/{agent}", json={"runner_id": None}, headers=auth_headers
    )
    assert unbound.status_code == 200, unbound.text
    return created.json()["id"]


async def test_a_press_for_an_agent_with_no_runner_waits(
    app, auth_headers, bind_runner, live_scheduler
):
    job_id = await _unbound_agent_job(app, auth_headers, bind_runner, "norunner596")

    res = await app.post(f"{BASE}/jobs/{job_id}/run", headers=auth_headers)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert any(text in body["waiting_reason"] for text in WAITS_FOR), body["waiting_reason"]

    async with async_session_factory() as db:
        rows = (await db.execute(select(JobRun).where(JobRun.job_id == job_id))).scalars().all()
        entries = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "norunner596")
                )
            )
            .scalars()
            .all()
        )
    # The message is kept and the firing says it is still pending, not that it failed.
    assert [r.status for r in rows] == ["in_progress"]
    assert rows[0].error_summary is None
    assert [e.state for e in entries] == ["queued"]


async def test_withdrawing_a_waiting_firings_message_stops_the_firing(
    app, auth_headers, bind_runner, live_scheduler
):
    """F625: withdrawing the entry left the firing `in_progress` forever, even once the job was
    archived. With nothing left to deliver and no run, the firing is over: `stopped`, naming why."""
    job_id = await _unbound_agent_job(app, auth_headers, bind_runner, "withdrawn625")
    assert (await app.post(f"{BASE}/jobs/{job_id}/run", headers=auth_headers)).status_code == 200
    async with async_session_factory() as db:
        (entry,) = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "withdrawn625")
                )
            )
            .scalars()
            .all()
        )

    withdrawn = await app.delete(f"{BASE}/queue/entries/{entry.id}", headers=auth_headers)

    assert withdrawn.status_code == 200, withdrawn.text
    async with async_session_factory() as db:
        rows = (await db.execute(select(JobRun).where(JobRun.job_id == job_id))).scalars().all()
    assert [r.status for r in rows] == ["stopped"]
    assert "withdrawn" in rows[0].error_summary


async def test_archiving_a_job_closes_a_firing_left_with_nothing_to_deliver(
    app, auth_headers, bind_runner, live_scheduler
):
    """A firing orphaned before the withdrawal closed it (live data) is closed by the archive."""
    job_id = await _unbound_agent_job(app, auth_headers, bind_runner, "orphan625")
    assert (await app.post(f"{BASE}/jobs/{job_id}/run", headers=auth_headers)).status_code == 200
    async with async_session_factory() as db:
        entry = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "orphan625")
                )
            )
            .scalars()
            .one()
        )
        entry.state = "withdrawn"  # as a Hub before this fix left it
        await db.commit()

    archived = await app.post(f"{BASE}/jobs/{job_id}/archive", headers=auth_headers)

    assert archived.status_code == 200, archived.text
    async with async_session_factory() as db:
        rows = (await db.execute(select(JobRun).where(JobRun.job_id == job_id))).scalars().all()
    assert [r.status for r in rows] == ["stopped"]


async def test_a_firing_whose_message_still_waits_is_left_in_progress_by_the_archive(
    app, auth_headers, bind_runner, live_scheduler
):
    job_id = await _unbound_agent_job(app, auth_headers, bind_runner, "kept625")
    assert (await app.post(f"{BASE}/jobs/{job_id}/run", headers=auth_headers)).status_code == 200

    await app.post(f"{BASE}/jobs/{job_id}/archive", headers=auth_headers)

    async with async_session_factory() as db:
        rows = (await db.execute(select(JobRun).where(JobRun.job_id == job_id))).scalars().all()
    assert [r.status for r in rows] == ["in_progress"]
