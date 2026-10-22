"""F925: a job naming an agent that is gone (removed by a session sync, or archived) queues nothing.

Job create checked the roster and `PATCH {"enabled": true}` did not, so a job could be switched on
for an agent a sync had deleted. Its firing queued an entry and opened a conversation *before* the
trigger refused the name, the press answered 500, and the next agent of that name received the
dead firing's message and ran it. The firing now refuses first: a `failed` row and its event, no
entry, no conversation; the press says 409 with the reason.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Conversation, EventLog, InboundQueueEntry, JobRun
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


async def _job_for(app, auth_headers, bind_runner, agent):
    """A disabled job naming *agent*, on a roster that also holds two agents that stay."""
    await _roster(app, auth_headers, bind_runner, "stays1", "stays2", agent)
    created = await app.post(
        f"{BASE}/jobs",
        json={
            "name": f"job-{agent}",
            "agent": agent,
            "cron": "0 4 * * *",
            "enabled": False,
            "message": "Reply OK.",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _remove_by_sync(app, auth_headers, *keep):
    synced = await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"} for name in keep}}},
        headers=auth_headers,
    )
    assert synced.status_code == 200, synced.text


async def _force_enabled(job_id):
    async with async_session_factory() as db:
        (await db.get(AIJob, job_id)).enabled = True
        await db.commit()


async def _left_behind(agent):
    async with async_session_factory() as db:
        entries = (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == agent)))
            .scalars()
            .all()
        )
        conversations = (
            (await db.execute(select(Conversation).where(Conversation.agent == agent)))
            .scalars()
            .all()
        )
    return entries, conversations


async def _gone(app, auth_headers, bind_runner, how):
    job_id = await _job_for(app, auth_headers, bind_runner, "vanishes")
    if how == "sync":
        await _remove_by_sync(app, auth_headers, "stays1", "stays2")
    else:
        archived = await app.post(f"{BASE}/agents/vanishes/archive", headers=auth_headers)
        assert archived.status_code == 200, archived.text
    return job_id


@pytest.mark.parametrize("how", ["sync", "archive"])
async def test_a_job_for_a_gone_agent_cannot_be_enabled(app, auth_headers, bind_runner, how):
    job_id = await _gone(app, auth_headers, bind_runner, how)

    refused = await app.patch(f"{BASE}/jobs/{job_id}", json={"enabled": True}, headers=auth_headers)

    assert refused.status_code == 400, refused.text
    assert "vanishes" in refused.json()["detail"]
    assert (await app.get(f"{BASE}/jobs/{job_id}", headers=auth_headers)).json()["enabled"] is False


@pytest.mark.parametrize("how", ["sync", "archive"])
async def test_a_press_for_a_gone_agent_queues_nothing_and_says_why(
    app, auth_headers, bind_runner, live_scheduler, add_agent, how
):
    job_id = await _gone(app, auth_headers, bind_runner, how)
    await _force_enabled(job_id)

    pressed = await app.post(f"{BASE}/jobs/{job_id}/run", headers=auth_headers)

    assert pressed.status_code == 409, pressed.text
    assert "vanishes" in pressed.json()["detail"]
    entries, conversations = await _left_behind("vanishes")
    assert entries == []
    assert conversations == []
    async with async_session_factory() as db:
        runs = (await db.execute(select(JobRun).where(JobRun.job_id == job_id))).scalars().all()
        kinds = (
            (
                await db.execute(
                    select(EventLog.event_type).where(EventLog.project_id == "proj-test")
                )
            )
            .scalars()
            .all()
        )
    assert [run.status for run in runs] == ["failed"]
    assert "vanishes" in runs[0].error_summary
    assert "job_run_failed" in kinds
    assert "queue_entry_queued" not in kinds


async def test_a_later_agent_of_the_name_inherits_nothing(
    app, auth_headers, bind_runner, live_scheduler
):
    job_id = await _gone(app, auth_headers, bind_runner, "sync")
    await _force_enabled(job_id)
    await app.post(f"{BASE}/jobs/{job_id}/run", headers=auth_headers)

    await _roster(app, auth_headers, bind_runner, "stays1", "stays2", "vanishes")

    entries, conversations = await _left_behind("vanishes")
    assert entries == []
    assert conversations == []


async def test_a_job_for_a_present_agent_still_fires(
    app, auth_headers, bind_runner, live_scheduler
):
    job_id = await _job_for(app, auth_headers, bind_runner, "present")
    enabled = await app.patch(f"{BASE}/jobs/{job_id}", json={"enabled": True}, headers=auth_headers)
    assert enabled.status_code == 200, enabled.text

    await app.post(f"{BASE}/jobs/{job_id}/run", headers=auth_headers)

    entries, conversations = await _left_behind("present")
    assert len(entries) == 1
    assert len(conversations) == 1
