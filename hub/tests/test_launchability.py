"""Tests for the per-agent launchability probe (Phase 3 task 3.2)."""

from unittest.mock import patch

import pytest

from hub.launchability import (
    RUNNER_UNBOUND,
    access_path_notice,
    auto_snapshot_notice,
    described_access_path,
    get_agent_config,
    probe_agent,
    resolve_agent_env,
)
from hub.runner_adapters import get_adapter, resolve_access_axes
from tests.test_agent_trigger import _await_background_run, _fake_pty


class TestProbeAgent:
    def test_an_unbound_agent_says_so_instead_of_naming_a_cli_after_itself(self, monkeypatch):
        """The masking measured on the trial Hub 2026-08-21, and the reason `native` is not enough.

        An agent with `runner_id IS NULL` used to reach the `LEGACY_RUNNER_CLI["native"] is None` fallback
        at the bottom of `probe_agent`, whose default CLI is **the agent's own name** — so the queue
        status read `Runner CLI 'probe-norunner' was not found in PATH.` and sent the operator
        looking for a binary that was never meant to exist. `inbound_queue.py`'s own comment records
        the same masking being fixed once for the *bound* case; this is the branch that fix missed.

        `which` is made to succeed for everything, so a fallthrough would report runnable rather
        than merely a different message — the assertion fails loudly instead of subtly.
        """
        monkeypatch.setattr("hub.runner_adapters.base.shutil.which", lambda cli: "/usr/bin/" + cli)
        result = probe_agent("probe-norunner", {"runner": RUNNER_UNBOUND})
        assert result["runnable"] is False
        assert result["cli"] is None
        assert "no runner is bound" in result["reason"].lower()
        # The agent's own name must not appear as a binary anyone should go looking for.
        assert "probe-norunner" not in result["reason"]

    def test_manual_runner_is_never_runnable(self):
        result = probe_agent("claude", {"runner": "manual"})
        assert result["runnable"] is False
        assert result["present"] is False
        assert "manual" in result["reason"].lower()

    def test_cli_present_and_no_auth_requirement_is_runnable(self, monkeypatch):
        monkeypatch.setattr("hub.runner_adapters.base.shutil.which", lambda cli: "/usr/bin/claude")
        result = probe_agent("claude", {"runner": "claude"})
        assert result["present"] is True
        assert result["authorized"] is True
        assert result["runnable"] is True
        assert result["reason"] is None
        assert result["cli"] == "claude"

    def test_cli_missing_from_path(self, monkeypatch):
        monkeypatch.setattr("hub.runner_adapters.base.shutil.which", lambda cli: None)
        result = probe_agent("kimi", {"runner": "kimi"})
        assert result["present"] is False
        assert result["runnable"] is False
        assert "not found in PATH" in result["reason"]

    def test_native_runner_falls_back_to_agent_name_as_cli(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            "hub.runner_adapters.base.shutil.which",
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

        monkeypatch.setattr("hub.runner_adapters.base.shutil.which", _boom)

        missing = tmp_path / "nonexistent-binary"
        result = probe_agent("claude", {"runner": "claude", "cli": str(missing)})
        assert result["present"] is False
        assert "not an executable file" in result["reason"]

    def test_claude_proxy_requires_base_url_and_api_key_var(self, monkeypatch):
        monkeypatch.setattr("hub.runner_adapters.base.shutil.which", lambda cli: "/usr/bin/claude")
        result = probe_agent("minimax", {"runner": "claude_proxy"})
        assert result["authorized"] is False
        assert "ANTHROPIC_BASE_URL" in result["reason"]

    def test_claude_proxy_requires_the_api_key_env_var_to_be_set(self, monkeypatch):
        monkeypatch.setattr("hub.runner_adapters.base.shutil.which", lambda cli: "/usr/bin/claude")
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
        monkeypatch.setattr("hub.runner_adapters.base.shutil.which", lambda cli: "/usr/bin/claude")
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


@pytest.mark.asyncio
async def test_launchability_endpoint_reports_configured_agents(app, auth_headers, monkeypatch):
    monkeypatch.setattr("hub.runner_adapters.base.shutil.which", lambda cli: None)

    sync_resp = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"claude": {"runner": "claude"}, "backup": {"runner": "manual"}}}},
        headers=auth_headers,
    )
    assert sync_resp.status_code == 200

    resp = await app.get("/api/v1/projects/proj-test/agents/launchability", headers=auth_headers)
    assert resp.status_code == 200
    agents = resp.json()["agents"]

    assert agents["claude"]["runnable"] is False
    assert agents["claude"]["present"] is False
    assert agents["backup"]["runnable"] is False
    assert agents["backup"]["reason"] == "Runner is set to manual — no CLI to launch automatically."


