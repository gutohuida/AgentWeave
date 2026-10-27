"""The lead driver, the budget cap and the window (`a-build-has-a-driver-a-level-and-its-people`,
task `lead-budget-window`).

Red first, on the levels (task `levels`): there a lead-driven build's loop fires like any flow --
it selects work itself and briefs nobody -- no tool hands a task out, and a build's cap and window
are recorded and read by nothing, so a flow over its cap goes on staffing turns (the night of
2026-10-26/27 cost ~$44 with nothing to stop it).

Named by acceptance criterion: `-k briefed`, `-k budget`, `-k window`.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from hub import builds
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    Build,
    EventLog,
    InboundQueueEntry,
    Loop,
    Run,
    SpecDocument,
    Task,
    TurnUsage,
)
from hub.scheduler import JobScheduler
from hub.spec_payload import SCHEMA_VERSION
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

from .test_review_turn import _roster

P = "proj-test"
BASE = f"/api/v1/projects/{P}/project"
AGENT_DOCS = "/api/v1/agent-actions/spec/documents"
HAND_OUT = "/api/v1/agent-actions/tasks/{}/hand-out"
PATH = "spec/changes/a-led-build/spec.json"


def _scheduling():
    """`schedule_agent` answers "started" without spawning anything; queued input stays queued."""
    return patch(
        "hub.turn_scheduler.schedule_agent",
        AsyncMock(return_value=MagicMock(waiting_reason=None, terminal_failure=False)),
    )


async def _run_headers(run_id, agent):
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as db:
        db.add(
            Run(
                id=run_id,
                project_id=P,
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await db.commit()
    return {"Authorization": f"Bearer {token}"}


def _document():
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "A led build",
        "problem": "Nobody hands the work out.",
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "requirements": [
            {"key": "alpha", "statement": "It does alpha", "modal": "MUST"},
            {"key": "beta", "statement": "It does beta", "modal": "MUST"},
        ],
        "acceptance_criteria": [
            {
                "key": f"c-{key}",
                "requirement": key,
                "given": "g",
                "when": "w",
                "then": "t",
                "how_to_check": "pytest",
                "checked_by": "agent",
            }
            for key in ("alpha", "beta")
        ],
        "tasks": [
            {"key": "t1", "description": "Build alpha", "requirements": ["alpha"]},
            {"key": "t2", "description": "Build beta", "requirements": ["beta"]},
        ],
        "delivery": {"mode": "flow", "agent": "dev", "stop_when_queue_empties": True},
    }


async def _approved(app, auth_headers):
    author = await _run_headers("run-led-author", "author")
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "A led build"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(AGENT_DOCS, json={"path": PATH, "document": _document()}, headers=author)
    assert saved.status_code == 200, saved.text
    async with async_session_factory() as db:  # the author's turn is over
        (await db.get(Run, "run-led-author")).status = "completed"
        await db.commit()
    version = (await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)).json()[
        "content_version"
    ]
    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={"reason": "", "approve_anyway": True, "content_version": version},
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text


async def _build(app, auth_headers, **settings):
    with _scheduling():
        built = await app.post(
            f"{BASE}/documents/build", params={"path": PATH}, json=settings, headers=auth_headers
        )
    assert built.status_code == 200, built.text
    return built.json()["build_outcome"]


async def _rows(model, *where):
    async with async_session_factory() as db:
        return list((await db.execute(select(model).where(*where))).scalars())


async def _tick():
    (loop,) = await _rows(Loop)
    with _scheduling():
        async with async_session_factory() as db:
            job = await db.get(AIJob, loop.job_id)
            return await JobScheduler()._do_fire_job(job, "scheduled", db)


async def _briefs(lead="lead"):
    return await _rows(
        InboundQueueEntry,
        InboundQueueEntry.agent == lead,
        InboundQueueEntry.task_id.is_(None),
        InboundQueueEntry.review_task_id.is_(None),
    )


async def _read_all(lead="lead"):
    async with async_session_factory() as db:
        for entry in (
            await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == lead))
        ).scalars():
            entry.state = "delivered"
        await db.commit()


async def _tasks():
    (document,) = await _rows(SpecDocument, SpecDocument.path == PATH)
    return {t.spec_task_key: t for t in await _rows(Task, Task.spec_document_id == document.id)}


# ---------------------------------------------------------------------------------------------
# lead-briefed-and-hands-out (a-lead-hands-out-the-work)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_lead_is_briefed_and_hands_out_the_work(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "lead", "dev", "qa")
    await _approved(app, auth_headers)
    await _build(app, auth_headers, driver="lead", lead="lead", builders=["dev"], level="reviewed")

    briefs = await _briefs()
    assert len(briefs) == 1, "one brief when the build starts"
    assert all(task.id in briefs[0].content for task in (await _tasks()).values())
    assert "reviewed" in briefs[0].content and "dev" in briefs[0].content
    await _tick()
    assert len(await _briefs()) == 1, "no second brief over an unread one"
    await _read_all()

    t1 = (await _tasks())["t1"]
    lead = await _run_headers("run-lead-1", "lead")
    with _scheduling():
        handed = await app.post(
            HAND_OUT.format(t1.id), json={"agent": "dev", "review": False}, headers=lead
        )
    assert handed.status_code == 200, handed.text
    (turn,) = await _rows(InboundQueueEntry, InboundQueueEntry.agent == "dev")
    assert turn.task_id == t1.id
    assert (await _tasks())["t1"].assignee == "dev"

    async with async_session_factory() as db:
        task = await db.get(Task, t1.id)
        await apply_transition(db, task, "in_progress", run_actor("run-dev-t1", "dev"))
        await apply_transition(db, task, "completed", run_actor("run-dev-t1", "dev"))
        await db.commit()
    await _tick()  # the hand-off asks for the build's firing (`flow_advance`)

    assert len(await _briefs()) == 2, "one brief after the completion"
    await _tick()
    assert len(await _briefs()) == 2, "none stacked while unread"
    assert await _rows(InboundQueueEntry, InboundQueueEntry.agent == "qa") == []

    qa = await _run_headers("run-qa-1", "qa")
    refused = await app.post(
        HAND_OUT.format((await _tasks())["t2"].id), json={"agent": "dev"}, headers=qa
    )
    assert refused.status_code == 403, refused.text


@pytest.mark.asyncio
async def test_a_lead_hands_only_to_the_builds_people(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "lead", "dev", "qa", "architect")
    await _approved(app, auth_headers)
    await _build(app, auth_headers, driver="lead", lead="lead", builders=["dev"])
    lead = await _run_headers("run-lead-2", "lead")

    outside = await app.post(
        HAND_OUT.format((await _tasks())["t1"].id), json={"agent": "architect"}, headers=lead
    )

    assert outside.status_code == 409, outside.text
    assert "builders" in outside.text
    assert await _rows(InboundQueueEntry, InboundQueueEntry.agent == "architect") == []


# ---------------------------------------------------------------------------------------------
# cap-stops-new-turns (budget-and-window)
# ---------------------------------------------------------------------------------------------


async def _usage(run_id, agent, task_id, micros, status="completed"):
    async with async_session_factory() as db:
        db.add(Run(id=run_id, project_id=P, agent=agent, status=status, task_id=task_id))
        await db.flush()
        db.add(
            TurnUsage(
                id=f"tu-{run_id}",
                run_id=run_id,
                project_id=P,
                agent=agent,
                status="measured",
                total_tokens=1000,
                api_equivalent_usd_micros=micros,
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_the_budget_cap_stops_new_turns_and_raising_it_resumes(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _approved(app, auth_headers)
    outcome = await _build(app, auth_headers, driver="flow", builders=["dev"], budget_cap_usd=1)
    build_id = outcome["build"]["id"]
    tasks = await _tasks()
    await _usage("run-spent-1", "qa", tasks["t1"].id, 700_000)
    await _usage("run-spent-2", "qa", tasks["t2"].id, 500_000, status="running")

    await _tick()

    assert await _rows(InboundQueueEntry, InboundQueueEntry.agent == "dev") == []
    (running,) = await _rows(Run, Run.id == "run-spent-2")
    assert running.status == "running", "a running turn is never stopped"
    (build,) = await _rows(Build, Build.id == build_id)
    assert build.state == "stopped"
    assert "$1.20" in (build.stop_reason or "") and "$1.00" in (build.stop_reason or "")
    events = await _rows(EventLog, EventLog.event_type == "build_stopped")
    assert len(events) == 1 and "$1.20" in events[0].data["reason"]

    raised = await app.patch(
        f"{BASE}/builds/{build_id}", json={"budget_cap_usd": 5}, headers=auth_headers
    )
    assert raised.status_code == 200, raised.text
    assert raised.json()["state"] == "running"
    await _tick()

    staged = await _rows(InboundQueueEntry, InboundQueueEntry.agent == "dev")
    assert len(staged) == 1 and staged[0].task_id in {t.id for t in tasks.values()}


# ---------------------------------------------------------------------------------------------
# window-closed (budget-and-window)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_window_not_yet_open_briefs_nobody_until_it_opens(
    app, auth_headers, bind_runner, monkeypatch
):
    await _roster(app, auth_headers, bind_runner, "lead", "dev")
    await _approved(app, auth_headers)
    opens = datetime.now(timezone.utc) + timedelta(hours=1)
    await _build(
        app,
        auth_headers,
        driver="lead",
        lead="lead",
        builders=["dev"],
        window_start=opens.isoformat(),
    )

    await _tick()
    assert await _briefs() == [], "nobody is briefed before the window opens"
    # Waiting for its window is attended, not a stall: the sweep wakes no mender for it, though
    # nothing has moved for longer than its no-progress window.
    from hub import stalls

    async with async_session_factory() as db:
        assert await stalls._sweep(db, opens - timedelta(minutes=1)) == 0

    monkeypatch.setattr(builds, "now", lambda: opens + timedelta(minutes=1))
    await _tick()

    assert len(await _briefs()) == 1
    # And a brief queued for the lead and not yet read is work in hand, not a stall either.
    async with async_session_factory() as db:
        assert await stalls._sweep(db, opens + timedelta(minutes=40)) == 0
