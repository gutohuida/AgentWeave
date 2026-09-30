"""Isolation does not change under held work (F242; `isolation-does-not-change-under-held-work`,
design D1).

Whether an agent works in its own checkout is `read_only` in the configuration its turns read. The
app offers no control for it, because flipping it under work strands that work: a task-bound turn
after the flip runs in the operator's checkout, and nothing commits it. The API kept no such
promise. Two doors change it: `PATCH /agents/{name}` (`Agent.config`) and `POST /session/sync` (the
synced session entry, which outranks `Agent.config`). Both now refuse a change to where the agent
works while it has a live turn or an unfinished task, and say what clears it.
"""

import pytest
from sqlalchemy import select

from hub import run_liveness
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EventLog, ProjectSession, Run, Task

AGENTS = "/api/v1/projects/proj-test/agents"
SYNC = "/api/v1/projects/proj-test/session/sync"
CODE = "isolation_change_under_held_work"


async def _task(agent, *, status="in_progress", task_id=None):
    task_id = task_id or f"task-{agent}-{status}"
    async with async_session_factory() as session:
        session.add(
            Task(id=task_id, project_id="proj-test", title="work", status=status, assignee=agent)
        )
        await session.commit()
    return task_id


async def _live_run(agent, monkeypatch, run_id=None):
    run_id = run_id or f"run-{agent}-live"
    async with async_session_factory() as session:
        session.add(
            Run(id=run_id, project_id="proj-test", agent=agent, status="running", turn_depth=0)
        )
        await session.commit()
    monkeypatch.setitem(run_liveness.active_ptys, run_id, object())
    return run_id


async def _row(name):
    async with async_session_factory() as session:
        return (
            await session.execute(
                select(Agent).where(Agent.project_id == "proj-test", Agent.name == name)
            )
        ).scalar_one()


def _refusal(response):
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == CODE, detail
    return detail


# --- PATCH /agents/{name} ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flipping_a_busy_agent_to_the_shared_checkout_is_refused(
    app, auth_headers, add_agent
):
    await add_agent("beta")
    task = await _task("beta")

    response = await app.patch(
        f"{AGENTS}/beta", json={"config": {"read_only": True}}, headers=auth_headers
    )

    detail = _refusal(response)
    assert detail["held"]["tasks"] == [task]
    assert task in detail["message"]
    assert (await _row("beta")).config == {}


@pytest.mark.asyncio
async def test_clearing_read_only_is_a_change(app, auth_headers, add_agent):
    await add_agent("beta", config={"read_only": True})
    await _task("beta")

    response = await app.patch(f"{AGENTS}/beta", json={"config": None}, headers=auth_headers)

    _refusal(response)
    assert (await _row("beta")).config == {"read_only": True}


@pytest.mark.asyncio
async def test_a_live_turn_is_held_work(app, auth_headers, add_agent, monkeypatch):
    await add_agent("beta")
    run = await _live_run("beta", monkeypatch)

    response = await app.patch(
        f"{AGENTS}/beta", json={"config": {"read_only": True}}, headers=auth_headers
    )

    detail = _refusal(response)
    assert detail["held"]["runs"] == [run]
    assert run in detail["message"]


@pytest.mark.asyncio
async def test_a_refused_body_changes_nothing(app, auth_headers, add_agent):
    await add_agent("beta")
    await _task("beta")

    response = await app.patch(
        f"{AGENTS}/beta",
        json={"description": "renamed", "config": {"read_only": True}},
        headers=auth_headers,
    )

    _refusal(response)
    row = await _row("beta")
    assert row.description is None and row.config == {}


@pytest.mark.asyncio
async def test_turning_isolation_on_under_a_task_is_refused_too(app, auth_headers, add_agent):
    """The direction with no task checkout on disk: the earlier turns' edits sit uncommitted in the
    operator's checkout, and the next turn would provision a fresh checkout that cannot see them."""
    await add_agent("beta", config={"read_only": True})
    await _task("beta", status="assigned")

    response = await app.patch(
        f"{AGENTS}/beta", json={"config": {"read_only": False}}, headers=auth_headers
    )

    _refusal(response)


@pytest.mark.asyncio
async def test_an_agent_with_only_finished_tasks_can_be_flipped(app, auth_headers, add_agent):
    await add_agent("beta")
    await _task("beta", status="approved")
    await _task("beta", status="rejected")

    response = await app.patch(
        f"{AGENTS}/beta", json={"config": {"read_only": True}}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    assert (await _row("beta")).config == {"read_only": True}


@pytest.mark.asyncio
async def test_a_busy_agent_keeps_every_other_setting(app, auth_headers, add_agent):
    await add_agent("beta", config={"read_only": True})
    await _task("beta")

    other = await app.patch(
        f"{AGENTS}/beta", json={"config": {"model": "claude-haiku"}}, headers=auth_headers
    )
    same = await app.patch(
        f"{AGENTS}/beta", json={"config": {"read_only": True}}, headers=auth_headers
    )

    assert other.status_code == 200, other.text
    assert same.status_code == 200, same.text


# --- POST /session/sync --------------------------------------------------------------------------


async def _sync(app, auth_headers, agents):
    return await app.post(SYNC, json={"data": {"agents": agents}}, headers=auth_headers)


async def _session_data():
    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(ProjectSession).where(ProjectSession.project_id == "proj-test")
            )
        ).scalar_one()
        return row.data


@pytest.mark.asyncio
async def test_a_sync_that_flips_a_busy_agent_is_refused_whole(app, auth_headers):
    first = await _sync(app, auth_headers, {"beta": {}, "gamma": {}})
    assert first.status_code == 200, first.text
    task = await _task("beta")

    response = await _sync(app, auth_headers, {"beta": {"read_only": True}})

    detail = _refusal(response)
    assert "beta" in detail["message"] and task in detail["message"]
    assert await _session_data() == {"agents": {"beta": {}, "gamma": {}}}
    await _row("gamma")  # not deleted
    async with async_session_factory() as session:
        released = (
            await session.execute(
                select(EventLog).where(EventLog.event_type == "worktree_released")
            )
        ).all()
    assert released == []


@pytest.mark.asyncio
async def test_a_sync_that_drops_read_only_under_a_turn_is_refused(app, auth_headers, monkeypatch):
    assert (await _sync(app, auth_headers, {"beta": {"read_only": True}})).status_code == 200
    task = await _task("beta")
    run = await _live_run("beta", monkeypatch)

    response = await _sync(app, auth_headers, {"beta": {}})

    detail = _refusal(response)
    assert detail["held"] == {"runs": [run], "tasks": [task]}


@pytest.mark.asyncio
async def test_the_sync_door_reads_the_effective_config(app, auth_headers, add_agent):
    """The session entry outranks `Agent.config`. Here it says isolated over a stored read-only, so
    dropping it moves the agent to the shared checkout -- a change a comparison of `Agent.config`
    alone would not see."""
    assert (await _sync(app, auth_headers, {"beta": {"read_only": False}})).status_code == 200
    await add_agent("beta", config={"read_only": True})
    await _task("beta")

    response = await _sync(app, auth_headers, {"beta": {}})

    _refusal(response)


@pytest.mark.asyncio
async def test_a_sync_that_moves_nothing_is_accepted(app, auth_headers, add_agent):
    assert (await _sync(app, auth_headers, {"beta": {"read_only": True}})).status_code == 200
    await _task("beta")

    same = await _sync(app, auth_headers, {"beta": {"read_only": True}})
    more = await _sync(app, auth_headers, {"beta": {"read_only": True, "model": "x"}})

    assert same.status_code == 200, same.text
    assert more.status_code == 200, more.text
