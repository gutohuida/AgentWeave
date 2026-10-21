"""F815: an agent's message sent while the token budget is spent tells its sender it is held.

beta's `send_message` to alpha answered plain success while alpha's turn waited ("token budget
exhausted") until the operator raised the budget, so beta reported a delivery that could not happen.
Hop budget (F361) and no runner (F623) already say so; this is the third hold. The operator's own
message still runs on a spent budget (F814), so it is never held.
"""

from unittest.mock import AsyncMock, patch

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Project, Run, TurnUsage

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"


async def _spend_the_budget():
    async with async_session_factory() as db:
        project = await db.get(Project, PROJECT)
        project.token_budget = 100
        db.add(Run(id="run-spent-815", project_id=PROJECT, agent="history", status="completed"))
        db.add(
            TurnUsage(
                id="usage-spent-815",
                project_id=PROJECT,
                run_id="run-spent-815",
                agent="history",
                status="measured",
                input_tokens=500,
                output_tokens=0,
                total_tokens=500,
            )
        )
        await db.commit()


async def _sender(run_id: str, agent: str) -> dict[str, str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id=PROJECT,
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


async def test_an_agent_message_on_a_spent_budget_says_it_is_held(app, add_agent, bind_runner):
    await add_agent("alpha")
    await add_agent("beta")
    await bind_runner("alpha")
    await _spend_the_budget()
    headers = await _sender("run-f815-a", "beta")

    response = await _send(app, headers, "alpha")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["held"] == "token_budget"
    assert not body["held_by_hop_budget"]
    note = body["delivery_note"]
    assert "token budget is spent" in note
    assert body["id"] in note
    assert "alpha" in note


async def test_an_agent_message_with_budget_left_carries_no_note(app, add_agent, bind_runner):
    await add_agent("alpha")
    await add_agent("beta")
    await bind_runner("alpha")
    headers = await _sender("run-f815-b", "beta")

    body = (await _send(app, headers, "alpha")).json()

    assert body["held"] is None
    assert body["delivery_note"] is None


async def test_the_operators_message_on_a_spent_budget_is_not_held(
    app, auth_headers, add_agent, bind_runner
):
    await add_agent("alpha")
    await bind_runner("alpha")
    await _spend_the_budget()

    with patch("hub.turn_scheduler.schedule_accepted", AsyncMock()):
        response = await app.post(
            f"/api/v1/projects/{PROJECT}/messages",
            headers=auth_headers,
            json={"recipient": "alpha", "content": "hello"},
        )

    assert response.status_code == 201, response.text
    assert response.json()["held"] is None
