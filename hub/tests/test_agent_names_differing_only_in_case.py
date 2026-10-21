"""F811: two agents whose names differ only in case are one agent to the filesystem.

Worktrees live at `.agentweave/worktrees/<name>`, on a filesystem that is case-insensitive by
default on Windows and macOS, so `EPS` shares `eps`'s checkout and the Hub's remedy ("delete that
directory") would delete another agent's work. Uniqueness is refused case-insensitively, archived
rows included, at the three doors that add an agent row. Not a reserved name: those are checked at
every use site, and an existing pair must keep running.
"""

import pytest
from sqlalchemy import select

from hub import route_words
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.model_catalog import get_provider
from hub.utils import short_id

BASE = "/api/v1/projects/proj-test"
CLAUDE_MODEL = get_provider("claude").models[0].id


async def _seed(name, lifecycle="open"):
    async with async_session_factory() as session:
        session.add(
            Agent(
                id=f"agent-{short_id()}",
                project_id="proj-test",
                name=name,
                color_index=0,
                lifecycle=lifecycle,
            )
        )
        await session.commit()


async def _roster(app, auth_headers):
    resp = await app.get(f"{BASE}/agents", headers=auth_headers)
    return {row["name"] for row in resp.json()}


def test_the_twin_check_is_case_insensitive_and_names_the_existing_agent():
    refusal = route_words.agent_case_twin("EPS", ["eps", "other"])
    assert refusal is not None
    assert "'eps'" in refusal and "case" in refusal
    assert route_words.agent_case_twin("eps", ["eps"]) is None  # the same name is not a twin
    assert route_words.agent_case_twin("epsilon", ["eps"]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["open", "archived"])
async def test_the_create_dialog_route_refuses_a_case_twin(app, auth_headers, lifecycle):
    await _seed("eps", lifecycle)

    resp = await app.post(
        f"{BASE}/agents",
        json={"name": "EPS", "provider": "claude", "model": CLAUDE_MODEL},
        headers=auth_headers,
    )

    assert resp.status_code == 409, resp.text
    assert isinstance(resp.json()["detail"], str)
    assert "'eps'" in resp.json()["detail"] and "case" in resp.json()["detail"]
    # The roster lists open agents only; neither the archived nor the refused one is added.
    assert await _roster(app, auth_headers) == ({"eps"} if lifecycle == "open" else set())
    async with async_session_factory() as session:
        names = (await session.execute(select(Agent.name))).scalars().all()
    assert names == ["eps"]


@pytest.mark.asyncio
async def test_an_agent_request_refuses_a_case_twin(app, auth_headers, add_agent, bind_runner):
    token = "aw_run_run-case-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-case",
                project_id="proj-test",
                agent="lead",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    await add_agent("template")
    await bind_runner("template", cli="claude")
    await _seed("eps", "archived")

    resp = await app.post(
        "/api/v1/agent-actions/agents/request",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "EPS", "template": "template", "task": "work"},
    )

    assert resp.status_code == 409, resp.text
    assert "'eps'" in resp.json()["detail"] and "case" in resp.json()["detail"]
    assert "EPS" not in await _roster(app, auth_headers)


@pytest.mark.asyncio
async def test_a_session_sync_refuses_a_case_twin_of_a_stored_agent(app, auth_headers):
    await _seed("eps")

    resp = await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {"eps": {}, "EPS": {}}}},
        headers=auth_headers,
    )

    assert resp.status_code == 409, resp.text
    assert "case" in resp.json()["detail"]
    assert await _roster(app, auth_headers) == {"eps"}


@pytest.mark.asyncio
async def test_a_session_sync_refuses_two_new_names_that_differ_only_in_case(app, auth_headers):
    resp = await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {"beta": {}, "Beta": {}}}},
        headers=auth_headers,
    )

    assert resp.status_code == 409, resp.text
    assert await _roster(app, auth_headers) == set()


@pytest.mark.asyncio
async def test_an_existing_twin_pair_still_syncs(app, auth_headers):
    """The check is at creation: a pair that already exists is not stopped from syncing."""
    await _seed("eps")
    await _seed("EPS")

    resp = await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {"eps": {}, "EPS": {}}}},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    assert await _roster(app, auth_headers) == {"eps", "EPS"}
