"""A Copilot agent on a model-provider (BYOK) runner: what reaches its run.

Task 1.8 of `a-copilot-agent-uses-hooks-and-its-own-agents` (design D7). This file holds the
per-run half: a provider runner's model is the runner's own, so a run may not choose another, and
one a conversation stored before the agent reached the provider runner is not applied. Then task
3.3's first slice: the run's environment (the provider's variables exactly, or none) and
launchability through the routes. Then 3.3's second slice: the one-shot spawns (checkpoints, their
probes, handovers, titles) get the same variables, and the runner's model.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from hub.conversation_titles import generate_conversation_title
from hub.conversations import get_conversation_by_id
from hub.copilot_acp import TurnOutcome
from hub.db.engine import async_session_factory
from hub.db.models import (
    Conversation,
    InboundQueueEntry,
    Project,
    Run,
    Runner,
    WorkerInvocation,
)
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


# --- The environment half (task 3.3, first slice): what the trigger hands Copilot's turn. ---

AMBIENT_PROVIDER = {
    "COPILOT_PROVIDER_BASE_URL": "https://attacker.example",
    "COPILOT_PROVIDER_TYPE": "openai",
    "COPILOT_MODEL": "gpt-5",
    "COPILOT_OFFLINE": "1",
}
# Names R3's "overwrite the four" would have left in place (review 2026-09-28, finding 3).
OUTRANKING = {
    "COPILOT_PROVIDER_BEARER_TOKEN": "bearer-value",
    "COPILOT_PROVIDER_WIRE_MODEL": "wire-model",
    "COPILOT_PROVIDER_API_KEY_COMMAND": "echo other-key",
    "COPILOT_PROVIDER_HEADERS": "X-Extra: 1",
}


def _provider_names(env: dict) -> dict:
    return {
        key: value
        for key, value in env.items()
        if key.upper().startswith("COPILOT_PROVIDER_")
        or key.upper() in ("COPILOT_MODEL", "COPILOT_OFFLINE")
    }


async def _run_env(app, auth_headers, agent: str) -> dict:
    fake = _fake_turn()
    with patch("hub.copilot_acp.run_turn", fake):
        response = await _trigger(app, auth_headers, agent, session_mode="new")
        assert response.status_code == 200, response.text
        await await_background_runs()
    fake.assert_called_once()
    return fake.call_args.kwargs["env"]


async def _agent_with(app, auth_headers, name: str, **meta) -> None:
    sync = await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {name: {"runner": "copilot", **meta}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text


@pytest.mark.asyncio
async def test_a_provider_runners_run_gets_exactly_the_providers_variables(
    app, auth_headers, monkeypatch
):
    for name, value in {**AMBIENT_PROVIDER, **OUTRANKING}.items():
        monkeypatch.setenv(name, value)
    await _provider_agent(app, auth_headers, "env-1")

    env = await _run_env(app, auth_headers, "env-1")

    assert _provider_names(env) == {
        "COPILOT_PROVIDER_TYPE": "anthropic",
        "COPILOT_PROVIDER_BASE_URL": "https://api.anthropic.com",
        "COPILOT_PROVIDER_API_KEY": "sk-ant-test-value",
        "COPILOT_MODEL": HAIKU,
    }


@pytest.mark.asyncio
async def test_an_agents_env_vars_cannot_add_to_a_provider_runners_variables(app, auth_headers):
    """Finding 3, the second source: the agent's own `env_vars`, merged before the guard."""
    await _agent_with(app, auth_headers, "env-2", env_vars={**OUTRANKING, "COPILOT_MODEL": "gpt-5"})
    runner_id = await _runner(
        app, auth_headers, "env-2-byok", model=HAIKU, provider_config=PROVIDER
    )
    await _bind(app, auth_headers, "env-2", runner_id)

    env = await _run_env(app, auth_headers, "env-2")

    assert sorted(_provider_names(env)) == [
        "COPILOT_MODEL",
        "COPILOT_PROVIDER_API_KEY",
        "COPILOT_PROVIDER_BASE_URL",
        "COPILOT_PROVIDER_TYPE",
    ]
    assert env["COPILOT_MODEL"] == HAIKU


