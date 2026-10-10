"""Tests for the model catalog (2026-08-04-hub-model-control-and-provisioning)."""

from hub.db.models import RUNNER_CLIS
from hub.model_catalog import (
    CATALOG,
    get_provider,
    model_context_window,
    render_control_args,
    render_control_config,
    validate_overrides,
)


class TestCatalogCoverage:
    def test_every_declared_provider_matches_a_runner_cli(self):
        # The catalog's keys are exactly RUNNER_CLIS — a provider the Hub cannot bind a
        # Runner to must not appear in the catalog, and vice versa.
        assert set(CATALOG.keys()) == set(RUNNER_CLIS)

    def test_no_unspawnable_provider_is_declared(self):
        for provider in CATALOG:
            assert provider in ("claude", "codex", "copilot")

    def test_every_model_has_an_id_and_label(self):
        for entry in CATALOG.values():
            assert entry.models
            for model in entry.models:
                assert model.id
                assert model.label

    def test_every_declared_claude_model_has_a_context_window(self):
        """A window is only useful if it is there for every model an agent might run.

        Opus 5 and Fable 5 were `None`, so a Claude agent on either reported no context
        percentage even once the resolution path was correct — the catalog had nothing to
        resolve. Filled from Anthropic's published model reference (both 1M), which is a weaker
        source than the live `result`-event observation behind Sonnet 5 and Haiku 4.5 but a
        better one than leaving the field blank. `context_window_for_model` returns None for a
        model the catalog does not declare, so an unknown model still yields no percentage
        rather than a substituted guess — see `test_context_usage_measurement.py`.
        """
        assert model_context_window("claude", "claude-opus-5") == 1_000_000
        assert model_context_window("claude", "claude-fable-5") == 1_000_000
        # Live-verified 2026-09-23 via Claude's own result event.
        assert model_context_window("claude", "claude-opus-5-5") == 1_000_000
        assert model_context_window("claude", "claude-fable-5-1") == 1_000_000
        # Live-verified via Claude's own result event.
        assert model_context_window("claude", "claude-sonnet-5") == 1_000_000
        assert model_context_window("claude", "claude-haiku-4-5-20251001") == 200_000

    def test_sonnet_5_5_is_offered_and_owns_the_sonnet_alias_and_the_default(self):
        """F507/F575. Live-verified 2026-10-10 (CLI 2.1.291): `--model claude-sonnet-5-5` and
        `--model sonnet` both answered with `modelUsage["claude-sonnet-5-5"]`, window 1,000,000.
        `claude-sonnet-5` stays declared, as the previous generation runner records name."""
        claude = get_provider("claude")
        assert claude.model("claude-sonnet-5-5").label == "Sonnet 5.5"
        assert claude.model("sonnet").id == "claude-sonnet-5-5"
        assert [m.id for m in claude.models if m.default] == ["claude-sonnet-5-5"]
        assert model_context_window("claude", "claude-sonnet-5-5") == 1_000_000
        assert claude.model("claude-sonnet-5").id == "claude-sonnet-5"


class TestValidateOverrides:
    def test_a_value_valid_for_one_provider_is_refused_for_the_other(self):
        # "max" is a valid Claude effort value but not one Codex's catalog declares.
        accepted, rejection = validate_overrides("codex", {"effort": "max"})
        assert accepted == {}
        assert rejection is not None
        assert rejection.control == "effort"

    def test_a_value_valid_for_its_own_provider_is_accepted(self):
        accepted, rejection = validate_overrides("claude", {"effort": "max"})
        assert rejection is None
        assert accepted == {"effort": "max"}

    def test_an_undeclared_control_is_refused(self):
        accepted, rejection = validate_overrides("claude", {"verbosity": "high"})
        assert accepted == {}
        assert rejection is not None
        assert rejection.control == "verbosity"

    def test_an_unknown_provider_is_refused(self):
        accepted, rejection = validate_overrides("gemini", {"effort": "high"})
        assert accepted == {}
        assert rejection is not None

    def test_model_is_validated_against_the_provider_models_not_controls(self):
        accepted, rejection = validate_overrides("claude", {"model": "claude-opus-5"})
        assert rejection is None
        assert accepted == {"model": "claude-opus-5"}

    def test_a_model_not_in_the_provider_catalog_is_refused(self):
        accepted, rejection = validate_overrides("claude", {"model": "gpt-5.6-terra"})
        assert accepted == {}
        assert rejection is not None
        assert rejection.control == "model"

    def test_model_and_control_overrides_validate_together(self):
        accepted, rejection = validate_overrides(
            "codex", {"model": "gpt-5.6-terra", "effort": "high"}
        )
        assert rejection is None
        assert accepted == {"model": "gpt-5.6-terra", "effort": "high"}


