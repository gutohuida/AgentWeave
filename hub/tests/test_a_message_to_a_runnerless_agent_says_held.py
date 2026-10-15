"""F623: a message to an agent with no runner tells its sender it is held, and the team says why.

alpha's `send_message` to runnerless gamma answered `{"success": true}` and the entry sat queued
until the operator bound a runner; the turn context's Team block listed gamma as `runner=native`
and the palette read "Native". The hop-budget hold already carried a delivery note (F361); this
is the same contract for the other hold a sender cannot see.
"""

from unittest.mock import AsyncMock, patch

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run

pytestmark = pytest.mark.asyncio

P = "/api/v1/projects/proj-test"


async def _sender(run_id: str, agent: str) -> dict[str, str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _send(app, headers, to):
    with patch("hub.turn_scheduler.schedule_accepted", AsyncMock()):
        return await app.post(
            "/api/v1/agent-actions/messages",
            headers=headers,
            json={"recipient": to, "content": "hello"},
        )


async def test_a_message_to_an_agent_with_no_runner_says_it_is_held(app, add_agent):
    await add_agent("alpha")
    await add_agent("gamma")
    headers = await _sender("run-f623-a", "alpha")

    response = await _send(app, headers, "gamma")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["held"] == "no_runner"
    assert not body["held_by_hop_budget"]
    note = body["delivery_note"]
    assert "gamma has no runner" in note
    assert body["id"] in note
    assert "binds one" in note


async def test_a_message_to_a_bound_agent_carries_no_note(app, add_agent, bind_runner):
    await add_agent("alpha")
    await add_agent("beta")
    await bind_runner("beta")
    headers = await _sender("run-f623-b", "alpha")

    body = (await _send(app, headers, "beta")).json()

    assert body["held"] is None
    assert body["delivery_note"] is None


async def test_send_message_tool_carries_a_no_runner_hold():
    from hub import mcp_server

    held = {"id": "msg-1", "held": "no_runner", "delivery_note": "Recorded as msg-1, but"}
    with patch.object(mcp_server, "_hub_request", return_value=held):
        reply = mcp_server.send_message(to_agent="gamma", subject="s", content="x")
    assert reply["success"] is True
    assert reply["held"] == "no_runner"
    assert reply["delivery_note"] == "Recorded as msg-1, but"


async def test_the_team_block_and_roster_say_no_runner(app, auth_headers, add_agent, bind_runner):
    await add_agent("alpha")
    await add_agent("gamma")
    await bind_runner("alpha")

    context = await app.get(f"{P}/agents/agent-context?agent=alpha", headers=auth_headers)
    assert context.status_code == 200, context.text
    text = context.text
    assert "`gamma`: no runner" in text
    assert "`gamma`: runner=native" not in text

    roster = {a["name"]: a for a in (await app.get(f"{P}/agents", headers=auth_headers)).json()}
    assert roster["gamma"]["display_model"] == "No runner"
    assert roster["alpha"]["display_model"] != "No runner"