@pytest.mark.asyncio
async def test_launchability_lifecycle_filter_matches_the_roster(app, auth_headers, add_agent):
    """F181: the probe must apply the same lifecycle filter `list_agents` does, with the same
    "no `Agent` row counts as open" rule — see `get_agents_launchability`'s docstring. Covers
    4.3's four cases in one sequence: default omits archived, `?lifecycle=archived` returns it,
    `?lifecycle=all` returns both, and a name that exists only in session config (no `Agent` row
    at all) is excluded from the archived filter too.
    """
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"config-only": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    await add_agent("db-agent")
    archived = await app.post(
        "/api/v1/projects/proj-test/agents/db-agent/archive", headers=auth_headers
    )
    assert archived.status_code == 200

    default = await app.get("/api/v1/projects/proj-test/agents/launchability", headers=auth_headers)
    assert default.status_code == 200
    default_agents = default.json()["agents"]
    assert "db-agent" not in default_agents
    assert "config-only" in default_agents

    archived_only = await app.get(
        "/api/v1/projects/proj-test/agents/launchability?lifecycle=archived", headers=auth_headers
    )
    assert archived_only.status_code == 200
    archived_agents = archived_only.json()["agents"]
    assert "db-agent" in archived_agents
    # A name with no `Agent` row cannot have been archived -- it counts as open, so it must not
    # leak into the archived filter. This is the case the 4.3 mutation (filtering the `Agent`
    # query instead of the merged roster) gets wrong.
    assert "config-only" not in archived_agents

    everything = await app.get(
        "/api/v1/projects/proj-test/agents/launchability?lifecycle=all", headers=auth_headers
    )
    assert everything.status_code == 200
    all_agents = everything.json()["agents"]
    assert "db-agent" in all_agents
    assert "config-only" in all_agents


