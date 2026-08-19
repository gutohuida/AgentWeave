"""A conversation created by a loop firing says which loop, in the list that draws the rail.

A loop firing starts a *new* conversation every time (task 8.1 refuses `session_mode="resume"` for
a loop), so an agent's conversation list silently fills with threads nobody typed. Measured on the
trial Hub 2026-08-19: one agent had 20 conversations, 11 of them firings across 5 loops,
interleaved by recency with the 9 the operator started, and nothing on the row told them apart.

The distinction this file exists to pin down: `origin == "job"` is *not* the answer. A plain
scheduled job produces exactly that origin and has no loop, so it must come back with `loop: null`
and draw no marker.
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import JobRun


async def _sync_agents(app, auth_headers, *names):
    response = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "manual"} for name in names}}},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _create_job(app, auth_headers, name: str, *, loop: bool) -> str:
    body = {
        "name": name,
        "agent": "looper",
        "message": "work the queue",
        "cron": "0 9 * * *",
    }
    if loop:
        body["purpose"] = "loop marker coverage"
    created = await app.post("/api/v1/projects/proj-test/jobs", json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    payload = created.json()
    assert (payload["loop"] is not None) is loop
    return payload["id"]


async def _fired_conversation(job_id: str, *, agent: str = "looper", fired_at=None) -> str:
    """A conversation as a firing leaves it: origin "job", with a `JobRun` pointing at it."""
    async with async_session_factory() as db:
        conversation = new_conversation(project_id="proj-test", agent=agent, origin="job")
        conversation.title = "Firing"
        db.add(conversation)
        db.add(
            JobRun(
                id=f"run-{job_id}-{conversation.id}",
                job_id=job_id,
                project_id="proj-test",
                fired_at=fired_at or datetime.now(timezone.utc),
                status="completed",
                trigger="scheduled",
                conversation_id=conversation.id,
            )
        )
        await db.commit()
        return conversation.id


async def _conversations(app, auth_headers, agent="looper"):
    response = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/conversations", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return {row["id"]: row for row in response.json()}


@pytest.mark.asyncio
async def test_a_loop_firing_names_its_loop(app, auth_headers):
    await _sync_agents(app, auth_headers, "looper")
    job_id = await _create_job(app, auth_headers, "nightly sweep", loop=True)
    conversation_id = await _fired_conversation(job_id)

    row = (await _conversations(app, auth_headers))[conversation_id]

    assert row["origin"] == "job"
    assert row["loop"] is not None
    # The label is the job's name — the same pairing `LoopSummary.label` uses, so the marker and
    # the loops index name one loop one way.
    assert row["loop"]["label"] == "nightly sweep"
    assert row["loop"]["id"].startswith("loop-")


@pytest.mark.asyncio
async def test_a_plain_scheduled_job_gets_no_loop_despite_the_same_origin(app, auth_headers):
    """The distinction `origin` cannot make. Both conversations are `origin == "job"`; only one
    came from a loop, and only that one may draw a marker."""
    await _sync_agents(app, auth_headers, "looper")
    loop_job = await _create_job(app, auth_headers, "nightly sweep", loop=True)
    plain_job = await _create_job(app, auth_headers, "hourly ping", loop=False)
    from_loop = await _fired_conversation(loop_job)
    from_plain = await _fired_conversation(plain_job)

    rows = await _conversations(app, auth_headers)

    assert rows[from_plain]["origin"] == rows[from_loop]["origin"] == "job"
    assert rows[from_plain]["loop"] is None
    assert rows[from_loop]["loop"]["label"] == "nightly sweep"


@pytest.mark.asyncio
async def test_an_operator_conversation_has_no_loop(app, auth_headers):
    await _sync_agents(app, auth_headers, "looper")
    await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "looper", "message": "Look at the build"},
        headers=auth_headers,
    )

    rows = list((await _conversations(app, auth_headers)).values())

    assert len(rows) == 1
    assert rows[0]["origin"] == "operator"
    assert rows[0]["loop"] is None


@pytest.mark.asyncio
async def test_repeated_firings_onto_one_conversation_report_the_newest(app, auth_headers):
    """A conversation reachable from more than one firing gets a deterministic answer, not
    whichever row the database returned first."""
    await _sync_agents(app, auth_headers, "looper")
    old_job = await _create_job(app, auth_headers, "retired sweep", loop=True)
    new_job = await _create_job(app, auth_headers, "current sweep", loop=True)

    now = datetime.now(timezone.utc)
    conversation_id = await _fired_conversation(old_job, fired_at=now - timedelta(hours=2))
    async with async_session_factory() as db:
        db.add(
            JobRun(
                id=f"run-{new_job}-later",
                job_id=new_job,
                project_id="proj-test",
                fired_at=now,
                status="completed",
                trigger="scheduled",
                conversation_id=conversation_id,
            )
        )
        await db.commit()

    row = (await _conversations(app, auth_headers))[conversation_id]

    assert row["loop"]["label"] == "current sweep"


@pytest.mark.asyncio
async def test_the_project_wide_list_carries_the_loop_too(app, auth_headers):
    """The rail reads the project-scoped list, not the per-agent one — both must answer."""
    await _sync_agents(app, auth_headers, "looper")
    job_id = await _create_job(app, auth_headers, "nightly sweep", loop=True)
    conversation_id = await _fired_conversation(job_id)

    response = await app.get("/api/v1/projects/proj-test/conversations", headers=auth_headers)
    assert response.status_code == 200, response.text
    rows = {row["id"]: row for row in response.json()["conversations"]}

    assert rows[conversation_id]["loop"]["label"] == "nightly sweep"
