"""Configuring checkpointing, at the project and at the agent.

Tasks 8.4-8.7 of 2026-08-07-conversation-handoff-rework, at the API boundary.

The recurring failure these guard against is a setting that looks configured and cannot fire:
half a threshold completed from elsewhere, a token count above the model's window, or a notes
point at or after the cutover it is supposed to precede.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Agent, Runner

PROJECT = "proj-test"


def _settings(**overrides):
    body = {
        "name": "Testbed",
        "hop_budget": 6,
        "turn_delivery_cap": 10,
        "agent_budget": 8,
        "token_budget": None,
        "allow_agent_jobs": False,
    }
    body.update(overrides)
    return body


async def _runner(app, auth_headers, runner_id="runner-cheap"):
    async with async_session_factory() as db:
        db.add(
            Runner(
                id=runner_id,
                project_id=PROJECT,
                name="Cheap",
                cli="claude",
                model="claude-haiku-4-5-20251001",
            )
        )
        await db.commit()
    return runner_id


# --------------------------------------------------------------------------- project settings


@pytest.mark.asyncio
async def test_a_project_can_be_put_on_automatic_with_a_token_threshold(app, auth_headers):
    runner_id = await _runner(app, auth_headers)
    response = await app.put(
        f"/api/v1/projects/{PROJECT}/settings",
        json=_settings(
            checkpoint_mode="automatic",
            checkpoint_threshold_mode="tokens",
            checkpoint_threshold_value=150_000,
            checkpoint_notes_value=120_000,
            checkpoint_runner_id=runner_id,
            checkpoint_model="claude-haiku-4-5-20251001",
        ),
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["checkpoint_threshold_value"] == 150_000


@pytest.mark.asyncio
async def test_half_a_threshold_is_refused(app, auth_headers):
    """Not a partial setting to be completed from elsewhere: a value of 150 inheriting `percent`
    reads as 150% and never fires."""
    for partial in (
        {"checkpoint_threshold_mode": "tokens"},
        {"checkpoint_threshold_value": 150_000},
    ):
        response = await app.put(
            f"/api/v1/projects/{PROJECT}/settings",
            json=_settings(**partial),
            headers=auth_headers,
        )
        assert response.status_code == 422, response.text
        assert "together" in response.text


async def _bound_agent(name, runner_id, model, *, own_threshold=None):
    async with async_session_factory() as db:
        db.add(Runner(id=runner_id, project_id=PROJECT, name=runner_id, cli="claude", model=model))
        agent = Agent(id=f"agent-{name}", project_id=PROJECT, name=name, runner_id=runner_id)
        if own_threshold:
            agent.checkpoint_threshold_mode = "tokens"
            agent.checkpoint_threshold_value = own_threshold
        db.add(agent)
        await db.commit()


@pytest.mark.asyncio
async def test_the_checkpoint_workers_window_does_not_judge_a_project_threshold(app, auth_headers):
    """F541. A project threshold applies to the project's agents; the model that writes the
    checkpoint has its own window, which says nothing about when one is due. 250k against a
    worker on Haiku (200k) with no agent that it could miss is accepted, with nothing to warn of."""
    response = await app.put(
        f"/api/v1/projects/{PROJECT}/settings",
        json=_settings(
            checkpoint_threshold_mode="tokens",
            checkpoint_threshold_value=250_000,
            checkpoint_model="claude-haiku-4-5-20251001",
        ),
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["warnings"] == []


@pytest.mark.asyncio
async def test_a_project_threshold_that_cannot_fire_for_an_agent_is_saved_with_a_warning(
    app, auth_headers
):
    """F541, decided `overhaul-token-threshold-window`: warn, not refuse. The Haiku agent can
    never reach 250k; the Opus agent can, and an agent with its own threshold is not governed by
    the project's."""
    await _bound_agent("small", "runner-small", "claude-haiku-4-5-20251001")
    await _bound_agent("big", "runner-big", "claude-opus-5-5")
    await _bound_agent("own", "runner-own", "claude-haiku-4-5-20251001", own_threshold=100_000)
    response = await app.put(
        f"/api/v1/projects/{PROJECT}/settings",
        json=_settings(checkpoint_threshold_mode="tokens", checkpoint_threshold_value=250_000),
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["checkpoint_threshold_value"] == 250_000
    assert len(body["warnings"]) == 1
    assert "small" in body["warnings"][0] and "never fire" in body["warnings"][0]
    assert "big" not in body["warnings"][0] and "own" not in body["warnings"][0]


@pytest.mark.asyncio
async def test_a_token_threshold_above_the_agents_own_window_is_refused(app, auth_headers):
    """F541. Haiku 4.5's window is 200k; an agent on it with a 250k threshold would never
    checkpoint. The agent route used to check nothing against any window."""
    await _bound_agent("small", "runner-small", "claude-haiku-4-5-20251001")
    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/small",
        json={"checkpoint_threshold_mode": "tokens", "checkpoint_threshold_value": 250_000},
        headers=auth_headers,
    )
    assert response.status_code == 400, response.text
    assert "never fire" in response.text
    async with async_session_factory() as db:
        row = (await db.execute(select(Agent).where(Agent.name == "small"))).scalars().one()
    assert row.checkpoint_threshold_value is None


