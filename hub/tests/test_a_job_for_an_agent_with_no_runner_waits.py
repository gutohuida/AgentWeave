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
