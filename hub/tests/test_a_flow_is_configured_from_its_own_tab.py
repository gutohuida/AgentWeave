"""A loop's default agent is configured from the loop's own tab, and staged like the rest of it.

Change `a-flow-is-configured-from-its-own-tab`, design D2, D3, D7. Before it `PATCH /jobs/{id}`
refused `agent` with a 422, and `LoopSummary` did not say which document a loop declares.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AIJob,
    Conversation,
    EventLog,
    JobRun,
    Loop,
    Run,
    Task,
    TurnUsage,
)
from hub.scheduler import JobScheduler, _stage_pending_loop_edit
from hub.utils import short_id

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
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
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


# --- D2a: the firing side (`_do_fire_job`) -----------------------------------------------------


async def _open_task(loop_id, task_id="task-open"):
    async with async_session_factory() as db:
        db.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title="open work",
                status="pending",
                loop_id=loop_id,
            )
        )
        await db.commit()


def _scheduling():
    """`schedule_agent` answers "started" without spawning anything."""
    return patch(
        "hub.turn_scheduler.schedule_agent",
        AsyncMock(return_value=MagicMock(waiting_reason=None, terminal_failure=False)),
    )


async def _tick(job_id):
    async with async_session_factory() as db:
        job = await db.get(AIJob, job_id)
        return await JobScheduler()._do_fire_job(job, "scheduled", db)


async def _flow(app, auth_headers, bind_runner, **extra):
    await _roster(app, auth_headers, "agent-a", "agent-b")
    await bind_runner("agent-a", cli="claude")
    await bind_runner("agent-b", cli="claude")
    return await _loop_job(app, auth_headers, **extra)


async def _stage(app, auth_headers, job_id, **body):
    resp = await app.patch(f"{BASE}/jobs/{job_id}", json=body, headers=auth_headers)
    assert resp.status_code == 200, resp.text


async def _hold(agent):
    now = datetime.now(timezone.utc)
    epoch = (now + timedelta(hours=1)).timestamp()
    async with async_session_factory() as db:
        run_id = f"run-{short_id()}"
        db.add(Run(id=run_id, project_id="proj-test", agent=agent, status="failed"))
        await db.flush()
        db.add(
            TurnUsage(
                id=f"usage-{short_id()}",
                run_id=run_id,
                project_id="proj-test",
                agent=agent,
                status="unavailable",
                allowance={
                    "status": "rejected",
                    "resetsAt": epoch,
                    "rateLimitType": "five_hour",
                    "overageStatus": "rejected",
                    "overageDisabledReason": "out_of_credits",
                    "isUsingOverage": False,
                    "unifiedWindows": {"five_hour": {"utilization": 1.02, "resetsAt": epoch}},
                },
                observed_at=now - timedelta(minutes=1),
            )
        )
        await db.commit()


async def _active_firing(job_id, agent):
    """A `JobRun` in progress whose conversation has `agent`'s `Run` running."""
    async with async_session_factory() as db:
        conv = Conversation(id=f"conv-{short_id()}", project_id="proj-test", agent=agent)
        db.add(conv)
        await db.flush()
        db.add(
            JobRun(
                id=f"run-{short_id()}",
                job_id=job_id,
                project_id="proj-test",
                fired_at=datetime.now(timezone.utc),
                status="in_progress",
                trigger="scheduled",
                conversation_id=conv.id,
            )
        )
        db.add(
            Run(
                id=f"run-{short_id()}",
                project_id="proj-test",
                agent=agent,
                status="running",
                conversation_id=conv.id,
            )
        )
        await db.commit()


async def _applied(loop_id):
    return await _events(loop_id, "loop_edit_applied")


async def test_a_staged_agent_archived_before_the_firing_is_dropped_by_the_tick(
    app, auth_headers, bind_runner
):
    job_id, loop_id = await _flow(app, auth_headers, bind_runner)
    await _open_task(loop_id)
    await _stage(app, auth_headers, job_id, agent="agent-b", purpose="p2")
    async with async_session_factory() as db:
        row = (await db.execute(select(Agent).where(Agent.name == "agent-b"))).scalar_one()
        row.lifecycle = "archived"
        await db.commit()

    with _scheduling():
        await _tick(job_id)

    async with async_session_factory() as db:
        assert (await db.get(AIJob, job_id)).agent == "agent-a"
        loop = await db.get(Loop, loop_id)
        assert loop.purpose == "p2" and loop.pending_agent is None
    (event,) = await _applied(loop_id)
    assert event.data["changes"]["agent_dropped"] == {"name": "agent-b", "reason": "archived"}
    assert "agent" not in event.data["changes"]


