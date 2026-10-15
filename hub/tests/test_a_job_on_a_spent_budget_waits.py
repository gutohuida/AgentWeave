"""F608: a job fired on a spent token budget is a wait, not a failure.

The budget holds autonomous input until the operator raises it, and the held entry then runs. The
job's own record used to say `failed` and the press answered 500 for work that later ran -- F596's
defect, through a different refusal. The firing is now `in_progress` and the press answers 200
with the reason it waits.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, JobRun, Project, Run, TurnUsage
from hub.scheduler import JobScheduler

from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/projects/proj-test"


@pytest.fixture
def live_scheduler(monkeypatch):
    import hub.scheduler as scheduler_module

    instance = JobScheduler()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: instance)
    return instance


async def _spend_the_budget():
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.token_budget = 100
        db.add(Run(id="run-spent-608", project_id="proj-test", agent="history", status="completed"))
        db.add(
            TurnUsage(
                id="usage-spent-608",
                project_id="proj-test",
                run_id="run-spent-608",
                agent="history",
                status="measured",
                input_tokens=500,
                output_tokens=0,
                total_tokens=500,
            )
        )
        await db.commit()


async def test_a_press_on_a_spent_budget_waits_and_keeps_the_message(
    app, auth_headers, bind_runner, live_scheduler
):
    await _roster(app, auth_headers, bind_runner, "spent608")
    created = await app.post(
        f"{BASE}/jobs",
        json={
            "name": "job-spent608",
            "agent": "spent608",
            "cron": "0 0 1 1 *",
            "enabled": True,
            "message": "Reply OK.",
        },
        headers=auth_headers,
    )
    assert created.status_code in (200, 201), created.text
    job_id = created.json()["id"]
    await _spend_the_budget()

    with patch("hub.api.v1.agent_trigger.PtySession.spawn") as spawn:
        res = await app.post(f"{BASE}/jobs/{job_id}/run", headers=auth_headers)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["waiting_reason"] == "token budget exhausted"
    spawn.assert_not_called()

    async with async_session_factory() as db:
        rows = (await db.execute(select(JobRun).where(JobRun.job_id == job_id))).scalars().all()
        entries = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "spent608")
                )
            )
            .scalars()
            .all()
        )
    assert [r.status for r in rows] == ["in_progress"]
    assert rows[0].error_summary is None
    assert [e.state for e in entries] == ["queued"]
