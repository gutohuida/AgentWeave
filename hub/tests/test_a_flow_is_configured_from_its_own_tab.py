"""A loop's default agent is configured from the loop's own tab, and staged like the rest of it.

Change `a-flow-is-configured-from-its-own-tab`, design D2, D3, D7. Before it `PATCH /jobs/{id}`
refused `agent` with a 422, and `LoopSummary` did not say which document a loop declares.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AIJob, EventLog, Loop, Run, Task
from hub.scheduler import JobScheduler, _stage_pending_loop_edit

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/projects/proj-test"


async def _roster(app, auth_headers, *names):
    sync = await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"} for name in names}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text


async def _loop_job(app, auth_headers, agent="agent-a", **extra):
    resp = await app.post(
        f"{BASE}/jobs",
        json={
            "name": "Configurable",
            "agent": agent,
            "message": "work the queue",
            "cron": "*/5 * * * *",
            "enabled": True,
            "purpose": "keep going",
            "stop_when_queue_empties": True,
            **extra,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["id"], body["loop"]["id"]


async def _events(loop_id, event_type):
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(EventLog).where(
                        EventLog.event_type == event_type, EventLog.loop_id == loop_id
                    )
                )
            )
            .scalars()
            .all()
        )
    return rows


async def test_an_agent_alone_is_staged_on_a_loop(app, auth_headers):
    await _roster(app, auth_headers, "agent-a", "agent-b")
    job_id, loop_id = await _loop_job(app, auth_headers)

    resp = await app.patch(f"{BASE}/jobs/{job_id}", json={"agent": "agent-b"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent"] == "agent-a"
    assert body["loop"]["pending_edit"]["agent"] == "agent-b"

    async with async_session_factory() as db:
        assert (await db.get(Loop, loop_id)).pending_agent == "agent-b"
    staged = await _events(loop_id, "loop_edit_staged")
    assert len(staged) == 1
    assert "agent" in staged[0].data["changes"]


async def test_an_agent_and_a_purpose_make_one_staged_event(app, auth_headers):
    await _roster(app, auth_headers, "agent-a", "agent-b")
    job_id, loop_id = await _loop_job(app, auth_headers)

    resp = await app.patch(
        f"{BASE}/jobs/{job_id}", json={"agent": "agent-b", "purpose": "p2"}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    staged = await _events(loop_id, "loop_edit_staged")
    assert len(staged) == 1
    assert set(staged[0].data["changes"]) == {"agent", "purpose"}


async def test_a_plain_job_opted_in_by_the_same_patch_names_the_agent_at_once(app, auth_headers):
    await _roster(app, auth_headers, "agent-a", "agent-b")
    created = await app.post(
        f"{BASE}/jobs",
        json={"name": "plain", "agent": "agent-a", "message": "m", "cron": "*/5 * * * *"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    resp = await app.patch(
        f"{BASE}/jobs/{job_id}",
        json={"agent": "agent-b", "purpose": "now a loop"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["agent"] == "agent-b"
    assert resp.json()["loop"]["pending_edit"] is None
    assert await _events(resp.json()["loop"]["id"], "loop_edit_staged") == []


async def test_a_plain_job_takes_the_agent_at_once_and_drops_its_session(app, auth_headers):
    await _roster(app, auth_headers, "agent-a", "agent-b")
    created = await app.post(
        f"{BASE}/jobs",
        json={"name": "plain", "agent": "agent-a", "message": "m", "cron": "*/5 * * * *"},
        headers=auth_headers,
    )
    job_id = created.json()["id"]
    async with async_session_factory() as db:
        (await db.get(AIJob, job_id)).last_session_id = "sess-old"
        await db.commit()

    resp = await app.patch(f"{BASE}/jobs/{job_id}", json={"agent": "agent-b"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["agent"] == "agent-b"
    async with async_session_factory() as db:
        assert (await db.get(AIJob, job_id)).last_session_id is None

    # Naming the agent it already has keeps the session.
    async with async_session_factory() as db:
        (await db.get(AIJob, job_id)).last_session_id = "sess-new"
        await db.commit()
    resp = await app.patch(f"{BASE}/jobs/{job_id}", json={"agent": "agent-b"}, headers=auth_headers)
    assert resp.status_code == 200
    async with async_session_factory() as db:
        assert (await db.get(AIJob, job_id)).last_session_id == "sess-new"


async def test_an_unknown_or_archived_agent_is_refused_and_nothing_is_staged(app, auth_headers):
    await _roster(app, auth_headers, "agent-a", "agent-b")
    job_id, loop_id = await _loop_job(app, auth_headers)

    resp = await app.patch(
        f"{BASE}/jobs/{job_id}",
        json={"agent": "nobody", "name": "renamed"},
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
    async with async_session_factory() as db:
        assert (await db.get(AIJob, job_id)).name == "Configurable"
        assert (await db.get(Loop, loop_id)).pending_agent is None

    async with async_session_factory() as db:
        # Not in the synced session data: a session-known name whose row is archived is accepted
        # (design D2, Opus review 7), so the refusal is exercised on a roster-only agent.
        db.add(Agent(id=1000, project_id="proj-test", name="agent-c", lifecycle="archived"))
        await db.commit()
    resp = await app.patch(f"{BASE}/jobs/{job_id}", json={"agent": "agent-c"}, headers=auth_headers)
    assert resp.status_code == 400, resp.text
    assert await _events(loop_id, "loop_edit_staged") == []


async def test_the_agent_plane_may_not_change_the_agent(app, auth_headers):
    await _roster(app, auth_headers, "agent-a", "agent-b")
    job_id, loop_id = await _loop_job(app, auth_headers)
    token = "aw_run_run-agent-edit-secret"
    async with async_session_factory() as db:
        db.add(
            Run(
                id="run-agent-edit",
                project_id="proj-test",
                agent="agent-b",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await db.commit()
    settings = await app.put(
        f"{BASE}/settings",
        headers=auth_headers,
        json={
            "hop_budget": 8,
            "turn_delivery_cap": 10,
            "agent_budget": 8,
            "allow_agent_jobs": True,
        },
    )
    assert settings.status_code == 200, settings.text
    headers = {"Authorization": f"Bearer {token}"}

    refused = await app.patch(
        f"/api/v1/agent-actions/jobs/{job_id}", headers=headers, json={"agent": "agent-b"}
    )
    assert refused.status_code == 403, refused.text
    assert "only the operator" in refused.text
    async with async_session_factory() as db:
        assert (await db.get(AIJob, job_id)).agent == "agent-a"
        assert (await db.get(Loop, loop_id)).pending_agent is None

    control = await app.patch(
        f"/api/v1/agent-actions/jobs/{job_id}", headers=headers, json={"name": "x"}
    )
    assert control.status_code == 200, control.text


async def test_loops_carry_their_document(app, auth_headers):
    await _roster(app, auth_headers, "agent-a")
    _, plain_id = await _loop_job(app, auth_headers)
    listed = await app.get(f"{BASE}/loops", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    row = next(r for r in listed.json() if r["id"] == plain_id)
    assert row["spec_document_id"] is None

    async with async_session_factory() as db:
        (await db.get(Loop, plain_id)).spec_document_id = "doc-flow-1"
        await db.commit()
    listed = await app.get(f"{BASE}/loops", headers=auth_headers)
    assert next(r for r in listed.json() if r["id"] == plain_id)["spec_document_id"] == "doc-flow-1"
    detail = await app.get(f"{BASE}/loops/{plain_id}", headers=auth_headers)
    assert detail.json()["spec_document_id"] == "doc-flow-1"


# --- application (`_stage_pending_loop_edit`) --------------------------------------------------


async def _staged(app, auth_headers, control=None, session_id=None):
    await _roster(app, auth_headers, "agent-a", "agent-b")
    job_id, loop_id = await _loop_job(app, auth_headers)
    async with async_session_factory() as db:
        job = await db.get(AIJob, job_id)
        loop = await db.get(Loop, loop_id)
        loop.control = control
        job.last_session_id = session_id
        await db.commit()
    return job_id, loop_id


async def test_applying_a_staged_agent_names_it_and_clears_the_session(app, auth_headers):
    job_id, loop_id = await _staged(app, auth_headers, session_id="sess-old")
    await app.patch(f"{BASE}/jobs/{job_id}", json={"agent": "agent-b"}, headers=auth_headers)

    async with async_session_factory() as db:
        job = await db.get(AIJob, job_id)
        loop = await db.get(Loop, loop_id)
        payload = _stage_pending_loop_edit(loop, job, agent_archived=False)
        assert job.agent == "agent-b"
        assert job.last_session_id is None
        assert loop.pending_agent is None and loop.pending_edit_at is None
        assert payload["changes"]["agent"] == {"from": "agent-a", "to": "agent-b"}


async def test_applying_the_agent_already_in_force_keeps_the_session(app, auth_headers):
    job_id, loop_id = await _staged(app, auth_headers, session_id="sess-keep")
    await app.patch(f"{BASE}/jobs/{job_id}", json={"agent": "agent-a"}, headers=auth_headers)

    async with async_session_factory() as db:
        job = await db.get(AIJob, job_id)
        loop = await db.get(Loop, loop_id)
        payload = _stage_pending_loop_edit(loop, job, agent_archived=False)
        assert job.agent == "agent-a"
        assert job.last_session_id == "sess-keep"
        assert "agent" not in payload["changes"]


async def test_a_staged_agent_archived_before_the_firing_is_dropped(app, auth_headers):
    job_id, loop_id = await _staged(app, auth_headers)
    await app.patch(
        f"{BASE}/jobs/{job_id}", json={"agent": "agent-b", "purpose": "p2"}, headers=auth_headers
    )

    async with async_session_factory() as db:
        job = await db.get(AIJob, job_id)
        loop = await db.get(Loop, loop_id)
        payload = _stage_pending_loop_edit(loop, job, agent_archived=True)
        assert job.agent == "agent-a"
        assert loop.purpose == "p2"
        assert loop.pending_agent is None
        assert payload["changes"]["agent_dropped"] == {"name": "agent-b", "reason": "archived"}
        assert "agent" not in payload["changes"]


async def test_applying_a_changed_agent_returns_creator_control_to_the_operator(app, auth_headers):
    job_id, loop_id = await _staged(app, auth_headers, control="creator")
    await app.patch(f"{BASE}/jobs/{job_id}", json={"agent": "agent-b"}, headers=auth_headers)

    async with async_session_factory() as db:
        job = await db.get(AIJob, job_id)
        loop = await db.get(Loop, loop_id)
        payload = _stage_pending_loop_edit(loop, job, agent_archived=False)
        assert loop.control is None
        assert payload["changes"]["control"] == {"from": "creator", "to": "operator"}
        assert payload["actor"] == "operator"


async def test_a_revert_leaves_creator_control_alone(app, auth_headers):
    job_id, loop_id = await _staged(app, auth_headers, control="creator")
    await app.patch(f"{BASE}/jobs/{job_id}", json={"agent": "agent-a"}, headers=auth_headers)

    async with async_session_factory() as db:
        job = await db.get(AIJob, job_id)
        loop = await db.get(Loop, loop_id)
        payload = _stage_pending_loop_edit(loop, job, agent_archived=False)
        assert loop.control == "creator"
        assert "control" not in payload["changes"]


async def test_a_staged_agent_is_applied_by_the_next_firing_and_moves_no_task(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, "agent-a", "agent-b")
    await bind_runner("agent-a", cli="claude")
    await bind_runner("agent-b", cli="claude")
    job_id, loop_id = await _loop_job(app, auth_headers)
    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-held-by-a",
                project_id="proj-test",
                title="held",
                status="assigned",
                assignee="agent-a",
                loop_id=loop_id,
            )
        )
        await db.commit()
    await app.patch(f"{BASE}/jobs/{job_id}", json={"agent": "agent-b"}, headers=auth_headers)

    fake_session = MagicMock()
    fake_session.pid = 6161
    fake_session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-b-1"}\n',
        "",
    ]
    fake_session.wait.return_value = 0
    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            scheduler = JobScheduler()
            async with async_session_factory() as db:
                fresh = await db.get(AIJob, job_id)
                await scheduler._fire_job_internal(fresh, trigger="scheduled", session=db)
            for task in list(agent_trigger._background_runs):
                await task

    async with async_session_factory() as db:
        job = await db.get(AIJob, job_id)
        loop = await db.get(Loop, loop_id)
        task = await db.get(Task, "task-held-by-a")
        applied = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "loop_edit_applied")))
            .scalars()
            .all()
        )

    assert job.agent == "agent-b"
    assert loop.pending_agent is None
    assert task.assignee == "agent-a"
    assert len(applied) == 1
    assert applied[0].data["changes"]["agent"] == {"from": "agent-a", "to": "agent-b"}
