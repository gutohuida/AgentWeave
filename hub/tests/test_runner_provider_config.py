"""A Copilot runner on a model provider (BYOK), through `POST /runners` and `PATCH /runners/{id}`.

Task 1.7 of `a-copilot-agent-uses-hooks-and-its-own-agents` (design D7). The runner stores the
provider's address and the *name* of the variable that holds its key; every refusal is a 400 with
a string `detail` that never repeats a submitted value, so a pasted key never reaches a response.
"""

import re

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import Runner

PROJECT = "proj-test"
RUNNERS = f"/api/v1/projects/{PROJECT}/runners"
HAIKU = "claude-haiku-4-5-20251001"
PROVIDER = {"type": "anthropic", "api_key_var": "MY_ANTHROPIC_KEY"}


async def _runner_count() -> int:
    async with async_session_factory() as db:
        return (await db.execute(select(func.count()).select_from(Runner))).scalar_one()


async def _stored(runner_id: str) -> tuple:
    async with async_session_factory() as db:
        row = await db.get(Runner, runner_id)
        return row.model, row.flags, row.provider_config


async def _create(app, auth_headers, **body):
    payload = {"name": "BYOK", "cli": "copilot", **body}
    return await app.post(RUNNERS, json=payload, headers=auth_headers)


async def _refused(response, *, not_containing: str = "") -> str:
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, str), detail
    if not_containing:
        assert not_containing not in response.text
    return detail


async def _provider_runner(app, auth_headers, **extra) -> dict:
    response = await _create(app, auth_headers, model=HAIKU, provider_config=PROVIDER, **extra)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- create


@pytest.mark.asyncio
async def test_a_provider_runner_is_created_with_the_variable_name_and_no_key(app, auth_headers):
    body = await _provider_runner(app, auth_headers)
    assert body["provider_config"] == {
        "type": "anthropic",
        "base_url": "https://api.anthropic.com",
        "api_key_var": "MY_ANTHROPIC_KEY",
    }
    assert body["model"] == HAIKU
    assert body["model_unrecognised"] is False
    assert "api_key" not in body["provider_config"]
    assert (await _stored(body["id"]))[2] == body["provider_config"]

    listing = await app.get(RUNNERS, headers=auth_headers)
    listed = next(r for r in listing.json() if r["id"] == body["id"])
    assert listed["provider_config"]["api_key_var"] == "MY_ANTHROPIC_KEY"
    assert listed["model_unrecognised"] is False


@pytest.mark.asyncio
async def test_a_pasted_key_as_the_variable_name_is_refused_and_nothing_is_stored(
    app, auth_headers
):
    before = await _runner_count()
    response = await _create(
        app,
        auth_headers,
        model=HAIKU,
        provider_config={"type": "anthropic", "api_key_var": "sk-ant-api03-xyz"},
    )
    detail = await _refused(response, not_containing="sk-ant-api03-xyz")
    assert "name of an environment variable" in detail
    assert "Hub's environment" in detail
    assert await _runner_count() == before


@pytest.mark.asyncio
async def test_a_long_pasted_key_gets_the_sentence_not_a_422(app, auth_headers):
    pasted = "sk-ant-" + "x" * 293
    assert len(pasted) == 300
    response = await _create(
        app, auth_headers, model=HAIKU, provider_config={"type": "anthropic", "api_key_var": pasted}
    )
    detail = await _refused(response, not_containing=pasted)
    assert "name of an environment variable" in detail


@pytest.mark.asyncio
async def test_a_key_under_an_unknown_field_is_refused_by_name_never_by_value(app, auth_headers):
    response = await _create(
        app,
        auth_headers,
        model=HAIKU,
        provider_config={"type": "anthropic", "api_key": "sk-ant-test-value"},
    )
    detail = await _refused(response, not_containing="sk-ant-test-value")
    assert "'api_key'" in detail


@pytest.mark.asyncio
async def test_a_pasted_key_as_a_field_name_is_not_repeated(app, auth_headers):
    response = await _create(
        app,
        auth_headers,
        model=HAIKU,
        provider_config={"type": "anthropic", "sk-ant-test-value": "MY_ANTHROPIC_KEY"},
    )
    await _refused(response, not_containing="sk-ant-test-value")


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [12345, ["MY_ANTHROPIC_KEY"], {"name": "MY_ANTHROPIC_KEY"}])
async def test_a_non_string_variable_name_is_refused_with_a_400(app, auth_headers, value):
    response = await _create(
        app,
        auth_headers,
        model=HAIKU,
        provider_config={"type": "anthropic", "api_key_var": value},
    )
    detail = await _refused(response)
    assert "api_key_var" in detail