class TestRenderControlArgs:
    def test_claude_effort_renders_as_a_flag(self):
        assert render_control_args("claude", {"effort": "high"}) == ["--effort", "high"]

    def test_codex_effort_renders_as_a_config_override(self):
        assert render_control_args("codex", {"effort": "high"}) == [
            "-c",
            "model_reasoning_effort=high",
        ]

    def test_an_empty_override_set_renders_nothing(self):
        assert render_control_args("claude", {}) == []

    def test_an_unknown_control_renders_nothing_render_never_rejects(self):
        # render_control_args trusts its caller validated first; an unknown control is
        # simply skipped rather than raising, since validate_overrides is the gate.
        assert render_control_args("claude", {"verbosity": "high"}) == []

    def test_model_key_is_skipped_not_rendered_as_a_control(self):
        # "model" has its own dedicated application path in build_command — a caller may
        # pass the full override dict (including "model") without stripping it first.
        assert render_control_args("claude", {"model": "claude-opus-5", "effort": "high"}) == [
            "--effort",
            "high",
        ]


class TestRenderControlConfig:
    """F99 — the same declarations, rendered as the `config` map app-server takes instead of
    the argv it does not read."""

    def test_codex_effort_renders_as_a_config_key(self):
        assert render_control_config("codex", {"effort": "high"}) == {
            "model_reasoning_effort": "high"
        }

    def test_a_flag_style_control_renders_nothing(self):
        # Claude's effort is a flag, not a config override — and Claude has no app-server
        # transport at all. Only `style="config"` belongs in this map.
        assert render_control_config("claude", {"effort": "high"}) == {}

    def test_codex_permission_mode_renders_nothing(self):
        # ApplySpec(style="none") — it reaches the runtime as a thread policy, not a config key.
        assert render_control_config("codex", {"permission_mode": "manual"}) == {}

    def test_model_and_unknown_controls_are_skipped(self):
        assert render_control_config("codex", {"model": "gpt-5.6-terra", "verbosity": "high"}) == {}

    def test_an_unknown_provider_renders_nothing(self):
        assert render_control_config("gemini", {"effort": "high"}) == {}


class TestProviderLookup:
    def test_get_provider_returns_none_for_an_unknown_provider(self):
        assert get_provider("gemini") is None

    def test_get_provider_returns_the_descriptor(self):
        entry = get_provider("codex")
        assert entry is not None
        assert entry.provider == "codex"


class TestCopilotCatalog:
    """`a-copilot-agent-runs-over-acp` design D13 (task 1.12)."""

    def test_copilot_is_declared_with_auto_as_its_default(self):
        entry = get_provider("copilot")
        assert entry is not None
        assert entry.label == "GitHub Copilot"
        assert entry.models[0].id == "auto"
        assert entry.models[0].label == "Auto"
        assert [m.id for m in entry.models if m.default] == ["auto"]

    def test_every_copilot_model_states_its_window_as_unknown(self):
        # Copilot reports the window per turn (`usage_update.size`, D11); the catalog never
        # borrows one.
        entry = get_provider("copilot")
        assert entry is not None
        assert len(entry.models) > 1
        assert all(m.context_window is None for m in entry.models)

    def test_copilot_lists_what_its_cli_printed(self):
        entry = get_provider("copilot")
        assert entry is not None
        ids = {m.id for m in entry.models}
        # A sample of `evidence/help-config.txt`'s `model` list (build 1.0.88).
        assert {"claude-haiku-4.5", "gpt-5.5", "mai-code-1.1-flash", "gemini-3.8-flash"} <= ids

    def test_copilot_permissions_match_codex_but_default_to_workspace(self):
        copilot = get_provider("copilot").control("permission_mode")
        codex = get_provider("codex").control("permission_mode")
        assert [(v.id, v.label) for v in copilot.values] == [(v.id, v.label) for v in codex.values]
        # D8: Copilot has no sandbox of its own to fall back on, so an unset posture is judged
        # as Workspace only, and the control says so.
        assert copilot.default == "workspace"
        assert copilot.apply.style == "none"

    def test_copilot_effort_renders_as_a_flag(self):
        assert render_control_args("copilot", {"effort": "high"}) == [
            "--reasoning-effort",
            "high",
        ]
        assert render_control_config("copilot", {"effort": "high"}) == {}

    def test_an_undeclared_copilot_model_is_refused(self):
        # `session/set_model` accepts anything and `--model` on Free is silently replaced, so the
        # Hub's own validation is the only backstop.
        accepted, rejection = validate_overrides("copilot", {"model": "bogus-model"})
        assert accepted == {}
        assert rejection is not None and rejection.control == "model"

    def test_auto_is_an_id_not_an_alias(self):
        entry = get_provider("copilot")
        assert entry is not None
        assert all(not m.aliases for m in entry.models)
        assert validate_overrides("copilot", {"model": "auto"}) == ({"model": "auto"}, None)
