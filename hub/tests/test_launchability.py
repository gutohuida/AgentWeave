"""Tests for the per-agent launchability probe (Phase 3 task 3.2)."""

import pytest

from hub.launchability import probe_agent


class TestProbeAgent:
    def test_manual_runner_is_never_runnable(self):
        result = probe_agent("claude", {"runner": "manual"})
        assert result["runnable"] is False
        assert result["present"] is False
        assert "manual" in result["reason"].lower()

    def test_cli_present_and_no_auth_requirement_is_runnable(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: "/usr/bin/claude")
        result = probe_agent("claude", {"runner": "claude"})
        assert result["present"] is True
        assert result["authorized"] is True
        assert result["runnable"] is True
        assert result["reason"] is None
        assert result["cli"] == "claude"

    def test_cli_missing_from_path(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: None)
        result = probe_agent("kimi", {"runner": "kimi"})
        assert result["present"] is False
        assert result["runnable"] is False
        assert "not found in PATH" in result["reason"]

    def test_native_runner_falls_back_to_agent_name_as_cli(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            "hub.launchability.shutil.which",
            lambda cli: seen.setdefault("cli", cli) and "/usr/bin/mycli",
        )
        result = probe_agent("mycli", {"runner": "native"})
        assert result["cli"] == "mycli"
        assert seen["cli"] == "mycli"

    def test_cli_override_checks_absolute_path_not_which(self, monkeypatch, tmp_path):
        # An override must never fall through to a PATH lookup — the whole point of
        # pinning is to bypass PATH ambiguity.
        def _boom(cli):
            raise AssertionError("shutil.which should not be called for a pinned cli")

        monkeypatch.setattr("hub.launchability.shutil.which", _boom)

        missing = tmp_path / "nonexistent-binary"
        result = probe_agent("claude", {"runner": "claude", "cli": str(missing)})
        assert result["present"] is False
        assert "not an executable file" in result["reason"]

    def test_pilot_mode_blocks_runnable_even_when_present_and_authorized(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: "/usr/bin/claude")
        result = probe_agent("claude", {"runner": "claude", "pilot": True})
        assert result["present"] is True
        assert result["authorized"] is True
        assert result["runnable"] is False
        assert "pilot mode" in result["reason"]

    def test_claude_proxy_requires_base_url_and_api_key_var(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: "/usr/bin/claude")
        result = probe_agent("minimax", {"runner": "claude_proxy"})
        assert result["authorized"] is False
        assert "ANTHROPIC_BASE_URL" in result["reason"]

    def test_claude_proxy_requires_the_api_key_env_var_to_be_set(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: "/usr/bin/claude")
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        result = probe_agent(
            "minimax",
            {
                "runner": "claude_proxy",
                "env_vars": {
                    "ANTHROPIC_BASE_URL": "https://api.minimax.io/anthropic",
                    "ANTHROPIC_API_KEY_VAR": "MINIMAX_API_KEY",
                },
            },
        )
        assert result["authorized"] is False
        assert "MINIMAX_API_KEY" in result["reason"]

    def test_claude_proxy_runnable_once_env_var_is_set(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: "/usr/bin/claude")
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")
        result = probe_agent(
            "minimax",
            {
                "runner": "claude_proxy",
                "env_vars": {
                    "ANTHROPIC_BASE_URL": "https://api.minimax.io/anthropic",
                    "ANTHROPIC_API_KEY_VAR": "MINIMAX_API_KEY",
                },
            },
        )
        assert result["authorized"] is True
        assert result["runnable"] is True

    def test_copilot_requires_a_github_token(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: "/usr/bin/copilot")
        for var in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        result = probe_agent("copilot-agent", {"runner": "copilot"})
        assert result["authorized"] is False
        assert "GitHub auth token" in result["reason"]

    def test_copilot_runnable_with_any_recognized_token_var(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: "/usr/bin/copilot")
        monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        result = probe_agent("copilot-agent", {"runner": "copilot"})
        assert result["authorized"] is True
        assert result["runnable"] is True


@pytest.mark.asyncio
async def test_launchability_endpoint_reports_configured_agents(app, auth_headers, monkeypatch):
    monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: None)

    sync_resp = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"claude": {"runner": "claude"}, "backup": {"runner": "manual"}}}},
        headers=auth_headers,
    )
    assert sync_resp.status_code == 200

    resp = await app.get("/api/v1/agents/launchability", headers=auth_headers)
    assert resp.status_code == 200
    agents = resp.json()["agents"]

    assert agents["claude"]["runnable"] is False
    assert agents["claude"]["present"] is False
    assert agents["backup"]["runnable"] is False
    assert agents["backup"]["reason"] == "Runner is set to manual — no CLI to launch automatically."