@pytest.mark.asyncio
async def test_the_agent_window_is_the_one_the_same_patch_binds(app, auth_headers):
    """A body that rebinds the runner and sets the threshold is judged against the new model."""
    await _bound_agent("mover", "runner-small", "claude-haiku-4-5-20251001")
    async with async_session_factory() as db:
        db.add(Runner(id="runner-big", project_id=PROJECT, name="big", cli="claude", model="opus"))
        await db.commit()
    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/mover",
        json={
            "runner_id": "runner-big",
            "checkpoint_threshold_mode": "tokens",
            "checkpoint_threshold_value": 250_000,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_an_agent_threshold_is_accepted_where_its_window_is_unknown(app, auth_headers):
    name = await _agent(app, auth_headers)
    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{name}",
        json={"checkpoint_threshold_mode": "tokens", "checkpoint_threshold_value": 250_000},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_the_same_threshold_is_accepted_when_no_model_is_chosen(app, auth_headers):
    """Task 8.8's other half: an unknown window is not evidence that a number is wrong."""
    response = await app.put(
        f"/api/v1/projects/{PROJECT}/settings",
        json=_settings(checkpoint_threshold_mode="tokens", checkpoint_threshold_value=250_000),
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_a_notes_point_at_or_after_the_threshold_is_refused(app, auth_headers):
    """It would ask for notes from exactly the context the cutover exists to escape."""
    response = await app.put(
        f"/api/v1/projects/{PROJECT}/settings",
        json=_settings(
            checkpoint_threshold_mode="percent",
            checkpoint_threshold_value=80,
            checkpoint_notes_value=80,
        ),
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "below the checkpoint threshold" in response.text


@pytest.mark.asyncio
async def test_a_checkpoint_runner_from_another_project_is_refused(app, auth_headers):
    response = await app.put(
        f"/api/v1/projects/{PROJECT}/settings",
        json=_settings(checkpoint_runner_id="runner-elsewhere"),
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "belongs to this project" in response.text


# --------------------------------------------------------------------------- agent overrides


async def _agent(app, auth_headers, name="claude-1"):
    async with async_session_factory() as db:
        db.add(Agent(id=f"agent-{name}", project_id=PROJECT, name=name))
        await db.commit()
    return name


@pytest.mark.asyncio
async def test_an_agent_can_override_the_whole_threshold(app, auth_headers):
    name = await _agent(app, auth_headers)
    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{name}",
        json={"checkpoint_threshold_mode": "percent", "checkpoint_threshold_value": 60},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["checkpoint_threshold_value"] == 60

    async with async_session_factory() as db:
        row = (await db.execute(select(Agent).where(Agent.name == name))).scalars().one()
    assert (row.checkpoint_threshold_mode, row.checkpoint_threshold_value) == ("percent", 60)


@pytest.mark.asyncio
async def test_an_agent_cannot_override_half_a_threshold(app, auth_headers):
    name = await _agent(app, auth_headers)
    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{name}",
        json={"checkpoint_threshold_value": 150},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "half a threshold" in response.text


@pytest.mark.asyncio
async def test_clearing_an_agent_override_returns_it_to_the_projects_threshold(app, auth_headers):
    name = await _agent(app, auth_headers)
    await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{name}",
        json={
            "checkpoint_threshold_mode": "percent",
            "checkpoint_threshold_value": 60,
            "checkpoint_notes_value": 50,
        },
        headers=auth_headers,
    )
    cleared = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{name}",
        json={"checkpoint_threshold_mode": None, "checkpoint_threshold_value": None},
        headers=auth_headers,
    )
    assert cleared.status_code == 200, cleared.text

    async with async_session_factory() as db:
        row = (await db.execute(select(Agent).where(Agent.name == name))).scalars().one()

    assert row.checkpoint_threshold_mode is None
    assert row.checkpoint_threshold_value is None
    # The notes point goes with it. Left behind it would sit under a threshold it was never
    # measured against.
    assert row.checkpoint_notes_value is None


@pytest.mark.asyncio
async def test_an_agent_can_opt_out_while_inheriting_the_projects_threshold(app, auth_headers):
    name = await _agent(app, auth_headers)
    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{name}",
        json={"checkpoint_mode": "off"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["checkpoint_mode"] == "off"
    assert response.json()["checkpoint_threshold_mode"] is None


@pytest.mark.asyncio
async def test_a_null_agent_mode_means_inherit_not_off(app, auth_headers):
    name = await _agent(app, auth_headers)
    await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{name}",
        json={"checkpoint_mode": "automatic"},
        headers=auth_headers,
    )
    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{name}",
        json={"checkpoint_mode": None},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["checkpoint_mode"] is None


@pytest.mark.asyncio
async def test_an_unknown_agent_mode_is_refused(app, auth_headers):
    name = await _agent(app, auth_headers)
    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{name}",
        json={"checkpoint_mode": "whenever"},
        headers=auth_headers,
    )
    assert response.status_code == 400


# --------------------------------------------------------------------------- partial saves


@pytest.mark.asyncio
async def test_saving_an_unrelated_setting_does_not_clear_checkpointing(app, auth_headers):
    """Reproduces the defect this change exists to fix.

    `PUT /settings` replaces every field from its model, and every checkpoint field carries a
    default, so a client that submits only the fields it knows about resets the rest. The settings
    panel is exactly such a client: `ProjectSettingsInput` is a `Pick` of `ProjectSummary`, which
    carries neither the checkpoint fields nor the conversation-title ones.

    Observed live before the fix: eight fields configured, eight fields gone, HTTP 200. Silent and
    destructive, and indistinguishable afterwards from never having configured them.
    """
    runner_id = await _runner(app, auth_headers)
    configured = await app.put(
        f"/api/v1/projects/{PROJECT}/settings",
        json=_settings(
            checkpoint_mode="automatic",
            checkpoint_threshold_mode="percent",
            checkpoint_threshold_value=80,
            checkpoint_notes_value=70,
            checkpoint_runner_id=runner_id,
            checkpoint_model="claude-haiku-4-5-20251001",
        ),
        headers=auth_headers,
    )
    assert configured.status_code == 200, configured.text

    # Exactly what the panel submits: the six fields it can see, and nothing else.
    renamed = await app.put(
        f"/api/v1/projects/{PROJECT}/settings",
        json={
            "name": "Renamed",
            "hop_budget": 6,
            "turn_delivery_cap": 10,
            "agent_budget": 8,
            "token_budget": None,
            "allow_agent_jobs": False,
        },
        headers=auth_headers,
    )
    assert renamed.status_code == 200, renamed.text

    after = await app.get(f"/api/v1/projects/{PROJECT}/settings", headers=auth_headers)
    body = after.json()
    assert body["name"] == "Renamed"
    assert body["checkpoint_mode"] == "automatic"
    assert body["checkpoint_threshold_mode"] == "percent"
    assert body["checkpoint_threshold_value"] == 80
    assert body["checkpoint_notes_value"] == 70
    assert body["checkpoint_runner_id"] == runner_id
    assert body["checkpoint_model"] == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_a_field_sent_as_null_is_still_cleared(app, auth_headers):
    """Omission must mean "leave alone" without making a deliberate clear impossible — otherwise
    the fix trades one unreachable state for another."""
    runner_id = await _runner(app, auth_headers)
    await app.put(
        f"/api/v1/projects/{PROJECT}/settings",
        json=_settings(checkpoint_mode="offered", checkpoint_runner_id=runner_id),
        headers=auth_headers,
    )
    cleared = await app.put(
        f"/api/v1/projects/{PROJECT}/settings",
        json=_settings(checkpoint_mode="off", checkpoint_runner_id=None),
        headers=auth_headers,
    )
    assert cleared.status_code == 200, cleared.text

    after = (await app.get(f"/api/v1/projects/{PROJECT}/settings", headers=auth_headers)).json()
    assert after["checkpoint_mode"] == "off"
    assert after["checkpoint_runner_id"] is None