@pytest.mark.asyncio
async def test_a_plain_runners_run_gets_no_provider_variables_from_the_hubs_shell(
    app, auth_headers, monkeypatch
):
    """Ungrouped (task 2.8): kept whichever groups survive."""
    for name, value in AMBIENT_PROVIDER.items():
        monkeypatch.setenv(name, value)
    await _agent(app, auth_headers, "plain-env-1")
    await _bind(app, auth_headers, "plain-env-1", await _runner(app, auth_headers, "plain-env-r"))

    env = await _run_env(app, auth_headers, "plain-env-1")

    assert _provider_names(env) == {}


@pytest.mark.asyncio
async def test_a_plain_runners_run_gets_none_from_the_agents_env_vars_either(app, auth_headers):
    """R3: a copy of the Claude guard's `env_vars` exemption would let these through."""
    await _agent_with(app, auth_headers, "plain-env-2", env_vars=dict(AMBIENT_PROVIDER))
    await _bind(app, auth_headers, "plain-env-2", await _runner(app, auth_headers, "plain-env-r2"))

    env = await _run_env(app, auth_headers, "plain-env-2")

    assert _provider_names(env) == {}


@pytest.mark.asyncio
async def test_a_provider_named_in_the_agents_own_config_is_not_a_provider(app, auth_headers):
    """A model provider is a runner's alone: session.json cannot make a plain runner's runs BYOK."""
    await _agent_with(app, auth_headers, "spoof", provider_config=PROVIDER)
    await _bind(app, auth_headers, "spoof", await _runner(app, auth_headers, "spoof-r"))

    env = await _run_env(app, auth_headers, "spoof")

    assert _provider_names(env) == {}


def test_a_missing_key_builds_an_empty_key_rather_than_raising(monkeypatch):
    """Finding 10: `guard_env` must not raise, and must not fall back to the subscription."""
    from hub.launchability import resolve_agent_env

    monkeypatch.delenv("MY_ANTHROPIC_KEY")
    env = resolve_agent_env(
        "copilot", {"runner": "copilot", "model": HAIKU, "provider_config": PROVIDER}
    )

    assert env is not None
    assert _provider_names(env) == {
        "COPILOT_PROVIDER_TYPE": "anthropic",
        "COPILOT_PROVIDER_BASE_URL": "https://api.anthropic.com",
        "COPILOT_PROVIDER_API_KEY": "",
        "COPILOT_MODEL": HAIKU,
    }


# --- Launchability, through the routes (design D7, R3's table of sites). ---

NOT_SIGNED_IN = "Copilot is not signed in to GitHub. Run `copilot login`."


