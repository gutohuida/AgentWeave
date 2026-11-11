"""Choosing a model for an agent directly (`settings-in-the-app-s-style-where-you-expect-them`,
FR-9): PATCH an agent with `provider` and `model` and the Hub binds it to the project's runner for
them, reusing one that exists and making one only when none does."""

import pytest

BASE = "/api/v1/projects/proj-test"


async def _runners(app, auth_headers):
    return (await app.get(f"{BASE}/runners", headers=auth_headers)).json()


async def _agent(app, auth_headers, name):
    roster = (await app.get(f"{BASE}/agents", headers=auth_headers)).json()
    return next(a for a in roster if a["name"] == name)


@pytest.mark.asyncio
async def test_ac_model_new_choosing_an_unused_model_makes_one_runner(
    app, auth_headers, add_agent, bind_runner
):
    await add_agent("sonnet-agent")
    await bind_runner("sonnet-agent", cli="claude", model="claude-sonnet-5-5")
    before = [r for r in await _runners(app, auth_headers) if r["model"] == "claude-haiku-5-5"]
    assert before == []

    resp = await app.patch(
        f"{BASE}/agents/sonnet-agent",
        json={"provider": "claude", "model": "claude-haiku-5-5"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    made = [r for r in await _runners(app, auth_headers) if r["model"] == "claude-haiku-5-5"]
    assert len(made) == 1 and made[0]["cli"] == "claude"
    agent = await _agent(app, auth_headers, "sonnet-agent")
    assert agent["runner_id"] == made[0]["id"]
    assert agent["display_model"] == "claude-haiku-5-5"


@pytest.mark.asyncio
async def test_ac_model_reuse_a_second_agent_shares_the_existing_runner(
    app, auth_headers, add_agent, bind_runner
):
    await add_agent("first-agent")
    await add_agent("second-agent")
    await bind_runner("first-agent", cli="claude", model="claude-opus-5-5")
    existing = (await _agent(app, auth_headers, "first-agent"))["runner_id"]
    count = len(await _runners(app, auth_headers))

    resp = await app.patch(
        f"{BASE}/agents/second-agent",
        json={"provider": "claude", "model": "claude-opus-5-5"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    assert len(await _runners(app, auth_headers)) == count
    assert (await _agent(app, auth_headers, "second-agent"))["runner_id"] == existing
    assert (await _agent(app, auth_headers, "first-agent"))["runner_id"] == existing


@pytest.mark.asyncio
async def test_the_providers_own_default_is_a_runner_with_no_model(app, auth_headers, add_agent):
    await add_agent("default-agent")
    resp = await app.patch(
        f"{BASE}/agents/default-agent",
        json={"provider": "claude", "model": None},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    again = await app.patch(
        f"{BASE}/agents/default-agent",
        json={"provider": "claude", "model": None},
        headers=auth_headers,
    )
    assert again.status_code == 200
    plain = [
        r for r in await _runners(app, auth_headers) if r["cli"] == "claude" and r["model"] is None
    ]
    assert len(plain) == 1


@pytest.mark.asyncio
async def test_an_undeclared_model_or_a_mixed_body_is_refused(app, auth_headers, add_agent):
    await add_agent("refused-agent")
    unknown = await app.patch(
        f"{BASE}/agents/refused-agent",
        json={"provider": "claude", "model": "no-such-model"},
        headers=auth_headers,
    )
    assert unknown.status_code == 400
    both = await app.patch(
        f"{BASE}/agents/refused-agent",
        json={"provider": "claude", "model": "claude-opus-5-5", "runner_id": "runner-x"},
        headers=auth_headers,
    )
    assert both.status_code == 400
