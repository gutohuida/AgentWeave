"""Tests for the per-agent launchability probe (Phase 3 task 3.2)."""

import pytest

from hub.launchability import (
    RUNNER_UNBOUND,
    access_path_notice,
    auto_snapshot_notice,
    described_access_path,
    get_agent_config,
    probe_agent,
    resolve_access_path,
    resolve_agent_env,
)


class TestProbeAgent:
    def test_an_unbound_agent_says_so_instead_of_naming_a_cli_after_itself(self, monkeypatch):
        """The masking measured on the trial Hub 2026-08-21, and the reason `native` is not enough.

        An agent with `runner_id IS NULL` used to reach the `RUNNER_CLI["native"] is None` fallback
        at the bottom of `probe_agent`, whose default CLI is **the agent's own name** — so the queue
        status read `Runner CLI 'probe-norunner' was not found in PATH.` and sent the operator
        looking for a binary that was never meant to exist. `inbound_queue.py`'s own comment records
        the same masking being fixed once for the *bound* case; this is the branch that fix missed.

        `which` is made to succeed for everything, so a fallthrough would report runnable rather
        than merely a different message — the assertion fails loudly instead of subtly.
        """
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: "/usr/bin/" + cli)
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


class TestCollaborationReadiness:
    """Task 6: collaboration_ready/collaboration_reason on the launchability probe —
    only meaningful for an agent the Hub can trigger directly (a bound Runner) and only
    once basic launchability already holds."""

    @pytest.fixture(autouse=True)
    def _reachable_hub(self, monkeypatch):
        monkeypatch.setattr("hub.bound_address.get", lambda: ("127.0.0.1", 8010))

    @pytest.fixture(autouse=True)
    def _cli_present(self, monkeypatch):
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: f"/usr/bin/{cli}")

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
        monkeypatch.setattr("hub.launchability.shutil.which", lambda cli: None)
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
    """Two questions, two functions — `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`
    §4. `resolve_access_path` answers what the run is *given* (and so what its permission posture
    is); `described_access_path` answers what the run is *told*, and refuses to assert a tool
    surface the Hub has no grounds to believe the harness will honour.

    This class used to be introduced by a docstring saying the path "is probed per runner rather
    than assumed". Nothing was probed; the probe had had no caller since `d279d22`, and two of the
    tests below guarded a call that could not happen for any input (`design.md` D10).
    """

    def test_an_explicit_cli_statement_is_what_the_run_is_given(self):
        """The operator's declaration is the only thing that moves the injected server — and it
        moves it in the direction that removes the unanswerable approver flag, not only the
        wording."""
        assert resolve_access_path("claude", override="cli") == "cli"
        assert described_access_path("cli", override="cli") == "cli"

    def test_an_explicit_mcp_statement_is_grounds_on_its_own(self):
        """Nothing has been observed about this harness, and the operator has still settled it.

        The distinguishing half: with the same absent observation and no statement, the run is
        told the HTTP form. Delete the `override == "mcp"` branch and this test fails while the
        one below it passes.
        """
        assert described_access_path("mcp", override="mcp", harness_honoured_mcp=False) == "mcp"
        assert described_access_path("mcp", override=None, harness_honoured_mcp=False) == "cli"

    def test_unprobeable_runner_defaults_to_cli(self):
        assert resolve_access_path("kimi", override=None) == "cli"

    def test_auto_is_treated_as_unset_and_therefore_as_no_statement(self):
        """`auto` is the CLI's default value for `hub_client`, and it means the operator has said
        nothing. It must not read as an assertion that MCP is there: injected, yes — described,
        only on grounds."""
        assert resolve_access_path("claude", override="auto") == "mcp"
        assert described_access_path("mcp", override="auto", harness_honoured_mcp=False) == "cli"
        assert described_access_path("mcp", override="auto", harness_honoured_mcp=True) == "mcp"

    def test_injectable_runner_needs_no_global_registration(self):
        """Kept from before §4, and updated deliberately rather than by accident.

        It pins the post-`d279d22` behaviour: the Hub injects its server for any injectable runner
        without asking whether the operator registered one by hand. That is still true and is now
        the *only* thing this function decides — the second assertion is what §4 added, and it is
        the one that stops the same value from also asserting the tools are there.
        """
        assert resolve_access_path("codex", override=None) == "mcp"
        assert described_access_path("mcp", override=None, harness_honoured_mcp=False) == "cli"

    def test_a_run_given_no_server_is_never_described_as_having_one(self):
        """Grounds cannot manufacture a surface that was not injected. A harness that honoured MCP
        on an earlier run says nothing about a run the operator has moved to `cli`."""
        assert described_access_path("cli", override=None, harness_honoured_mcp=True) == "cli"

    def test_an_observed_harness_is_described_as_having_the_tools(self):
        assert described_access_path("mcp", override=None, harness_honoured_mcp=True) == "mcp"

    def test_the_probe_is_gone_and_stays_gone(self):
        """`probe_mcp_registered` shelled `<cli> mcp list` in a separate process with no
        `--mcp-config`, so it could only see servers registered by hand — never the one the Hub
        injects on the turn's own command line. A `False` from it resolved the path to `cli`,
        suppressing the injection it had been asked about (`design.md` D10). Three test files were
        written believing it still ran. This asserts it cannot come back unnoticed."""
        import hub.launchability as launchability

        assert not hasattr(launchability, "probe_mcp_registered")
        assert not hasattr(launchability, "_probe_cache")