@pytest.fixture
def _not_signed_in(monkeypatch):
    from hub.copilot_probe import CopilotProbe

    for name in ("GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    def _verdict(cls, cli_override=None):
        return {
            "runner": "copilot",
            "cli": "copilot.exe",
            "present": True,
            "authorized": False,
            "runnable": False,
            "reason": NOT_SIGNED_IN,
            "version": "1.0.88",
        }

    monkeypatch.setattr(CopilotProbe, "verdict", classmethod(_verdict))


async def _verdicts(app, auth_headers, agent: str, runner_id: str) -> tuple:
    runners = await app.get(
        f"/api/v1/projects/{PROJECT}/runners/launchability", headers=auth_headers
    )
    agents = await app.get(f"/api/v1/projects/{PROJECT}/agents/launchability", headers=auth_headers)
    assert runners.status_code == 200, runners.text
    assert agents.status_code == 200, agents.text
    return runners.json()["runners"][runner_id], agents.json()["agents"][agent]


@pytest.mark.asyncio
async def test_without_its_key_variable_a_provider_runner_is_not_authorized_and_says_which(
    app, auth_headers, monkeypatch, _not_signed_in
):
    await _agent(app, auth_headers, "lk-1")
    runner_id = await _runner(app, auth_headers, "lk-1-byok", model=HAIKU, provider_config=PROVIDER)
    await _bind(app, auth_headers, "lk-1", runner_id)
    monkeypatch.delenv("MY_ANTHROPIC_KEY")

    for verdict in await _verdicts(app, auth_headers, "lk-1", runner_id):
        assert verdict["present"] is True
        assert verdict["authorized"] is False
        assert verdict["runnable"] is False
        assert "MY_ANTHROPIC_KEY" in verdict["reason"]
        assert "GitHub" not in verdict["reason"]
        assert verdict["version"] == "1.0.88"

    fake = _fake_turn()
    with patch("hub.copilot_acp.run_turn", fake):
        refused = await _trigger(app, auth_headers, "lk-1", session_mode="new")
        await await_background_runs()
    # The trigger's launchability refusal: the input waits, with the reason, and nothing runs.
    assert refused.status_code == 200, refused.text
    assert refused.json()["status"] == "queued"
    assert refused.json()["run_id"] is None
    assert "MY_ANTHROPIC_KEY" in refused.json()["waiting_reason"]
    fake.assert_not_called()
    runs, _, _ = await _counts("lk-1")
    assert runs == 0


@pytest.mark.asyncio
async def test_with_its_key_variable_a_provider_runner_runs_without_a_github_login(
    app, auth_headers, _not_signed_in
):
    await _agent(app, auth_headers, "lk-2")
    runner_id = await _runner(app, auth_headers, "lk-2-byok", model=HAIKU, provider_config=PROVIDER)
    await _bind(app, auth_headers, "lk-2", runner_id)

    for verdict in await _verdicts(app, auth_headers, "lk-2", runner_id):
        assert verdict["authorized"] is True, verdict
        assert verdict["runnable"] is True, verdict
        assert verdict["reason"] is None

    created = await app.post(
        f"/api/v1/projects/{PROJECT}/agents",
        json={"name": "lk-2-new", "runner_id": runner_id},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text


@pytest.mark.asyncio
async def test_a_plain_runner_still_reports_copilots_own_verdict(app, auth_headers, _not_signed_in):
    await _agent(app, auth_headers, "lk-3")
    runner_id = await _runner(app, auth_headers, "lk-3-plain")
    await _bind(app, auth_headers, "lk-3", runner_id)

    for verdict in await _verdicts(app, auth_headers, "lk-3", runner_id):
        assert verdict["authorized"] is False
        assert verdict["reason"] == NOT_SIGNED_IN

    created = await app.post(
        f"/api/v1/projects/{PROJECT}/agents",
        json={"name": "lk-3-new", "runner_id": runner_id},
        headers=auth_headers,
    )
    assert created.status_code == 409, created.text


@pytest.mark.asyncio
async def test_a_damaged_stored_provider_is_reported_not_raised_on(app, auth_headers):
    """Read defensively: one bad row must not 500 the launchability list for every agent."""
    from hub.db.models import Runner

    await _agent(app, auth_headers, "lk-4")
    runner_id = await _runner(app, auth_headers, "lk-4-byok", model=HAIKU, provider_config=PROVIDER)
    await _bind(app, auth_headers, "lk-4", runner_id)
    async with async_session_factory() as db:
        row = await db.get(Runner, runner_id)
        row.provider_config = "sk-ant-pasted-into-the-wrong-place"
        await db.commit()

    for verdict in await _verdicts(app, auth_headers, "lk-4", runner_id):
        assert verdict["authorized"] is False
        assert "damaged" in verdict["reason"]
        assert "sk-ant-pasted" not in verdict["reason"]


@pytest.mark.asyncio
async def test_an_unbound_agents_own_provider_is_not_judged_as_one(
    app, auth_headers, _not_signed_in
):
    """`get_agent_config` drops a session.json `provider_config`: an unbound agent configured
    there is still judged on Copilot's own verdict, not on a key variable it chose."""
    await _agent_with(app, auth_headers, "unbound-spoof", provider_config=PROVIDER, model=HAIKU)

    agents = await app.get(f"/api/v1/projects/{PROJECT}/agents/launchability", headers=auth_headers)

    assert agents.status_code == 200, agents.text
    assert agents.json()["agents"]["unbound-spoof"]["reason"] == NOT_SIGNED_IN


# ---------------------------------------------------------------------------
# Task 3.3's second slice, 1.8's one-shot half (review 2026-09-28, finding 1): a checkpoint, a
# handover and a title spawned on a provider runner get its variables and its model, through the
# real `run_worker` and titler with only the process spawn patched.
# ---------------------------------------------------------------------------

CHECKPOINT_BODY = {
    "objective": "Refuse an entry with no postings.",
    "state": "The guard was already correct; a test now pins it.",
}
PROVIDER_ENV = {
    "COPILOT_PROVIDER_TYPE": "anthropic",
    "COPILOT_PROVIDER_BASE_URL": "https://api.anthropic.com",
    "COPILOT_PROVIDER_API_KEY": "sk-ant-test-value",
    "COPILOT_MODEL": HAIKU,
}


def _copilot_answer(answer: str) -> str:
    """`copilot -p --output-format json`'s JSONL, as `parse_copilot_envelope` reads it."""
    lines = (
        {"type": "assistant.message", "data": {"content": answer}},
        {"type": "result", "sessionId": "one-shot"},
    )
    return "\n".join(json.dumps(line) for line in lines)


def _capture_worker(monkeypatch) -> list:
    """Every worker spawn's (argv, env), answering with a valid checkpoint body."""
    from hub.worker import _Spawn

    spawns: list = []

    def _spawn(cmd, cwd, timeout, env=None):
        spawns.append((list(cmd), dict(env or {})))
        return _Spawn("ok", stdout=_copilot_answer(json.dumps(CHECKPOINT_BODY)), exit_code=0)

    monkeypatch.setattr("hub.worker._run_worker_process", _spawn)
    return spawns


def _capture_titler(monkeypatch) -> list:
    spawns: list = []

    def _spawn(cmd, cwd, env=None):
        spawns.append((list(cmd), dict(env or {})))
        return _copilot_answer("Fix the checkout flake")

    monkeypatch.setattr("hub.conversation_titles._run_titler", _spawn)
    return spawns


def _model_flag(argv: list):
    return argv[argv.index("--model") + 1] if "--model" in argv else None


async def _checkpoint_seat(app, auth_headers, runner_id: str) -> None:
    """The project's checkpoint runner, chosen through the settings route as an operator does."""
    chosen = await app.put(
        f"/api/v1/projects/{PROJECT}/settings",
        json={
            "name": "Testbed",
            "hop_budget": 6,
            "turn_delivery_cap": 10,
            "agent_budget": 8,
            "token_budget": None,
            "allow_agent_jobs": False,
            "checkpoint_mode": "offered",
            "checkpoint_runner_id": runner_id,
        },
        headers=auth_headers,
    )
    assert chosen.status_code == 200, chosen.text


async def _store_checkpoint_model(model) -> None:
    """Written directly: a value stored before the runner gained a provider, which the settings
    route now refuses."""
    async with async_session_factory() as db:
        project = await db.get(Project, PROJECT)
        project.checkpoint_model = model
        await db.commit()


async def _conversation_with_a_turn(app, auth_headers, agent: str) -> str:
    """A real conversation with one finished (faked) Copilot turn in it."""
    with patch("hub.copilot_acp.run_turn", _fake_turn()):
        response = await _trigger(app, auth_headers, agent, session_mode="new")
        assert response.status_code == 200, response.text
        await await_background_runs()
    return response.json()["conversation_id"]


async def _operator_checkpoint(app, auth_headers, conversation_id: str):
    return await app.post(
        f"/api/v1/projects/{PROJECT}/conversations/{conversation_id}/checkpoint",
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_a_checkpoint_on_a_provider_runner_gets_the_providers_variables_and_model(
    app, auth_headers, monkeypatch
):
    for name, value in {**AMBIENT_PROVIDER, **OUTRANKING}.items():
        monkeypatch.setenv(name, value)
    await _provider_agent(app, auth_headers, "os-1")
    conversation_id = await _conversation_with_a_turn(app, auth_headers, "os-1")
    seat = await _runner(app, auth_headers, "os-1-seat", model=HAIKU, provider_config=PROVIDER)
    await _checkpoint_seat(app, auth_headers, seat)
    spawns = _capture_worker(monkeypatch)

    response = await _operator_checkpoint(app, auth_headers, conversation_id)

    assert response.status_code == 201, response.text
    # Generation, then its probe: both spawned on the provider runner.
    assert len(spawns) == 2
    for argv, env in spawns:
        assert _provider_names(env) == PROVIDER_ENV
        assert _model_flag(argv) == HAIKU


@pytest.mark.asyncio
async def test_a_checkpoint_model_stored_before_the_provider_is_ignored_for_the_runners(
    app, auth_headers, monkeypatch
):
    await _provider_agent(app, auth_headers, "os-2")
    conversation_id = await _conversation_with_a_turn(app, auth_headers, "os-2")
    seat = await _runner(app, auth_headers, "os-2-seat", model=HAIKU, provider_config=PROVIDER)
    await _checkpoint_seat(app, auth_headers, seat)
    await _store_checkpoint_model("auto")
    spawns = _capture_worker(monkeypatch)

    response = await _operator_checkpoint(app, auth_headers, conversation_id)

    assert response.status_code == 201, response.text
    assert spawns, "no generation spawned: the stored model was refused instead of ignored"
    for argv, env in spawns:
        assert _model_flag(argv) == HAIKU
        assert env["COPILOT_MODEL"] == HAIKU
    async with async_session_factory() as db:
        assert (await db.get(Project, PROJECT)).checkpoint_model == "auto", "left in place"


@pytest.mark.asyncio
async def test_the_context_pressure_trigger_resolves_the_runners_model_too(app, auth_headers):
    """The third generation site, `checkpoint_trigger._resolve_runner`: it hands the worker the
    same model the route and the handover do."""
    from hub.checkpoint_trigger import _resolve_runner

    seat = await _runner(app, auth_headers, "os-3-seat", model=HAIKU, provider_config=PROVIDER)
    await _checkpoint_seat(app, auth_headers, seat)
    await _store_checkpoint_model("auto")
    async with async_session_factory() as db:
        project = await db.get(Project, PROJECT)
        assert await _resolve_runner(db, project) == ("copilot", HAIKU, seat)

    # A Claude API id is the provider's to take, so a valid stored one still wins.
    await _store_checkpoint_model("claude-sonnet-5")
    async with async_session_factory() as db:
        project = await db.get(Project, PROJECT)
        assert await _resolve_runner(db, project) == ("copilot", "claude-sonnet-5", seat)


@pytest.mark.asyncio
async def test_a_handover_on_a_provider_checkpoint_runner_gets_its_variables(
    app, auth_headers, bind_runner, monkeypatch
):
    from hub.checkpoint_handover import consider_handover

    from .test_handover_briefs_the_reviewer import AUTHOR, _flow_handover
    from .test_review_turn import _roster

    await _roster(app, auth_headers, bind_runner, AUTHOR)
    seat = await _runner(app, auth_headers, "os-4-seat", model=HAIKU, provider_config=PROVIDER)
    await _checkpoint_seat(app, auth_headers, seat)
    await _store_checkpoint_model("auto")
    async with async_session_factory() as db:
        *_, run = await _flow_handover(db, suffix="byok")
    spawns = _capture_worker(monkeypatch)

    assert await consider_handover(run.id) is not None

    assert spawns
    for argv, env in spawns:
        assert _provider_names(env) == PROVIDER_ENV
        assert _model_flag(argv) == HAIKU


async def _title_mode(runner_id) -> None:
    async with async_session_factory() as db:
        project = await db.get(Project, PROJECT)
        project.conversation_title_mode = "generate"
        project.conversation_title_runner_id = runner_id
        await db.commit()


@pytest.mark.asyncio
async def test_a_title_on_the_projects_provider_title_runner_gets_its_variables(
    app, auth_headers, monkeypatch
):
    monkeypatch.setenv("COPILOT_PROVIDER_BEARER_TOKEN", "ambient-bearer")
    await _agent(app, auth_headers, "os-5")
    plain = await _runner(app, auth_headers, "os-5-plain")
    await _bind(app, auth_headers, "os-5", plain)
    conversation_id = await _conversation_with_a_turn(app, auth_headers, "os-5")
    seat = await _runner(app, auth_headers, "os-5-titles", model=HAIKU, provider_config=PROVIDER)
    await _title_mode(seat)
    spawns = _capture_titler(monkeypatch)

    title = await generate_conversation_title(project_id=PROJECT, conversation_id=conversation_id)

    assert title == "Fix the checkout flake"
    [(argv, env)] = spawns
    assert _provider_names(env) == PROVIDER_ENV
    assert _model_flag(argv) == HAIKU


@pytest.mark.asyncio
async def test_a_title_on_the_agents_own_provider_runner_gets_its_variables(
    app, auth_headers, monkeypatch
):
    await _provider_agent(app, auth_headers, "os-6")
    conversation_id = await _conversation_with_a_turn(app, auth_headers, "os-6")
    await _title_mode(None)
    spawns = _capture_titler(monkeypatch)

    assert await generate_conversation_title(project_id=PROJECT, conversation_id=conversation_id)

    [(argv, env)] = spawns
    assert _provider_names(env) == PROVIDER_ENV
    assert _model_flag(argv) == HAIKU


@pytest.mark.asyncio
async def test_a_plain_runners_one_shots_get_no_provider_variables_from_the_hubs_shell(
    app, auth_headers, monkeypatch
):
    """The ungrouped half (task 2.8): kept if group C is cut."""
    for name, value in {**AMBIENT_PROVIDER, **OUTRANKING}.items():
        monkeypatch.setenv(name, value)
    await _agent(app, auth_headers, "os-7")
    plain = await _runner(app, auth_headers, "os-7-plain")
    await _bind(app, auth_headers, "os-7", plain)
    conversation_id = await _conversation_with_a_turn(app, auth_headers, "os-7")
    await _checkpoint_seat(app, auth_headers, plain)
    await _title_mode(plain)
    worker_spawns = _capture_worker(monkeypatch)
    titler_spawns = _capture_titler(monkeypatch)

    assert (await _operator_checkpoint(app, auth_headers, conversation_id)).status_code == 201
    await generate_conversation_title(project_id=PROJECT, conversation_id=conversation_id)

    assert worker_spawns and titler_spawns
    for _argv, env in worker_spawns + titler_spawns:
        assert _provider_names(env) == {}


@pytest.mark.asyncio
async def test_a_damaged_provider_runner_spawns_no_one_shot_on_the_subscription(
    app, auth_headers, monkeypatch
):
    """No launchability check precedes a one-shot: a damaged stored provider is refused there,
    never quietly run on the GitHub subscription."""
    await _provider_agent(app, auth_headers, "os-8")
    conversation_id = await _conversation_with_a_turn(app, auth_headers, "os-8")
    seat = await _runner(app, auth_headers, "os-8-seat", model=HAIKU, provider_config=PROVIDER)
    await _checkpoint_seat(app, auth_headers, seat)
    async with async_session_factory() as db:
        for runner in (await db.execute(select(Runner))).scalars():
            if runner.provider_config is not None:
                runner.provider_config = {"type": "anthropic"}  # no key variable
        await db.commit()
    await _title_mode(None)
    worker_spawns = _capture_worker(monkeypatch)
    titler_spawns = _capture_titler(monkeypatch)

    await _operator_checkpoint(app, auth_headers, conversation_id)
    title = await generate_conversation_title(project_id=PROJECT, conversation_id=conversation_id)

    assert title is None
    assert worker_spawns == [] and titler_spawns == []
    async with async_session_factory() as db:
        outcomes = (
            (
                await db.execute(
                    select(WorkerInvocation.outcome).where(WorkerInvocation.runner_id == seat)
                )
            )
            .scalars()
            .all()
        )
    assert outcomes == ["spawn_failed"]


@pytest.mark.asyncio
async def test_the_worker_refuses_a_model_the_provider_would_not_take(
    app, auth_headers, monkeypatch
):
    """The worker judges a provider runner's model by the provider rule, as the runner registry
    does: not by the `copilot` catalog (which declares neither the runner's Claude API id nor
    refuses `auto`). Every generation site resolves a provider model first, so this is the gate
    behind them."""
    from hub.checkpoint_generation import CheckpointBody
    from hub.worker import run_worker

    seat = await _runner(app, auth_headers, "os-9-seat", model=HAIKU, provider_config=PROVIDER)
    spawns = _capture_worker(monkeypatch)

    async def _work(model):
        return await run_worker(
            project_id=PROJECT,
            kind="checkpoint",
            prompt="P",
            prompt_version="test",
            output_model=CheckpointBody,
            cli="copilot",
            model=model,
            runner_id=seat,
        )

    refused = await _work("auto")
    assert (refused.outcome, spawns) == ("unknown_model", [])
    assert "Claude API model id" in refused.error

    accepted = await _work(HAIKU)
    assert accepted.outcome == "ok", accepted.error
    assert len(spawns) == 1
