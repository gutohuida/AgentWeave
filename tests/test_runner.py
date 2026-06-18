"""Tests for agentweave.runner.

Covers the three helpers that drive the claude_proxy runner (v0.12.0+):

  get_agent_env              — env-var overrides for ANTHROPIC_BASE_URL / API key
  get_missing_api_key_var    — diagnostic: which env var is missing
  build_claude_proxy_cmd     — command-line construction for the claude CLI

These are shared between cli.py (switch / run) and watchdog.py (auto-ping),
so a regression here breaks every claude_proxy agent invocation.
"""

import os

import pytest

from agentweave import runner
from agentweave.runner import (
    build_claude_proxy_cmd,
    get_agent_env,
    get_missing_api_key_var,
)


# ---------------------------------------------------------------------------
# Stub session
# ---------------------------------------------------------------------------


class _StubSession:
    """Minimal Session-like object for runner helpers.

    Real Session.get_runner_config reads from the on-disk session.json,
    but for unit tests we only need a stable config dict per agent.
    """

    def __init__(self, configs):
        self._configs = dict(configs)

    def get_runner_config(self, agent):
        return self._configs.get(agent, {"runner": "native"})


# ---------------------------------------------------------------------------
# get_agent_env
# ---------------------------------------------------------------------------


def test_get_agent_env_returns_empty_for_native_runner():
    """A native runner has no env overrides."""
    s = _StubSession({"alice": {"runner": "native"}})
    assert get_agent_env(s, "alice") == {}


def test_get_agent_env_returns_empty_for_manual_runner():
    """A manual runner also has no env overrides."""
    s = _StubSession({"alice": {"runner": "manual"}})
    assert get_agent_env(s, "alice") == {}


def test_get_agent_env_returns_overrides_when_base_url_and_key_var_set(
    monkeypatch,
):
    """When ANTHROPIC_BASE_URL and ANTHROPIC_API_KEY_VAR are both set in the
    agent config AND the actual key is in os.environ, return the overrides."""
    monkeypatch.setenv("MY_KEY", "sk-test-123")
    s = _StubSession(
        {
            "minimax": {
                "runner": "claude_proxy",
                "env_vars": {
                    "ANTHROPIC_BASE_URL": "https://api.minimaxi.com",
                    "ANTHROPIC_API_KEY_VAR": "MY_KEY",
                },
            }
        }
    )
    env = get_agent_env(s, "minimax")
    assert env == {
        "ANTHROPIC_BASE_URL": "https://api.minimaxi.com",
        "ANTHROPIC_API_KEY": "sk-test-123",
    }


def test_get_agent_env_returns_empty_when_key_var_not_in_environ(
    monkeypatch,
):
    """If the configured key var is unset in os.environ, return {} so the
    caller can warn the user (do not leak a partial override)."""
    monkeypatch.delenv("MY_KEY", raising=False)
    s = _StubSession(
        {
            "minimax": {
                "runner": "claude_proxy",
                "env_vars": {
                    "ANTHROPIC_BASE_URL": "https://api.minimaxi.com",
                    "ANTHROPIC_API_KEY_VAR": "MY_KEY",
                },
            }
        }
    )
    assert get_agent_env(s, "minimax") == {}


def test_get_agent_env_returns_empty_when_base_url_missing():
    """If the agent config lacks ANTHROPIC_BASE_URL, return {} (claude_proxy
    is misconfigured; caller will warn)."""
    s = _StubSession(
        {
            "minimax": {
                "runner": "claude_proxy",
                "env_vars": {"ANTHROPIC_API_KEY_VAR": "MY_KEY"},
            }
        }
    )
    assert get_agent_env(s, "minimax") == {}


# ---------------------------------------------------------------------------
# get_missing_api_key_var
# ---------------------------------------------------------------------------


def test_get_missing_api_key_var_returns_var_name_when_unset(
    monkeypatch,
):
    """The diagnostic helper must name the env var the user needs to set."""
    monkeypatch.delenv("MY_KEY", raising=False)
    s = _StubSession(
        {
            "minimax": {
                "runner": "claude_proxy",
                "env_vars": {"ANTHROPIC_API_KEY_VAR": "MY_KEY"},
            }
        }
    )
    assert get_missing_api_key_var(s, "minimax") == "MY_KEY"


def test_get_missing_api_key_var_returns_none_when_key_present(
    monkeypatch,
):
    """When the env var IS set, the diagnostic must return None (nothing missing)."""
    monkeypatch.setenv("MY_KEY", "sk-test-123")
    s = _StubSession(
        {
            "minimax": {
                "runner": "claude_proxy",
                "env_vars": {"ANTHROPIC_API_KEY_VAR": "MY_KEY"},
            }
        }
    )
    assert get_missing_api_key_var(s, "minimax") is None


def test_get_missing_api_key_var_returns_none_for_native_agent():
    """A native agent has no API key requirement — return None."""
    s = _StubSession({"alice": {"runner": "native"}})
    assert get_missing_api_key_var(s, "alice") is None


# ---------------------------------------------------------------------------
# build_claude_proxy_cmd
# ---------------------------------------------------------------------------


def test_build_claude_proxy_cmd_minimal():
    """Minimal invocation: no session_id, no model."""
    cmd = build_claude_proxy_cmd("claude", "hello")
    assert cmd[:3] == ["claude", "--output-format", "stream-json"]
    assert "--verbose" in cmd
    assert cmd[-2:] == ["-p", "hello"]


def test_build_claude_proxy_cmd_with_session_id():
    """A session_id must add --resume <id> between --verbose and -p."""
    cmd = build_claude_proxy_cmd("claude", "hello", session_id="sess-42")
    # Find the indices so we don't depend on unrelated flags' order.
    assert cmd[cmd.index("--resume") + 1] == "sess-42"
    assert cmd[-2:] == ["-p", "hello"]


def test_build_claude_proxy_cmd_with_model():
    """A model must add --model <m> between --verbose and -p."""
    cmd = build_claude_proxy_cmd("claude", "hello", model="opus-4")
    assert cmd[cmd.index("--model") + 1] == "opus-4"
    assert cmd[-2:] == ["-p", "hello"]


def test_build_claude_proxy_cmd_with_both_session_and_model():
    """Session + model together must not collide."""
    cmd = build_claude_proxy_cmd(
        "claude", "hi", session_id="sess-1", model="sonnet-4"
    )
    assert cmd[cmd.index("--resume") + 1] == "sess-1"
    assert cmd[cmd.index("--model") + 1] == "sonnet-4"
    assert cmd[-2:] == ["-p", "hi"]
