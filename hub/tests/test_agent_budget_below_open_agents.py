"""F728 (1): an agent budget set below the agents already open was saved with `warnings: []`, and
the Overview then read "10 of 8 agents". Warn, not refuse (the open agents keep working); the
warning says what the lower budget means and how to get back under it."""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Agent

PROJECT = "proj-test"


def _settings(agent_budget):
    return {
        "name": "Testbed",
        "hop_budget": 6,
        "turn_delivery_cap": 10,
        "agent_budget": agent_budget,
        "token_budget": None,
        "allow_agent_jobs": False,
    }


async def _agents(*names, archived=()):
    async with async_session_factory() as db:
        for name in (*names, *archived):
            db.add(
                Agent(
                    id=f"agent-{name}",
                    project_id=PROJECT,
                    name=name,
                    lifecycle="archived" if name in archived else "open",
                )
            )
        await db.commit()


async def _save(app, auth_headers, budget):
    response = await app.put(
        f"/api/v1/projects/{PROJECT}/settings", json=_settings(budget), headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_a_budget_below_the_open_agents_is_saved_with_a_warning(app, auth_headers):
    await _agents("a", "b", "c", archived=("old",))

    body = await _save(app, auth_headers, 2)

    assert body["agent_budget"] == 2
    assert len(body["warnings"]) == 1
    warning = body["warnings"][0]
    assert "now 2" in warning and "3 agents are open" in warning
    assert "until 2 are archived" in warning


@pytest.mark.asyncio
async def test_a_budget_the_open_agents_fit_warns_of_nothing(app, auth_headers):
    await _agents("a", "b", "c", archived=("old",))

    assert (await _save(app, auth_headers, 3))["warnings"] == []
