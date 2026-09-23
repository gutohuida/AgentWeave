"""Round 4a: a route given a name that belongs to nothing refuses it, not an empty answer.

F192 (stop), F194 (conversations, chat), F199 (queue, queue status), F247 (an agent's workspace):
each answered a typo'd agent name as if it were an idle agent with nothing to show. F239 answered
"0 tokens" for a conversation that does not exist or is another project's. F254 opened an SSE
stream for a project deleted after its ticket was minted. The trigger route has always refused the
identical mistake by name, so every leg here asserts the refusal *and* that the real thing still
answers — a fix that 404s everything would pass the first half alone.
"""

import asyncio

import pytest

from hub.auth import _make_ticket
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Project
from hub.inbound_queue import new_entry

P = "/api/v1/projects/proj-test"
GHOST = "ghost-agent-4a"
NOT_AN_AGENT = "is not an agent in this project"

pytestmark = pytest.mark.asyncio


async def _rostered(name: str) -> None:
    async with async_session_factory() as session:
        session.add(Agent(id=f"agt-{name}", project_id="proj-test", name=name))
        await session.commit()


async def _conversation(agent: str, project_id: str = "proj-test") -> str:
    async with async_session_factory() as session:
        conversation = new_conversation(project_id=project_id, agent=agent, origin="operator")
        session.add(conversation)
        await session.commit()
        return conversation.id


@pytest.mark.parametrize(
    "route",
    [
        "/agent/{agent}/conversations",
        "/agent/{agent}/chat",
        "/queue/{agent}",
        "/queue/{agent}/status",
        "/worktrees/{agent}",
    ],
)
async def test_a_name_nothing_is_recorded_under_is_refused_by_name(app, auth_headers, route):
    await _rostered("real-agent")

    ghost = await app.get(P + route.format(agent=GHOST), headers=auth_headers)
    assert ghost.status_code == 404, ghost.text
    assert f"{GHOST} {NOT_AN_AGENT}" in ghost.json()["detail"]

    if route != "/worktrees/{agent}":  # needs a bound workspace; covered by test_worktrees.py
        real = await app.get(P + route.format(agent="real-agent"), headers=auth_headers)
        assert real.status_code == 200, real.text


@pytest.mark.parametrize("route", ["/agent/{agent}/conversations", "/queue/{agent}"])
async def test_a_removed_agent_s_history_stays_readable(app, auth_headers, route):
    """Session sync deletes the roster row of an agent it no longer declares and keeps its
    conversations and queue. A roster-only check would 404 them; known means either."""
    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent="removed", origin="operator")
        session.add(conversation)
        await session.flush()
        session.add(
            new_entry(
                project_id="proj-test",
                agent="removed",
                origin_type="operator",
                origin_agent=None,
                conversation_id=conversation.id,
                content="left behind",
                hop_depth=0,
            )
        )
        await session.commit()

    resp = await app.get(P + route.format(agent="removed"), headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1


@pytest.mark.parametrize(
    "route",
    [
        "/agent/{agent}/conversations",
        "/agent/{agent}/chat",
        "/queue/{agent}",
        "/queue/{agent}/status",
    ],
)
async def test_every_name_the_roster_lists_is_known(app, auth_headers, route):
    """Round 4 review: `GET /agents` lists a task's assignee before the agent has any row, and
    these routes 404'd that name while the rail showed it. Every name the roster lists answers."""
    created = await app.post(
        f"{P}/tasks", json={"title": "for later", "assignee": "planned"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    roster = await app.get(f"{P}/agents", headers=auth_headers)
    names = {row["name"] for row in roster.json()}
    assert "planned" in names

    for name in names:
        resp = await app.get(P + route.format(agent=name), headers=auth_headers)
        assert resp.status_code == 200, (name, resp.text)


async def test_the_operator_s_own_sender_name_is_not_an_agent(app, auth_headers):
    """`operator` is recorded as a message sender (F261) and is reserved (F415): not an agent."""
    await _rostered("someone")
    sent = await app.post(
        f"{P}/messages", json={"to": "someone", "content": "hi"}, headers=auth_headers
    )
    assert sent.status_code in (200, 201), sent.text

    resp = await app.get(f"{P}/queue/operator/status", headers=auth_headers)

    assert resp.status_code == 404, resp.text


async def test_stop_tells_a_typo_from_an_idle_agent(app, auth_headers):
    await _rostered("idle-agent")

    ghost = await app.post(f"{P}/agent/{GHOST}/stop", headers=auth_headers)
    idle = await app.post(f"{P}/agent/idle-agent/stop", headers=auth_headers)

    assert ghost.status_code == 404, ghost.text
    assert NOT_AN_AGENT in ghost.json()["detail"]
    assert idle.status_code == 404, idle.text
    assert idle.json()["detail"] == "idle-agent has no run in progress."


async def test_an_invalid_queue_state_names_the_valid_ones(app, auth_headers):
    await _rostered("real-agent")

    resp = await app.get(f"{P}/queue/real-agent?state=pending", headers=auth_headers)

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "'pending'" in detail
    assert all(state in detail for state in ("queued", "delivered", "withdrawn"))


async def test_usage_for_an_unknown_or_foreign_conversation_is_refused(app, auth_headers):
    async with async_session_factory() as session:
        session.add(Project(id="proj-other", name="Other"))
        await session.commit()
    own = await _conversation("real-agent")
    foreign = await _conversation("their-agent", project_id="proj-other")

    for conversation_id in ("conv-does-not-exist", foreign):
        resp = await app.get(
            f"{P}/accounting/conversations/{conversation_id}", headers=auth_headers
        )
        assert resp.status_code == 404, (conversation_id, resp.text)
        assert resp.json()["detail"] == "Conversation not found"

    measured = await app.get(f"{P}/accounting/conversations/{own}", headers=auth_headers)
    assert measured.status_code == 200, measured.text
    assert measured.json()["measured_turns"] == 0


async def test_a_ticket_for_a_deleted_project_opens_no_stream(app, auth_headers):
    """A ticket carries no database state, so one minted before the project was deleted still
    verifies. The header path answers 404 for that project; the ticket path must agree, and
    answer at once rather than hold open a stream nothing will broadcast on."""
    token, _ = _make_ticket("proj-deleted")

    resp = await asyncio.wait_for(
        app.get(f"/api/v1/projects/proj-deleted/events?token={token}"), timeout=10
    )

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Project not found"