@pytest.mark.asyncio
async def test_a_provider_config_that_is_not_an_object_is_refused_with_a_400(app, auth_headers):
    response = await _create(app, auth_headers, model=HAIKU, provider_config="sk-ant-test-value")
    await _refused(response, not_containing="sk-ant-test-value")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name", ["GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN", "DATABASE_URL", "AW_ANYTHING"]
)
async def test_a_hub_credential_is_refused_as_the_variable(app, auth_headers, name):
    response = await _create(
        app, auth_headers, model=HAIKU, provider_config={"type": "anthropic", "api_key_var": name}
    )
    detail = await _refused(response)
    assert "Hub's own credentials" in detail
    assert name in detail


@pytest.mark.asyncio
async def test_a_claude_runner_cannot_carry_a_provider(app, auth_headers):
    before = await _runner_count()
    response = await app.post(
        RUNNERS,
        json={"name": "C", "cli": "claude", "model": HAIKU, "provider_config": PROVIDER},
        headers=auth_headers,
    )
    detail = await _refused(response)
    assert "Only a copilot runner" in detail
    assert await _runner_count() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_type", ["azure", "openai"])
async def test_deferred_provider_types_are_refused(app, auth_headers, provider_type):
    response = await _create(
        app, auth_headers, model=HAIKU, provider_config={**PROVIDER, "type": provider_type}
    )
    detail = await _refused(response)
    assert "'anthropic'" in detail


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["not-a-model", "auto", "gpt-6-sol"])
async def test_a_model_the_claude_catalog_does_not_declare_is_refused(app, auth_headers, model):
    response = await _create(app, auth_headers, model=model, provider_config=PROVIDER)
    detail = await _refused(response)
    assert HAIKU in detail


@pytest.mark.asyncio
async def test_no_model_is_refused_on_create(app, auth_headers):
    response = await _create(app, auth_headers, provider_config=PROVIDER)
    detail = await _refused(response)
    assert "needs a model" in detail


@pytest.mark.asyncio
async def test_an_alias_is_refused_and_the_sentence_does_not_offer_it(app, auth_headers):
    """`ProviderDescriptor.model()` resolves `haiku` since `63d9f34`, and the shared
    `undeclared_model_reason` names aliases as acceptable. Neither may be the provider rule."""
    response = await _create(app, auth_headers, model="haiku", provider_config=PROVIDER)
    detail = await _refused(response)
    assert "(or " not in detail
    assert not re.search(r"(?<![\w-])haiku(?![\w-])", detail), detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base_url",
    ["http://localhost.evil.com", "http://localhost@evil.com", "http://example.com", "ftp://x.y"],
)
async def test_an_address_that_would_send_the_key_off_the_machine_in_clear_is_refused(
    app, auth_headers, base_url
):
    response = await _create(
        app, auth_headers, model=HAIKU, provider_config={**PROVIDER, "base_url": base_url}
    )
    detail = await _refused(response)
    assert "base_url" in detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:4000",
        "http://127.0.0.1:4000",
        "http://[::1]:4000",
        "https://example.com",
    ],
)
async def test_a_local_or_https_address_is_accepted(app, auth_headers, base_url):
    response = await _create(
        app, auth_headers, model=HAIKU, provider_config={**PROVIDER, "base_url": base_url}
    )
    assert response.status_code == 201, response.text
    assert response.json()["provider_config"]["base_url"] == base_url


@pytest.mark.asyncio
@pytest.mark.parametrize("flags", [["--model", "haiku"], ["--model=haiku"]])
async def test_a_model_flag_on_a_provider_runner_is_refused_on_create(app, auth_headers, flags):
    response = await _create(app, auth_headers, model=HAIKU, provider_config=PROVIDER, flags=flags)
    detail = await _refused(response)
    assert "--model" in detail


# --------------------------------------------------------------------------- PATCH


@pytest.mark.asyncio
async def test_patch_setting_model_null_on_a_provider_runner_is_refused(app, auth_headers):
    runner = await _provider_runner(app, auth_headers)
    response = await app.patch(
        f"{RUNNERS}/{runner['id']}", json={"model": None}, headers=auth_headers
    )
    await _refused(response)
    assert (await _stored(runner["id"]))[0] == HAIKU