async def test_the_tick_returns_creator_control_and_b_needs_the_operator(
    app, auth_headers, bind_runner
):
    job_id, loop_id = await _flow(app, auth_headers, bind_runner)
    await _open_task(loop_id)
    async with async_session_factory() as db:
        (await db.get(Loop, loop_id)).control = "creator"
        (await db.get(AIJob, job_id)).run_count = 1
        await db.commit()
    await _stage(app, auth_headers, job_id, agent="agent-b")

    with _scheduling():
        await _tick(job_id)

    async with async_session_factory() as db:
        assert (await db.get(Loop, loop_id)).control is None
    (event,) = await _applied(loop_id)
    assert event.data["changes"]["control"] == {"from": "creator", "to": "operator"}
    assert event.data["actor"] == "operator"

    results = {}
    for agent in ("agent-b", "agent-a"):
        token = f"aw_run_run-{agent}-creates"
        async with async_session_factory() as db:
            db.add(
                Run(
                    id=f"run-{agent}-creates",
                    project_id="proj-test",
                    agent=agent,
                    status="running",
                    turn_depth=0,
                    capability_token_hash=hash_run_token(token),
                )
            )
            await db.commit()
        results[agent] = await app.post(
            "/api/v1/agent-actions/tasks",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": f"from {agent}", "loop_id": loop_id},
        )
    # The job now names B, which has fired before and is no longer delegated to.
    assert results["agent-b"].status_code == 403, results["agent-b"].text
    assert "operator" in results["agent-b"].text
    # The old agent is not the loop's creator any more either.
    assert results["agent-a"].status_code == 403, results["agent-a"].text
    assert "creator" in results["agent-a"].text


async def test_a_revert_at_the_tick_keeps_creator_control(app, auth_headers, bind_runner):
    job_id, loop_id = await _flow(app, auth_headers, bind_runner)
    await _open_task(loop_id)
    async with async_session_factory() as db:
        (await db.get(Loop, loop_id)).control = "creator"
        await db.commit()
    await _stage(app, auth_headers, job_id, agent="agent-a")

    with _scheduling():
        await _tick(job_id)

    async with async_session_factory() as db:
        assert (await db.get(Loop, loop_id)).control == "creator"
    (event,) = await _applied(loop_id)
    assert "control" not in event.data["changes"]


async def test_a_staged_agent_waits_while_a_firing_of_the_loop_is_active(
    app, auth_headers, bind_runner
):
    """No document, A's firing running: the guard still asks about A, and the edit stays staged."""
    job_id, loop_id = await _flow(app, auth_headers, bind_runner)
    await _open_task(loop_id)
    await _active_firing(job_id, "agent-a")
    await _stage(app, auth_headers, job_id, agent="agent-b")

    with _scheduling():
        assert await _tick(job_id) is False  # refused busy: the guard asks about A
    async with async_session_factory() as db:
        loop = await db.get(Loop, loop_id)
        assert loop.pending_agent == "agent-b"
        assert (await db.get(AIJob, job_id)).agent == "agent-a"
    assert await _applied(loop_id) == []


async def test_switching_away_from_a_held_agent_takes_effect_at_the_next_tick(
    app, auth_headers, bind_runner
):
    """R1's version refused every tick on A's hold, so the switch made *because* of it never
    applied."""
    stop = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    job_id, loop_id = await _flow(app, auth_headers, bind_runner, stop_at=stop)
    await _open_task(loop_id)
    await _hold("agent-a")
    await _stage(app, auth_headers, job_id, agent="agent-b")

    with _scheduling():
        fired = await _tick(job_id)

    assert fired is True
    async with async_session_factory() as db:
        assert (await db.get(AIJob, job_id)).agent == "agent-b"
        assert (await db.get(Loop, loop_id)).pending_agent is None
    assert len(await _applied(loop_id)) == 1


async def test_a_refused_busy_tick_still_applies_and_announces_the_edit_once(
    app, auth_headers, bind_runner
):
    job_id, loop_id = await _flow(app, auth_headers, bind_runner)
    await _open_task(loop_id)
    await _stage(app, auth_headers, job_id, agent="agent-b")
    # B is held, so the guard refuses the tick for B.
    await _hold("agent-b")

    with _scheduling():
        fired = await _tick(job_id)

    assert fired is False
    async with async_session_factory() as db:
        assert (await db.get(AIJob, job_id)).agent == "agent-b"
    assert len(await _applied(loop_id)) == 1


