"""A Copilot agent on a model-provider (BYOK) runner: what reaches its run.

Task 1.8 of `a-copilot-agent-uses-hooks-and-its-own-agents` (design D7). This file holds the
per-run half so far: a provider runner's model is the runner's own, so a run may not choose
another, and one a conversation stored before the agent reached the provider runner is not applied.
The environment half lands with task 3.3.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from hub.conversations import get_conversation_by_id
from hub.copilot_acp import TurnOutcome
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Run
from hub.runner_events import text_event

from ._background_runs import await_background_runs

PROJECT = "proj-test"
HAIKU = "claude-haiku-4-5-20251001"
PROVIDER = {"type": "anthropic", "api_key_var": "MY_ANTHROPIC_KEY"}
# A `copilot` catalog id: valid as a per-run override on a plain Copilot runner, and exactly what
# must never be sent to the Anthropic API as a model name.
COPILOT_MODEL = "claude-haiku-4.5"


@pytest.fixture(autouse=True)
def _copilot_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    exe = tmp_path / "copilot.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr("hub.copilot_probe.resolve_copilot_executable", lambda override: exe)
    monkeypatch.setenv("MY_ANTHROPIC_KEY", "sk-ant-test-value")
    return tmp_path


def _fake_turn():
    async def _run(**kwargs):
        await kwargs["on_session"]("sess-1")
        await kwargs["on_event"](text_event("hello from copilot"))
        return TurnOutcome(session_id="sess-1", status="completed")

    return AsyncMock(side_effect=_run)


async def _agent(app, auth_headers, name: str) -> None:
    sync = await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {name: {"runner": "copilot"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text


async def _runner(app, auth_headers, name: str, **body) -> str:
    created = await app.post(
        f"/api/v1/projects/{PROJECT}/runners",
        json={"name": name, "cli": "copilot", **body},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _bind(app, auth_headers, agent: str, runner_id: str) -> None:
    bound = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{agent}",
        json={"runner_id": runner_id},
        headers=auth_headers,
    )
    assert bound.status_code == 200, bound.text


async def _provider_agent(app, auth_headers, name: str) -> None:
    await _agent(app, auth_headers, name)
    runner_id = await _runner(
        app, auth_headers, f"{name}-byok", model=HAIKU, provider_config=PROVIDER
    )
    await _bind(app, auth_headers, name, runner_id)


async def _trigger(app, auth_headers, agent: str, **body):
    return await app.post(
        f"/api/v1/projects/{PROJECT}/agent/trigger",
        json={"agent": agent, "message": "hi", **body},
        headers=auth_headers,
    )


async def _counts(agent: str) -> tuple:
    async with async_session_factory() as db:
        runs = (
            await db.execute(select(func.count()).select_from(Run).where(Run.agent == agent))
        ).scalar_one()
        entries = (
            await db.execute(
                select(func.count())
                .select_from(InboundQueueEntry)
                .where(InboundQueueEntry.agent == agent)
            )
        ).scalar_one()
        stored = (
            (await db.execute(select(Conversation).where(Conversation.agent == agent)))
            .scalars()
            .all()
        )
        return runs, entries, [c.runtime_overrides for c in stored]


@pytest.mark.asyncio
async def test_a_model_override_on_a_provider_runner_is_refused_before_anything_exists(
    app, auth_headers
):
    await _provider_agent(app, auth_headers, "byok-1")
    fake = _fake_turn()
    with patch("hub.copilot_acp.run_turn", fake):
        response = await _trigger(
            app, auth_headers, "byok-1", session_mode="new", overrides={"model": "auto"}
        )
        await await_background_runs()

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert "runner's own model" in detail
    fake.assert_not_called()
    runs, entries, overrides = await _counts("byok-1")
    assert (runs, entries) == (0, 0)
    assert all(not stored for stored in overrides), overrides


@pytest.mark.asyncio
async def test_a_copilot_catalog_model_is_refused_too_and_the_stored_overrides_do_not_move(
    app, auth_headers
):
    """A model a plain Copilot runner accepts is the very one that must not reach the provider."""
    await _provider_agent(app, auth_headers, "byok-2")
    fake = _fake_turn()
    with patch("hub.copilot_acp.run_turn", fake):
        first = await _trigger(app, auth_headers, "byok-2", session_mode="new")
        assert first.status_code == 200, first.text
        await await_background_runs()
        conversation_id = first.json()["conversation_id"]

        refused = await _trigger(
            app,
            auth_headers,
            "byok-2",
            conversation_id=conversation_id,
            overrides={"model": COPILOT_MODEL},
        )
        await await_background_runs()

    assert refused.status_code == 400, refused.text
    assert fake.call_count == 1
    runs, _, overrides = await _counts("byok-2")
    assert runs == 1
    assert overrides == [None] or overrides == [{}], overrides


@pytest.mark.asyncio
async def test_other_controls_still_apply_on_a_provider_runner(app, auth_headers):
    await _provider_agent(app, auth_headers, "byok-3")
    fake = _fake_turn()
    with patch("hub.copilot_acp.run_turn", fake):
        response = await _trigger(
            app, auth_headers, "byok-3", session_mode="new", overrides={"effort": "high"}
        )
        assert response.status_code == 200, response.text
        await await_background_runs()

    fake.assert_called_once()
    assert fake.call_args.kwargs["model"] == HAIKU
    _, _, overrides = await _counts("byok-3")
    assert overrides == [{"effort": "high"}]


@pytest.mark.asyncio
async def test_a_plain_copilot_runner_still_takes_a_model_override(app, auth_headers):
    await _agent(app, auth_headers, "plain-1")
    await _bind(app, auth_headers, "plain-1", await _runner(app, auth_headers, "plain-1-r"))
    fake = _fake_turn()
    with patch("hub.copilot_acp.run_turn", fake):
        response = await _trigger(
            app, auth_headers, "plain-1", session_mode="new", overrides={"model": COPILOT_MODEL}
        )
        assert response.status_code == 200, response.text
        await await_background_runs()

    assert fake.call_args.kwargs["model"] == COPILOT_MODEL


@pytest.mark.asyncio
async def test_a_model_stored_before_the_rebind_is_not_applied_and_is_kept(app, auth_headers):
    """R3: overrides are trusted at spawn, so a `model` stored while the agent was on a plain
    Copilot runner would reach the provider unless the spawn itself ignores it."""
    await _agent(app, auth_headers, "rebound")
    await _bind(app, auth_headers, "rebound", await _runner(app, auth_headers, "rebound-plain"))
    fake = _fake_turn()
    with patch("hub.copilot_acp.run_turn", fake):
        first = await _trigger(
            app, auth_headers, "rebound", session_mode="new", overrides={"model": COPILOT_MODEL}
        )
        assert first.status_code == 200, first.text
        await await_background_runs()
        assert fake.call_args.kwargs["model"] == COPILOT_MODEL
        conversation_id = first.json()["conversation_id"]

        provider_runner = await _runner(
            app, auth_headers, "rebound-byok", model=HAIKU, provider_config=PROVIDER
        )
        await _bind(app, auth_headers, "rebound", provider_runner)
        second = await _trigger(app, auth_headers, "rebound", conversation_id=conversation_id)
        assert second.status_code == 200, second.text
        await await_background_runs()

    assert fake.call_count == 2
    assert fake.call_args.kwargs["model"] == HAIKU
    async with async_session_factory() as db:
        conversation = await get_conversation_by_id(db, conversation_id)
    # Left in place, not applied: rebinding back to the plain runner restores it.
    assert conversation.runtime_overrides == {"model": COPILOT_MODEL}
