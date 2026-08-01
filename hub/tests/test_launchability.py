"""Tests for the per-agent launchability probe (Phase 3 task 3.2)."""

import pytest

from hub.launchability import (
    access_path_notice,
    get_agent_config,
    probe_agent,
    probe_mcp_registered,
    resolve_access_path,
    resolve_agent_env,
)


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


class TestResolveAgentEnv:
    """Task 3.11: the Hub resolves provider environment itself at spawn time, mirroring
    `agentweave.watchdog._prepare_agent_env`/`_prepare_runner_env`'s exact semantics —
    closing the gap that used to require `eval $(agentweave switch <agent>)`."""

    def test_no_env_vars_returns_none(self):
        assert resolve_agent_env("claude_proxy", {}) is None

    def test_resolves_anthropic_api_key_from_named_var(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax-secret")
        config = {
            "env_vars": {
                "ANTHROPIC_BASE_URL": "https://api.minimax.io/anthropic",
                "ANTHROPIC_API_KEY_VAR": "MINIMAX_API_KEY",
            }
        }
        env = resolve_agent_env("claude_proxy", config)
        assert env["ANTHROPIC_API_KEY"] == "sk-minimax-secret"
        assert env["ANTHROPIC_BASE_URL"] == "https://api.minimax.io/anthropic"
        # The Hub's own environment is inherited, not replaced.
        assert "PATH" in env or "Path" in env

    def test_missing_named_var_clears_inherited_key_without_raising(self, monkeypatch):
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "leftover-from-a-different-agent")
        config = {
            "env_vars": {
                "ANTHROPIC_BASE_URL": "https://api.minimax.io/anthropic",
                "ANTHROPIC_API_KEY_VAR": "MINIMAX_API_KEY",
            }
        }
        env = resolve_agent_env("claude_proxy", config)
        assert "ANTHROPIC_API_KEY" not in env

    def test_self_referencing_placeholder_is_resolved(self, monkeypatch):
        monkeypatch.setenv("GLM_API_KEY", "glm-secret")
        config = {"env_vars": {"GLM_API_KEY": "GLM_API_KEY"}}
        env = resolve_agent_env("claude_proxy", config)
        assert env["GLM_API_KEY"] == "glm-secret"

    def test_native_claude_strips_inherited_proxy_base_url(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://leaked-proxy.example.com")
        env = resolve_agent_env("claude", {})
        assert env is not None
        assert "ANTHROPIC_BASE_URL" not in env

    def test_non_claude_runner_keeps_inherited_base_url(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://intentional.example.com")
        env = resolve_agent_env("codex", {})
        # No env_vars configured and not the "claude" runner -> no override needed at all.
        assert env is None


class TestAccessPath:
    """Task 4.3: the access path (MCP tool-protocol server vs. plain CLI commands) is
    probed per runner rather than assumed — `hub_client` becomes the operator's explicit
    override, honored ahead of any probe."""

    @pytest.fixture(autouse=True)
    def _clear_probe_cache(self):
        # probe_mcp_registered caches by CLI name for _PROBE_TTL_SECONDS — several tests
        # here probe "claude"/"codex" with conflicting fake results, so each test must
        # start from an empty cache rather than observing a previous test's result.
        import hub.launchability as launchability

        launchability._probe_cache.clear()
        yield
        launchability._probe_cache.clear()

    def test_explicit_override_wins_without_probing(self, monkeypatch):
        def _boom(cli):
            raise AssertionError("probe should not run when an override is given")

        monkeypatch.setattr("hub.launchability.probe_mcp_registered", _boom)
        assert resolve_access_path("claude", "claude", override="mcp") == "mcp"
        assert resolve_access_path("claude", "claude", override="cli") == "cli"

    def test_unprobeable_runner_defaults_to_cli(self, monkeypatch):
        def _boom(cli):
            raise AssertionError("kimi is not in PROBEABLE_RUNNERS — must not probe")

        monkeypatch.setattr("hub.launchability.probe_mcp_registered", _boom)
        assert resolve_access_path("kimi", "kimi", override=None) == "cli"

    def test_auto_override_is_treated_as_unset_and_probes(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.probe_mcp_registered", lambda cli: True)
        assert resolve_access_path("claude", "claude", override="auto") == "mcp"

    def test_probeable_runner_uses_probe_result(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.probe_mcp_registered", lambda cli: True)
        assert resolve_access_path("codex", "codex", override=None) == "mcp"
        monkeypatch.setattr("hub.launchability.probe_mcp_registered", lambda cli: False)
        assert resolve_access_path("codex", "codex", override=None) == "cli"

    def test_probe_mcp_registered_false_when_cli_not_on_path(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: None)
        assert probe_mcp_registered("claude") is False

    def test_probe_mcp_registered_reads_mcp_list_output(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: "/usr/bin/claude")

        class _FakeResult:
            returncode = 0
            stdout = "agentweave: connected\nother-server: connected\n"

        seen_cmd = {}

        def _fake_run(cmd, **kwargs):
            seen_cmd["cmd"] = cmd
            return _FakeResult()

        monkeypatch.setattr("hub.launchability.subprocess.run", _fake_run)
        assert probe_mcp_registered("claude") is True
        assert seen_cmd["cmd"] == ["claude", "mcp", "list"]

    def test_probe_mcp_registered_false_when_not_in_list_output(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: "/usr/bin/claude")

        class _FakeResult:
            returncode = 0
            stdout = "some-other-server: connected\n"

        monkeypatch.setattr("hub.launchability.subprocess.run", lambda cmd, **kw: _FakeResult())
        assert probe_mcp_registered("claude") is False

    def test_probe_mcp_registered_swallows_subprocess_errors(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: "/usr/bin/claude")

        def _raise(cmd, **kwargs):
            raise OSError("boom")

        monkeypatch.setattr("hub.launchability.subprocess.run", _raise)
        assert probe_mcp_registered("claude") is False

    def test_access_path_notice_names_the_available_tools(self):
        assert "send_message" in access_path_notice("mcp")
        assert "agentweave msg send" in access_path_notice("cli")
        assert "not available" in access_path_notice("cli")


@pytest.mark.asyncio
async def test_get_agent_config_falls_back_to_session_wide_hub_client(app, auth_headers):
    """Task 4.3: a per-agent `hub_client` override wins; when absent, the session-wide
    default (session.json's top-level `hub_client`) applies — mirroring the CLI's
    Session.get_agent_hub_client fallback order."""
    from hub.db.engine import async_session_factory

    sync = await app.post(
        "/api/v1/session/sync",
        json={
            "data": {
                "hub_client": "cli",
                "agents": {
                    "session-default-agent": {"runner": "claude"},
                    "overridden-agent": {"runner": "claude", "hub_client": "mcp"},
                },
            }
        },
        headers=auth_headers,
    )
    assert sync.status_code == 200

    async with async_session_factory() as db:
        default_config = await get_agent_config("proj-test", "session-default-agent", db)
        override_config = await get_agent_config("proj-test", "overridden-agent", db)

    assert default_config["hub_client"] == "cli"
    assert override_config["hub_client"] == "mcp"