async def test_a_raise_after_the_edit_applied_announces_it_once_and_fails_the_run(
    app, auth_headers, bind_runner, monkeypatch
):
    import hub.scheduler as scheduler

    job_id, loop_id = await _flow(app, auth_headers, bind_runner)
    await _open_task(loop_id)
    await _stage(app, auth_headers, job_id, agent="agent-b")

    async def _boom(*args, **kwargs):
        raise RuntimeError("stop check exploded")

    monkeypatch.setattr(scheduler, "_loop_stop_reason", _boom)
    with _scheduling():
        fired = await _tick(job_id)  # no UnboundLocalError escapes

    assert fired is False
    async with async_session_factory() as db:
        runs = (await db.execute(select(JobRun).where(JobRun.job_id == job_id))).scalars().all()
        assert [r.status for r in runs] == ["failed"]
        assert (await db.get(AIJob, job_id)).agent == "agent-b"
    # No F349 (`persist_accepted_event`) in this tree: the handler's commit carries the edit.
    assert len(await _applied(loop_id)) == 1


async def test_the_summary_asks_about_the_agent_the_next_tick_will_run(
    app, auth_headers, bind_runner
):
    from hub.api.v1.jobs import _batch_loop_summaries

    job_id, loop_id = await _flow(app, auth_headers, bind_runner)
    await _open_task(loop_id)
    await _hold("agent-a")
    await _stage(app, auth_headers, job_id, agent="agent-b")

    async with async_session_factory() as db:
        summary = (await _batch_loop_summaries(db, [job_id]))[job_id]
    assert "agent-a" not in (summary.stall_reason or "")
    assert summary.agent == "agent-a"
    assert [t.get("agent") for t in summary.current_tasks] == ["agent-b"]

    await _active_firing(job_id, "agent-a")
    async with async_session_factory() as db:
        active = (await _batch_loop_summaries(db, [job_id]))[job_id]
    assert active.firing_active is True
    assert [t.get("agent") for t in active.current_tasks] != ["agent-b"]


async def test_one_emit_per_applied_edit_when_a_later_step_raises(app, auth_headers, bind_runner):
    job_id, loop_id = await _flow(app, auth_headers, bind_runner)
    await _open_task(loop_id)
    await _stage(app, auth_headers, job_id, agent="agent-b")

    with patch("hub.turn_scheduler.schedule_agent", AsyncMock(side_effect=RuntimeError("nope"))):
        await _tick(job_id)

    assert len(await _applied(loop_id)) == 1


async def test_tasks_stay_with_their_agent_across_an_agent_change(app, auth_headers, bind_runner):
    job_id, loop_id = await _flow(app, auth_headers, bind_runner)
    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-kept",
                project_id="proj-test",
                title="kept",
                status="assigned",
                assignee="agent-a",
                loop_id=loop_id,
            )
        )
        await db.commit()
    await _stage(app, auth_headers, job_id, agent="agent-b")

    with _scheduling():
        await _tick(job_id)

    async with async_session_factory() as db:
        kept = await db.get(Task, "task-kept")
        assert (kept.assignee, kept.status, kept.loop_id) == ("agent-a", "assigned", loop_id)
        assert (await db.get(AIJob, job_id)).agent == "agent-b"


async def test_an_archived_flow_leaves_the_document_to_its_successor(app, auth_headers):
    await _roster(app, auth_headers, "agent-a")
    _, first = await _loop_job(app, auth_headers)
    async with async_session_factory() as db:
        old = await db.get(Loop, first)
        old.spec_document_id = "doc-again"
        old.archived_at = datetime.now(timezone.utc)
        await db.commit()
    resp = await app.post(
        f"{BASE}/jobs",
        json={
            "name": "Second",
            "agent": "agent-a",
            "message": "m",
            "cron": "*/5 * * * *",
            "purpose": "again",
            "stop_when_queue_empties": True,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    second = resp.json()["loop"]["id"]
    async with async_session_factory() as db:
        (await db.get(Loop, second)).spec_document_id = "doc-again"
        await db.commit()

    default = await app.get(f"{BASE}/loops", headers=auth_headers)
    assert [r["id"] for r in default.json() if r["spec_document_id"] == "doc-again"] == [second]
    everything = await app.get(f"{BASE}/loops?include_archived=true", headers=auth_headers)
    ids = [r["id"] for r in everything.json() if r["spec_document_id"] == "doc-again"]
    assert ids == [first, second]