@pytest.mark.asyncio
async def test_patch_adding_a_provider_to_a_runner_on_auto_is_judged_on_the_pair(app, auth_headers):
    """R3: the legacy `model == current` exemption must not let a stored `auto` through."""
    created = await _create(app, auth_headers, model="auto")
    assert created.status_code == 201, created.text
    runner_id = created.json()["id"]

    refused = await app.patch(
        f"{RUNNERS}/{runner_id}", json={"provider_config": PROVIDER}, headers=auth_headers
    )
    await _refused(refused)
    assert await _stored(runner_id) == ("auto", None, None)

    accepted = await app.patch(
        f"{RUNNERS}/{runner_id}",
        json={"provider_config": PROVIDER, "model": HAIKU},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["provider_config"]["api_key_var"] == "MY_ANTHROPIC_KEY"
    assert (await _stored(runner_id))[0] == HAIKU


@pytest.mark.asyncio
async def test_patch_removing_the_provider_needs_a_copilot_model_or_none(app, auth_headers):
    runner = await _provider_runner(app, auth_headers)
    url = f"{RUNNERS}/{runner['id']}"

    refused = await app.patch(url, json={"provider_config": None}, headers=auth_headers)
    assert "Without its model provider" in await _refused(refused)
    assert (await _stored(runner["id"]))[2] is not None

    to_auto = await app.patch(
        url, json={"provider_config": None, "model": "auto"}, headers=auth_headers
    )
    assert to_auto.status_code == 200, to_auto.text
    assert await _stored(runner["id"]) == ("auto", None, None)


@pytest.mark.asyncio
async def test_patch_removing_the_provider_with_model_null_is_accepted(app, auth_headers):
    runner = await _provider_runner(app, auth_headers)
    response = await app.patch(
        f"{RUNNERS}/{runner['id']}",
        json={"provider_config": None, "model": None},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert await _stored(runner["id"]) == (None, None, None)


@pytest.mark.asyncio
async def test_patch_adding_a_provider_to_a_runner_whose_flags_carry_model_is_refused(
    app, auth_headers
):
    created = await _create(app, auth_headers, model="auto", flags=["--model=auto"])
    assert created.status_code == 201, created.text
    runner_id = created.json()["id"]

    response = await app.patch(
        f"{RUNNERS}/{runner_id}",
        json={"provider_config": PROVIDER, "model": HAIKU},
        headers=auth_headers,
    )
    detail = await _refused(response)
    assert "--model" in detail
    assert await _stored(runner_id) == ("auto", ["--model=auto"], None)


@pytest.mark.asyncio
async def test_patch_adding_a_model_flag_to_a_provider_runner_is_refused(app, auth_headers):
    runner = await _provider_runner(app, auth_headers)
    response = await app.patch(
        f"{RUNNERS}/{runner['id']}", json={"flags": ["--model", "haiku"]}, headers=auth_headers
    )
    await _refused(response)
    assert (await _stored(runner["id"]))[1] is None


@pytest.mark.asyncio
async def test_patch_a_pasted_key_is_refused_and_the_row_is_unchanged(app, auth_headers):
    runner = await _provider_runner(app, auth_headers)
    response = await app.patch(
        f"{RUNNERS}/{runner['id']}",
        json={"provider_config": {"type": "anthropic", "api_key_var": "sk-ant-api03-xyz"}},
        headers=auth_headers,
    )
    await _refused(response, not_containing="sk-ant-api03-xyz")
    assert (await _stored(runner["id"]))[2]["api_key_var"] == "MY_ANTHROPIC_KEY"


@pytest.mark.asyncio
async def test_patch_renaming_a_provider_runner_keeps_its_provider(app, auth_headers):
    runner = await _provider_runner(app, auth_headers)
    response = await app.patch(
        f"{RUNNERS}/{runner['id']}", json={"name": "Renamed"}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["provider_config"] == runner["provider_config"]


@pytest.mark.asyncio
async def test_a_damaged_stored_provider_does_not_break_the_runner_list(app, auth_headers):
    async with async_session_factory() as db:
        db.add(
            Runner(
                id="runner-damaged",
                project_id=PROJECT,
                name="Damaged",
                cli="copilot",
                model=HAIKU,
                provider_config="not-a-dict",
            )
        )
        await db.commit()
    listing = await app.get(RUNNERS, headers=auth_headers)
    assert listing.status_code == 200, listing.text
    assert any(r["id"] == "runner-damaged" for r in listing.json())


# --------------------------------------------------------------------------- checkpoint model


@pytest.mark.asyncio
async def test_a_provider_checkpoint_runner_refuses_a_checkpoint_model_it_cannot_send(
    app, auth_headers
):
    """Review 2026-09-28, finding 1. The route is `PUT /projects/{id}/settings` (the task's
    "PATCH /projects" names the same settings write)."""
    runner = await _provider_runner(app, auth_headers)
    settings = {
        "name": "Testbed",
        "hop_budget": 6,
        "turn_delivery_cap": 10,
        "agent_budget": 8,
        "token_budget": None,
        "allow_agent_jobs": False,
        "checkpoint_mode": "offered",
        "checkpoint_runner_id": runner["id"],
    }
    refused = await app.put(
        f"/api/v1/projects/{PROJECT}/settings",
        json={**settings, "checkpoint_model": "auto"},
        headers=auth_headers,
    )
    detail = await _refused(refused)
    assert "checkpoint_model" in detail
    assert HAIKU in detail

    accepted = await app.put(
        f"/api/v1/projects/{PROJECT}/settings",
        json={**settings, "checkpoint_model": HAIKU},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["checkpoint_model"] == HAIKU
