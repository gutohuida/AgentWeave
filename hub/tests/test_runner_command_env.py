"""Run-token forwarding into dynamically configured runner tool servers."""

from hub.runner_adapters import build_command


def test_codex_mcp_server_whitelists_run_identity_environment():
    command = build_command(
        runner="codex",
        cli="codex",
        prompt="verify",
        mcp_command=["python", "mcp_server.py"],
    )

    config_values = [command[index + 1] for index, item in enumerate(command[:-1]) if item == "-c"]
    env_config = next(
        value for value in config_values if value.startswith("mcp_servers.agentweave.env_vars=")
    )

    assert "AW_RUN_TOKEN" in env_config
    assert "AW_AGENT_IDENTITY" in env_config
    assert "AW_RUN_ID" in env_config
    assert "HUB_URL" in env_config
    assert "aw_run_" not in env_config


# ---------------------------------------------------------------------------------------------
# The Copilot environment filter (`a-copilot-agent-runs-over-acp` task 1.16, design D3)
# ---------------------------------------------------------------------------------------------

import pytest  # noqa: E402

from hub.launchability import (  # noqa: E402
    COPILOT_TRUST_ENV_NAMES,
    copilot_env_removal_sentence,
    copilot_guard_env,
    resolve_agent_env,
)

_TOKENS = ("GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN")
_PROVIDER_AND_MODEL = (
    "COPILOT_PROVIDER_BASE_URL",
    "COPILOT_PROVIDER_BEARER_TOKEN",
    "COPILOT_PROVIDER_WIRE_MODEL",
    "COPILOT_MODEL",
    "COPILOT_OFFLINE",
)


def _keys(env):
    return {key.upper() for key in env}


def test_ambient_github_tokens_are_removed_from_a_copilot_spawn(monkeypatch):
    for name in _TOKENS:
        monkeypatch.setenv(name, "ghp_ambient")
    env = resolve_agent_env("copilot", {})
    assert env is not None
    assert not _keys(env) & set(_TOKENS)


def test_a_token_the_agent_names_is_kept(monkeypatch):
    monkeypatch.setenv("COPILOT_GITHUB_TOKEN", "ghp_mine")
    monkeypatch.setenv("GH_TOKEN", "ghp_ambient")
    env = resolve_agent_env(
        "copilot", {"env_vars": {"COPILOT_GITHUB_TOKEN": "COPILOT_GITHUB_TOKEN"}}
    )
    assert env["COPILOT_GITHUB_TOKEN"] == "ghp_mine"
    assert "GH_TOKEN" not in _keys(env)


def test_claudes_environment_is_unchanged(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_ambient")
    monkeypatch.setenv("COPILOT_ALLOW_ALL", "true")
    assert resolve_agent_env("claude", {}) is None


@pytest.mark.parametrize("name", COPILOT_TRUST_ENV_NAMES + _PROVIDER_AND_MODEL)
def test_trust_provider_and_model_variables_never_reach_a_copilot_spawn(name, monkeypatch):
    monkeypatch.setenv(name, "true")
    assert name not in _keys(resolve_agent_env("copilot", {}))

    monkeypatch.delenv(name)
    env, removed = copilot_guard_env({"PATH": "x"}, {name: "true"})
    assert name not in _keys(env)
    assert removed == [name]
    env = resolve_agent_env("copilot", {"env_vars": {name: "true"}})
    assert name not in _keys(env)


def test_an_ambient_trust_variable_is_removed_without_being_reported(monkeypatch):
    env, removed = copilot_guard_env({"COPILOT_ALLOW_ALL": "true", "PATH": "x"}, {})
    assert "COPILOT_ALLOW_ALL" not in env
    assert removed == []


def test_copilot_home_from_env_vars_does_not_survive():
    env, _removed = copilot_guard_env({"COPILOT_HOME": "C:/mine", "PATH": "x"}, {})
    assert "COPILOT_HOME" not in env
    env = resolve_agent_env("copilot", {"env_vars": {"COPILOT_HOME": "C:/elsewhere"}})
    assert "COPILOT_HOME" not in _keys(env)


def test_removal_sentences_name_the_right_remedy():
    assert "Full access" in copilot_env_removal_sentence("COPILOT_ALLOW_ALL")
    assert "from its runner" in copilot_env_removal_sentence("COPILOT_PROVIDER_BASE_URL")
    assert "from its runner" in copilot_env_removal_sentence("COPILOT_MODEL")