class TestAccessPathNotice:
    def test_access_path_notice_names_the_available_tools(self):
        assert "send_message" in access_path_notice("mcp")

    def test_access_path_notice_offers_no_removed_cli_commands(self):
        """The fallback used to instruct `agentweave msg send`, `task create`, `question ask`
        and `agent request`; 2026-08-03-single-runtime left five app-lifecycle commands, so all
        of those were wrong. Naming none of them is still right — what changed in
        `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing` is the conclusion that was
        drawn from it, which used to be a flat denial of capability."""
        notice = access_path_notice("cli")
        for removed in ("agentweave msg", "agentweave task", "agentweave question"):
            assert removed not in notice

    def test_a_run_without_mcp_is_told_the_plane_is_reachable_over_http(self):
        """Task 1.1: the four things the notice owes a run that cannot use MCP. This assertion
        replaces one that required the words "no AgentWeave tool surface is available" — a green
        test pinning the false sentence this change exists to remove."""
        notice = access_path_notice("cli")
        assert "HUB_URL" in notice
        assert "AW_RUN_TOKEN" in notice
        assert "Authorization: Bearer" in notice
        assert "/api/v1/agent-actions" in notice
        assert "no AgentWeave tool surface is available" not in notice

    def test_a_run_without_mcp_is_not_told_it_cannot_act(self):
        """The delta's first scenario has two halves, and this is the second: the notice must
        not go on stating the denial in other words. An agent that is authenticated and told it
        is not will not try."""
        notice = access_path_notice("cli").lower()
        for denial in (
            "no agentweave tool surface",
            "cannot send messages",
            "report what you would have sent",
        ):
            assert denial not in notice

    def test_the_notice_names_the_credential_variable_and_never_its_value(self, monkeypatch):
        """Delta scenario "The credential is named and not disclosed", and design D4.

        The notice is prepended to the turn prompt, which is the durable record of the turn, so
        an interpolated credential is a credential in stored text. The distance between correct
        and a leak is one f-string, so the test renders with the real environment variables set
        to known sentinels and asserts neither value appears. Rendering with the variables
        *unset* would pass against an interpolating implementation."""
        monkeypatch.setenv("AW_RUN_TOKEN", "aw-run-tok-SENTINEL-2f4b9c")
        monkeypatch.setenv("HUB_URL", "http://127.0.0.1:65432")
        notice = access_path_notice("cli")
        assert "AW_RUN_TOKEN" in notice
        assert "aw-run-tok-SENTINEL-2f4b9c" not in notice
        assert "HUB_URL" in notice
        assert "65432" not in notice

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