@pytest.mark.asyncio
async def test_every_agent_the_default_probe_calls_runnable_is_not_refused_as_archived(
    app, auth_headers, bind_runner
):
    """F181's actual violation: before the lifecycle filter existed, an archived agent's probe
    still reported `runnable: true`, and `POST /agent/trigger` then refused it with 409. Drives
    both endpoints as one sequence over every name the default probe reports runnable, rather
    than a single hand-picked agent, so a future agent added here is covered for free.
    """
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={
            "data": {
                "agents": {
                    "open-runnable": {"runner": "claude"},
                    "archived-runnable": {"runner": "claude"},
                }
            }
        },
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("open-runnable", cli="claude")
    await bind_runner("archived-runnable", cli="claude")

    archived = await app.post(
        "/api/v1/projects/proj-test/agents/archived-runnable/archive", headers=auth_headers
    )
    assert archived.status_code == 200

    with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
        probe = await app.get(
            "/api/v1/projects/proj-test/agents/launchability", headers=auth_headers
        )
    assert probe.status_code == 200
    probe_agents = probe.json()["agents"]
    assert "archived-runnable" not in probe_agents
    assert probe_agents["open-runnable"]["runnable"] is True

    runnable_names = [name for name, result in probe_agents.items() if result["runnable"]]
    assert runnable_names, "the sequence below is vacuous if nothing is runnable"

    fake_spawn = _fake_pty(
        [
            '{"type":"system","subtype":"init","session_id":"sess-f181"}\n',
            '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-f181"}\n',
        ]
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            for name in runnable_names:
                resp = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": name, "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert resp.status_code != 409, f"{name}: {resp.text}"
                assert "archived" not in resp.text.lower(), f"{name}: {resp.text}"
            await _await_background_run()


class TestCollaborationReadiness:
    """Task 6: collaboration_ready/collaboration_reason on the launchability probe —
    only meaningful for an agent the Hub can trigger directly (a bound Runner) and only
    once basic launchability already holds."""

    @pytest.fixture(autouse=True)
    def _reachable_hub(self, monkeypatch):
        monkeypatch.setattr("hub.bound_address.get", lambda: ("127.0.0.1", 8010))

    @pytest.fixture(autouse=True)
    def _cli_present(self, monkeypatch):
        monkeypatch.setattr("hub.runner_adapters.base.shutil.which", lambda cli: f"/usr/bin/{cli}")

    async def _probe(self, app, auth_headers, name):
        resp = await app.get(
            "/api/v1/projects/proj-test/agents/launchability", headers=auth_headers
        )
        assert resp.status_code == 200
        return resp.json()["agents"][name]

    @pytest.mark.asyncio
    async def test_claude_agent_bound_to_a_runner_is_collaboration_ready(
        self, app, auth_headers, bind_runner
    ):
        sync = await app.post(
            "/api/v1/projects/proj-test/session/sync",
            json={"data": {"agents": {"claude-collab": {}}}},
            headers=auth_headers,
        )
        assert sync.status_code == 200
        await bind_runner("claude-collab", cli="claude")

        result = await self._probe(app, auth_headers, "claude-collab")
        assert result["runnable"] is True
        assert result["collaboration_ready"] is True
        assert result["collaboration_reason"] is None

    @pytest.mark.asyncio
    async def test_default_codex_agent_is_collaboration_ready(self, app, auth_headers, bind_runner):
        """A codex agent created with no special configuration can collaborate.

        This is the whole point of making app-server the default: the Add-agent dialog sets
        no flags, so under the old opt-in every codex agent an operator could create landed on
        the exec transport and could not call a single AgentWeave tool.
        """
        sync = await app.post(
            "/api/v1/projects/proj-test/session/sync",
            json={"data": {"agents": {"codex-default": {"yolo": False}}}},
            headers=auth_headers,
        )
        assert sync.status_code == 200
        await bind_runner("codex-default", cli="codex")

        result = await self._probe(app, auth_headers, "codex-default")
        assert result["runnable"] is True
        assert result["collaboration_ready"] is True
        assert result["collaboration_reason"] is None

    @pytest.mark.asyncio
    async def test_non_yolo_codex_agent_opted_out_of_app_server_is_not_collaboration_ready(
        self, app, auth_headers
    ):
        sync = await app.post(
            "/api/v1/projects/proj-test/session/sync",
            json={"data": {"agents": {"codex-exec": {"yolo": False}}}},
            headers=auth_headers,
        )
        assert sync.status_code == 200
        created = await app.post(
            "/api/v1/projects/proj-test/runners",
            json={"name": "codex-exec-runner", "cli": "codex", "flags": ["--no-app-server"]},
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text
        bound = await app.patch(
            "/api/v1/projects/proj-test/agents/codex-exec",
            json={"runner_id": created.json()["id"]},
            headers=auth_headers,
        )
        assert bound.status_code == 200, bound.text

        result = await self._probe(app, auth_headers, "codex-exec")
        assert result["runnable"] is True
        assert result["collaboration_ready"] is False
        assert "silently denied" in result["collaboration_reason"]
        # The remedies as the app labels them: the runner's flag, and the Full access posture.
        # "yolo" is a legacy config key no screen shows (design D7 of
        # `a-runner-that-cannot-collaborate-says-so-where-it-is-bound`).
        assert "--no-app-server" in result["collaboration_reason"]
        assert "Full access" in result["collaboration_reason"]
        assert "yolo" not in result["collaboration_reason"]

    @pytest.mark.asyncio
    async def test_yolo_codex_agent_is_collaboration_ready(self, app, auth_headers, bind_runner):
        sync = await app.post(
            "/api/v1/projects/proj-test/session/sync",
            json={"data": {"agents": {"codex-yolo": {"yolo": True}}}},
            headers=auth_headers,
        )
        assert sync.status_code == 200
        await bind_runner("codex-yolo", cli="codex")

        result = await self._probe(app, auth_headers, "codex-yolo")
        assert result["collaboration_ready"] is True

    @pytest.mark.asyncio
    async def test_app_server_opted_in_codex_agent_is_collaboration_ready_without_yolo(
        self, app, auth_headers
    ):
        sync = await app.post(
            "/api/v1/projects/proj-test/session/sync",
            json={"data": {"agents": {"codex-appserver": {"yolo": False}}}},
            headers=auth_headers,
        )
        assert sync.status_code == 200
        created = await app.post(
            "/api/v1/projects/proj-test/runners",
            json={"name": "codex-appserver-runner", "cli": "codex", "flags": ["--app-server"]},
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text
        bound = await app.patch(
            "/api/v1/projects/proj-test/agents/codex-appserver",
            json={"runner_id": created.json()["id"]},
            headers=auth_headers,
        )
        assert bound.status_code == 200, bound.text

        result = await self._probe(app, auth_headers, "codex-appserver")
        assert result["collaboration_ready"] is True
        assert result["collaboration_reason"] is None

    @pytest.mark.asyncio
    async def test_unknown_callback_address_is_not_collaboration_ready(
        self, app, auth_headers, bind_runner, monkeypatch
    ):
        monkeypatch.setattr("hub.bound_address.get", lambda: None)
        monkeypatch.delenv("HUB_URL", raising=False)
        sync = await app.post(
            "/api/v1/projects/proj-test/session/sync",
            json={"data": {"agents": {"claude-no-address": {}}}},
            headers=auth_headers,
        )
        assert sync.status_code == 200
        await bind_runner("claude-no-address", cli="claude")

        result = await self._probe(app, auth_headers, "claude-no-address")
        assert result["runnable"] is True
        assert result["collaboration_ready"] is False
        assert "callback address" in result["collaboration_reason"]

    @pytest.mark.asyncio
    async def test_agent_with_no_bound_runner_has_no_collaboration_verdict(self, app, auth_headers):
        sync = await app.post(
            "/api/v1/projects/proj-test/session/sync",
            json={"data": {"agents": {"unbound-agent": {"runner": "claude"}}}},
            headers=auth_headers,
        )
        assert sync.status_code == 200

        result = await self._probe(app, auth_headers, "unbound-agent")
        # Legacy config still drives basic launchability for a non-Hub-managed agent...
        assert result["runnable"] is True
        # ...but collaboration readiness does not apply — the Hub cannot trigger it.
        assert result["collaboration_ready"] is None
        assert result["collaboration_reason"] is None

    @pytest.mark.asyncio
    async def test_not_runnable_agent_has_no_collaboration_verdict(
        self, app, auth_headers, bind_runner, monkeypatch
    ):
        monkeypatch.setattr("hub.runner_adapters.base.shutil.which", lambda cli: None)
        sync = await app.post(
            "/api/v1/projects/proj-test/session/sync",
            json={"data": {"agents": {"claude-missing-cli": {}}}},
            headers=auth_headers,
        )
        assert sync.status_code == 200
        await bind_runner("claude-missing-cli", cli="claude")

        result = await self._probe(app, auth_headers, "claude-missing-cli")
        assert result["runnable"] is False
        assert result["collaboration_ready"] is None


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
    """Two questions — `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing` §4.
    `resolve_access_axes` (`runner_adapters`) answers what the run is *given* (and so what its
    permission posture is, via `.plane` and `.tool_surface`) — `launchability.resolve_access_path`
    used to answer the first half, and was deleted once every live runner had become
    unconditionally injectable (`each-runner-cli-is-one-adapter` task 3.2); `described_access_path`
    answers what the run is *told*, and refuses to assert a tool surface the Hub has no grounds to
    believe the harness will honour.

    This class used to be introduced by a docstring saying the path "is probed per runner rather
    than assumed". Nothing was probed; the probe had had no caller since `d279d22`, and two of the
    tests below guarded a call that could not happen for any input (`design.md` D10).
    """

    def test_an_explicit_cli_statement_is_what_the_run_is_given(self):
        """The operator's declaration is the only thing that moves the injected server — and it
        moves it in the direction that removes the unanswerable approver flag, not only the
        wording. A run given no server is told the call command (`a-run-reaches-the-hub-without-
        mcp` D1), never the `cli`/HTTP form."""
        axes = resolve_access_axes(get_adapter("claude"), hub_client="cli", flags=[])
        assert axes.plane == "cli"
        assert axes.tool_surface == "none"
        assert described_access_path("cli", override="cli") == "shim"

    def test_an_explicit_mcp_statement_is_grounds_on_its_own(self):
        """Nothing has been tested about this harness, and the operator has still settled it.

        The distinguishing half: with the same absent test and no statement, the run is told the
        call command. Delete the `override == "mcp"` branch and this test fails while the one
        below it passes.
        """
        assert described_access_path("mcp", override="mcp", latest=None) == "mcp"
        assert described_access_path("mcp", override=None, latest=None) == "shim"

    def test_auto_is_treated_as_unset_and_therefore_as_no_statement(self):
        """`auto` is the CLI's default value for `hub_client`, and it means the operator has said
        nothing. It must not read as an assertion that MCP is there: injected, yes — described,
        only on grounds."""
        axes = resolve_access_axes(get_adapter("claude"), hub_client="auto", flags=[])
        assert axes.plane == "mcp"
        assert described_access_path("mcp", override="auto", latest=None) == "shim"
        assert described_access_path("mcp", override="auto", latest="connected") == "mcp"

    def test_injectable_runner_needs_no_global_registration(self):
        """The Hub injects its server for any injectable runner without asking whether the
        operator registered one by hand; that injection still does not assert the tools are there
        (D10: no grounds, the call command)."""
        axes = resolve_access_axes(get_adapter("codex"), hub_client=None, flags=[])
        assert axes.plane == "mcp"
        assert described_access_path("mcp", override=None, latest=None) == "shim"

    def test_a_run_given_no_server_is_never_described_as_having_one(self):
        """Grounds cannot manufacture a surface that was not injected. A harness that connected on
        an earlier run says nothing about a run the operator has moved to `cli`."""
        assert described_access_path("cli", override=None, latest="connected") == "shim"
        assert described_access_path("cli", override="mcp", latest="connected") == "shim"

    def test_the_latest_test_decides_what_the_run_is_told(self):
        """F340: only a latest test of `connected` grounds the MCP form. `absent`, `failed`, an
        unrecognised string and no test at all are no grounds."""
        assert described_access_path("mcp", override=None, latest="connected") == "mcp"
        for latest in ("absent", "failed", "weird", None):
            assert described_access_path("mcp", override=None, latest=latest) == "shim", latest

    def test_a_run_is_never_described_as_cli_or_http(self):
        for plane in ("mcp", "cli"):
            for override in (None, "mcp", "cli", "auto"):
                for latest in (None, "connected", "absent", "failed"):
                    told = described_access_path(plane, override=override, latest=latest)
                    assert told in ("mcp", "shim"), (plane, override, latest, told)

    def test_the_probe_is_gone_and_stays_gone(self):
        """`probe_mcp_registered` shelled `<cli> mcp list` in a separate process with no
        `--mcp-config`, so it could only see servers registered by hand — never the one the Hub
        injects on the turn's own command line. A `False` from it resolved the path to `cli`,
        suppressing the injection it had been asked about (`design.md` D10). Three test files were
        written believing it still ran. This asserts it cannot come back unnoticed."""
        import hub.launchability as launchability

        assert not hasattr(launchability, "probe_mcp_registered")
        assert not hasattr(launchability, "_probe_cache")

    def test_the_permanent_grounds_are_gone(self):
        """F340: "any run ever announced" was positive-only and never revoked. It is replaced by
        `latest_mcp_test`, and must not come back beside it."""
        import hub.launchability as launchability

        assert not hasattr(launchability, "harness_has_honoured_mcp")


class TestAccessPathNotice:
    def test_access_path_notice_names_the_available_tools(self):
        assert "send_message" in access_path_notice("mcp")

    def test_access_path_notice_offers_no_removed_cli_commands(self):
        """The fallback used to instruct `agentweave msg send`, `task create`, `question ask`
        and `agent request`; 2026-08-03-single-runtime left five app-lifecycle commands, so all
        of those were wrong. Naming none of them is still right."""
        notice = access_path_notice("shim")
        for removed in ("agentweave msg", "agentweave task", "agentweave question"):
            assert removed not in notice

    def test_a_run_without_mcp_is_told_the_call_command(self):
        """`a-run-reaches-the-hub-without-mcp` D11: the raw HTTP form is no longer described to
        runs, because following it puts the credential into stored command text. The run is told
        the call command and where its arguments file goes, and nothing about the credential."""
        notice = access_path_notice("shim")
        assert "aw-tool" in notice
        assert ".agentweave/calls/" in notice
        assert "-Encoding utf8" in notice  # review fix 3: PowerShell 5.1's bare Set-Content
        assert "last line" in notice  # review note 9: the envelope is the last line
        # F477 (drive 9.4): the shape the approver gives standing to, said in so many words.
        assert "with your file-writing tool" in notice
        assert "on its own" in notice and "unquoted" in notice
        for absent in ("AW_RUN_TOKEN", "Bearer", "$HUB_URL", "/api/v1/agent-actions"):
            assert absent not in notice, absent
        assert "no AgentWeave tool surface is available" not in notice

    def test_a_run_without_mcp_is_not_told_it_cannot_act(self):
        """The delta's first scenario has two halves, and this is the second: the notice must
        not go on stating the denial in other words. An agent that is authenticated and told it
        is not will not try."""
        notice = access_path_notice("shim").lower()
        for denial in (
            "no agentweave tool surface",
            "cannot send messages",
            "report what you would have sent",
            "no mcp tools this turn",
        ):
            assert denial not in notice

    def test_the_notice_carries_no_credential_or_address_value(self, monkeypatch):
        """Rendered with the real variables set to sentinels: neither value appears in either
        form. Rendering with them unset would pass against an interpolating implementation."""
        monkeypatch.setenv("AW_RUN_TOKEN", "aw-run-tok-SENTINEL-2f4b9c")
        monkeypatch.setenv("HUB_URL", "http://127.0.0.1:65432")
        for told in ("mcp", "shim"):
            notice = access_path_notice(told)
            assert "aw-run-tok-SENTINEL-2f4b9c" not in notice
            assert "65432" not in notice

    def test_the_notice_takes_exactly_mcp_or_shim(self):
        """D11 (R2): a caller still passing `cli` fails loudly instead of rendering the form this
        change stops telling runs."""
        for value in ("cli", "http", ""):
            with pytest.raises(ValueError):
                access_path_notice(value)

    def test_a_shell_that_may_lack_network_is_told_so(self):
        """D10 / review fix 6: keyed on the adapter's `shell_may_lack_network`, true for Codex,
        whose sandboxed shell may not reach the Hub; no other runner's notice carries it."""
        from hub.runner_adapters import ADAPTERS

        sentence = "If `aw-tool` reports `unreachable`, say so in your reply rather than retrying."
        assert sentence not in access_path_notice("shim")
        assert sentence in access_path_notice("shim", shell_may_lack_network=True)
        assert sentence not in access_path_notice("mcp", shell_may_lack_network=True)
        assert [name for name, a in ADAPTERS.items() if a.shell_may_lack_network] == ["codex"]

    def test_f52_auto_snapshot_notice_says_the_agent_need_not_commit(self):
        """F52 (`scripts/drive/FINDINGS.md`, 2026-08-26): two live runs each spent most of a
        turn fighting a refused git commit, one giving up on the task entirely, because the
        agent believed unrecorded work was lost. It was not — `snapshot_worktree` commits
        automatically at every turn's end. The notice must say so and must not tell the agent
        to keep trying git."""
        notice = auto_snapshot_notice()
        assert "do not need to" in notice.lower()
        assert "commit" in notice.lower()
        assert "record_evidence" in notice


@pytest.mark.asyncio
async def test_get_agent_config_falls_back_to_session_wide_hub_client(app, auth_headers):
    """Task 4.3: a per-agent `hub_client` override wins; when absent, the session-wide
    default (session.json's top-level `hub_client`) applies — mirroring the CLI's
    Session.get_agent_hub_client fallback order."""
    from hub.db.engine import async_session_factory

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
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


@pytest.mark.asyncio
async def test_get_agent_config_reports_the_bound_runner_and_names_the_unbound_case(
    app, auth_headers, bind_runner
):
    """The bound `Runner` is the third source, and it outranks session.json.

    It used to be neither — `get_agent_config` read only session.json and `Agent.config`, and two
    call sites (`api/v1/agents.py`, `api/v1/inbound_queue.py`) pasted byte-identical blocks to
    compensate. Both covered the bound case; neither covered the unbound one, which is why an agent
    with `runner_id IS NULL` was reported as a missing CLI named after itself (measured on the
    trial Hub, 2026-08-21).

    Session.json deliberately says `kimi` here while the bound runner says `claude`: the bound
    runner is what `agent_trigger` will actually launch, so it must win, and asserting on the
    disagreement is what proves precedence rather than coincidence.
    """
    from hub.db.engine import async_session_factory

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"bound-agent": {"runner": "kimi"}, "unbound-agent": {}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("bound-agent", cli="claude")
    await bind_runner("unbound-agent", cli="claude")

    # Unbind the second one. This is the only route to the state -- creation refuses it
    # ("Provide either runner_id or both provider and model"), which is why the invariant held
    # everywhere except here.
    patched = await app.patch(
        "/api/v1/projects/proj-test/agents/unbound-agent",
        json={"runner_id": None},
        headers=auth_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["runner_id"] is None

    async with async_session_factory() as db:
        bound = await get_agent_config("proj-test", "bound-agent", db)
        unbound = await get_agent_config("proj-test", "unbound-agent", db)

    assert bound["runner"] == "claude"
    assert unbound["runner"] == RUNNER_UNBOUND

    # And the verdict the operator actually reads.
    assert probe_agent("unbound-agent", unbound)["runnable"] is False
    assert "no runner is bound" in probe_agent("unbound-agent", unbound)["reason"].lower()


def test_spec_turn_notice_neutralises_a_path_with_an_at_sign() -> None:
    """F409 D9: the path comes from the operator's subject and is composed into the turn prompt."""
    from hub.file_mentions import MENTION_NOTICE
    from hub.launchability import spec_turn_notice

    notice = spec_turn_notice("exploring", path="spec/a @x/y.html", is_unwritten=True)
    assert notice.count(r"spec/a \@x/y.html") == 2
    assert notice.replace(r"\@", "").count("@") == 0
    assert notice.endswith(MENTION_NOTICE)


def test_spec_turn_notice_is_unchanged_for_a_path_without_an_at_sign() -> None:
    from hub.file_mentions import MENTION_NOTICE
    from hub.launchability import spec_turn_notice

    notice = spec_turn_notice("exploring", path="spec/pale-otter.json", is_unwritten=True)
    assert MENTION_NOTICE not in notice
    assert "`spec/pale-otter.json`" in notice and "path='spec/pale-otter.json'" in notice


# ---------------------------------------------------------------------------------------------
# Copilot launchability is read from Copilot itself (`a-copilot-agent-runs-over-acp` task 1.15,
# design D15). The env-token branch these replace was wrong both ways: the operator's login lives
# in the Windows Credential Manager, and an ambient token silently overrides it.
# ---------------------------------------------------------------------------------------------


class TestCopilotProbeVerdict:
    @pytest.fixture(autouse=True)
    def _probe(self, tmp_path, monkeypatch):
        from hub import copilot_probe

        exe = tmp_path / "copilot.exe"
        exe.write_bytes(b"MZ")
        monkeypatch.setattr(copilot_probe.shutil, "which", lambda name: str(exe))
        for var in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        copilot_probe.CopilotProbe.reset()
        monkeypatch.setattr(copilot_probe.CopilotProbe, "refresh_enabled", True)
        self.scheduled = []
        monkeypatch.setattr(
            copilot_probe.CopilotProbe,
            "_schedule",
            classmethod(lambda cls, key, path: self.scheduled.append(key)),
        )
        self.exe = exe
        yield copilot_probe
        copilot_probe.CopilotProbe.reset()

    def _cache(self, copilot_probe, **fields):
        import time

        key = copilot_probe._key(self.exe.resolve())
        fields.setdefault("computed_at", time.monotonic())
        copilot_probe.CopilotProbe._verdicts[key] = copilot_probe._Verdict(**fields)
        return key

    def test_signed_in_needs_no_token(self, _probe):
        self._cache(_probe, present=True, authorized=True, reason=None, version="1.0.88")
        result = probe_agent("cop-1", {"runner": "copilot"})
        assert result["runnable"] is True
        assert result["reason"] is None
        assert result["cli"] == str(self.exe.resolve())
        assert "GitHub auth token" not in str(result)

    def test_not_signed_in_names_copilot_login(self, _probe):
        self._cache(_probe, present=True, authorized=False, reason=_probe.not_signed_in_reason())
        result = probe_agent("cop-1", {"runner": "copilot"})
        assert result["authorized"] is False and result["runnable"] is False
        assert "copilot login" in result["reason"]

    def test_too_old_names_the_version(self, _probe):
        self._cache(
            _probe,
            present=True,
            authorized=False,
            reason=_probe.too_old_reason("1.0.75"),
            version="1.0.75",
        )
        result = probe_agent("cop-1", {"runner": "copilot"})
        assert result["runnable"] is False
        assert "1.0.75" in result["reason"] and "1.0.81" in result["reason"]

    def test_pending_is_runnable_and_says_so(self, _probe):
        result = probe_agent("cop-1", {"runner": "copilot"})
        assert result["runnable"] is True
        assert result["verdict_pending"] is True
        assert len(self.scheduled) == 1

    def test_a_negative_verdict_is_always_stale(self, _probe, monkeypatch):
        """Finding 11: `copilot login` changes neither the path nor the mtime, so a negative
        verdict younger than the TTL is returned and a refresh is scheduled."""
        self._cache(_probe, present=True, authorized=False, reason=_probe.not_signed_in_reason())
        result = probe_agent("cop-1", {"runner": "copilot"})
        assert result["runnable"] is False
        assert len(self.scheduled) == 1

    def test_a_fresh_positive_verdict_schedules_nothing(self, _probe):
        self._cache(_probe, present=True, authorized=True, reason=None)
        probe_agent("cop-1", {"runner": "copilot"})
        assert self.scheduled == []

    def test_an_unresolvable_cli_is_not_present(self, _probe, monkeypatch):
        monkeypatch.setattr(_probe.shutil, "which", lambda name: None)
        result = probe_agent("cop-1", {"runner": "copilot"})
        assert result["present"] is False and result["runnable"] is False
        assert "was not found" in result["reason"]


class TestCopilotProbeRefresh:
    """The refresh itself, against a fake process: debounce, and failures that gate nothing."""

    @pytest.fixture(autouse=True)
    def _probe(self, tmp_path, monkeypatch):
        from hub import copilot_probe

        exe = tmp_path / "copilot.exe"
        exe.write_bytes(b"MZ")
        monkeypatch.setattr(copilot_probe.shutil, "which", lambda name: str(exe))
        copilot_probe.CopilotProbe.reset()
        monkeypatch.setattr(copilot_probe.CopilotProbe, "refresh_enabled", True)
        self.exe = exe
        yield copilot_probe
        copilot_probe.CopilotProbe.reset()

    @pytest.mark.asyncio
    async def test_a_second_read_within_five_seconds_schedules_no_refresh(
        self, _probe, monkeypatch
    ):
        import asyncio

        calls = []

        async def _fake_probe(path):
            calls.append(path)
            return _probe._Verdict(True, False, _probe.not_signed_in_reason())

        monkeypatch.setattr(_probe, "probe_copilot", _fake_probe)
        probe_agent("cop-1", {"runner": "copilot"})
        await asyncio.sleep(0)
        await asyncio.gather(*list(_probe.CopilotProbe._tasks))
        first = probe_agent("cop-1", {"runner": "copilot"})
        assert first["runnable"] is False  # the refreshed negative verdict
        await asyncio.sleep(0)
        assert len(calls) == 1  # the negative verdict is stale, but a refresh just finished

    @pytest.mark.asyncio
    async def test_an_unclassified_failure_leaves_the_verdict_and_adds_probe_error(
        self, _probe, monkeypatch
    ):
        import asyncio
        import time

        key = _probe._key(self.exe.resolve())
        _probe.CopilotProbe._verdicts[key] = _probe._Verdict(
            True, True, None, computed_at=time.monotonic() - _probe.POSITIVE_TTL_SECONDS - 1
        )

        async def _boom(path):
            raise TimeoutError("probe timed out")

        monkeypatch.setattr(_probe, "probe_copilot", _boom)
        probe_agent("cop-1", {"runner": "copilot"})
        await asyncio.gather(*list(_probe.CopilotProbe._tasks))
        result = probe_agent("cop-1", {"runner": "copilot"})
        assert result["runnable"] is True
        assert result["reason"] is None
        assert result["probe_error"] == "probe timed out"

    def test_the_probe_argv_disables_builtin_mcps(self, _probe):
        argv = _probe.probe_argv(self.exe)
        assert argv[0] == str(self.exe)
        assert "--disable-builtin-mcps" in argv
        assert "--acp" in argv and "--no-auto-update" in argv

    def test_record_writes_the_turns_verdict(self, _probe):
        _probe.CopilotProbe.record(
            present=True, authorized=False, reason=_probe.not_signed_in_reason()
        )
        result = probe_agent("cop-1", {"runner": "copilot"})
        assert result["runnable"] is False and "copilot login" in result["reason"]
