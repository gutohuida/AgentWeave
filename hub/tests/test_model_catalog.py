"""Tests for the model catalog (2026-08-04-hub-model-control-and-provisioning)."""

from hub.db.models import RUNNER_CLIS
from hub.model_catalog import (
    CATALOG,
    context_window_for_model,
    get_provider,
    model_context_window,
    render_control_args,
    validate_overrides,
)
from hub.runner_commands import SUPPORTED_RUNNERS


class TestCatalogCoverage:
    def test_every_declared_provider_is_spawnable(self):
        for provider in CATALOG:
            assert provider in SUPPORTED_RUNNERS

    def test_every_declared_provider_matches_a_runner_cli(self):
        # The catalog's keys are exactly RUNNER_CLIS — a provider the Hub cannot bind a
        # Runner to must not appear in the catalog, and vice versa.
        assert set(CATALOG.keys()) == set(RUNNER_CLIS)

    def test_no_unspawnable_provider_is_declared(self):
        for provider in CATALOG:
            assert provider in ("claude", "codex")

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
        # Live-verified via Claude's own result event.
        assert model_context_window("claude", "claude-sonnet-5") == 1_000_000
        assert model_context_window("claude", "claude-haiku-4-5-20251001") == 200_000


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
        accepted, rejection = validate_overrides("claude", {"model": "gpt-5.6-sol"})
        assert accepted == {}
        assert rejection is not None
        assert rejection.control == "model"

    def test_model_and_control_overrides_validate_together(self):
        accepted, rejection = validate_overrides(
            "codex", {"model": "gpt-5.6-sol", "effort": "high"}
        )
        assert rejection is None
        assert accepted == {"model": "gpt-5.6-sol", "effort": "high"}


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


class TestProviderLookup:
    def test_get_provider_returns_none_for_an_unknown_provider(self):
        assert get_provider("gemini") is None

    def test_get_provider_returns_the_descriptor(self):
        entry = get_provider("codex")
        assert entry is not None
        assert entry.provider == "codex"


class TestWindowVariants:
    """A model may offer more than one context window (2026-08-09-model-context-window-variants).

    Live-verified 2026-08-09 against this machine's `claude` CLI, reading each run's own
    `result.modelUsage.<model>.contextWindow`: Haiku 4.5 is 200,000 at its base id and declares a
    1,000,000 variant at `[1m]`. `[bogus]` and `[200k]` are both refused by the provider, so the
    suffix is parsed rather than ignored.
    """

    BASE = "claude-haiku-4-5-20251001"
    LONG = "claude-haiku-4-5-20251001[1m]"

    def test_a_variant_resolves_to_its_own_window_not_its_base_models(self):
        # The whole point of having selected it.
        assert model_context_window("claude", self.BASE) == 200_000
        assert model_context_window("claude", self.LONG) == 1_000_000

    def test_the_variant_pass_beats_the_prefix_fallback(self):
        """The defect this ordering exists to prevent.

        `claude-haiku-4-5-20251001[1m]` starts with `claude-haiku-4-5-20251001`, so the
        longest-declared-prefix rule would answer 200,000 for the model chosen *because* it holds
        1,000,000 — reporting a conversation as five times fuller than it is, and checkpointing
        it on that.
        """
        assert context_window_for_model(self.LONG) == 1_000_000
        assert context_window_for_model(self.BASE) == 200_000

    def test_a_variant_id_is_a_model_id(self):
        entry = get_provider("claude")
        assert entry is not None
        assert entry.model(self.LONG) is entry.model(self.BASE)

    def test_a_variant_is_accepted_as_a_model_override(self):
        accepted, rejection = validate_overrides("claude", {"model": self.LONG})
        assert rejection is None
        assert accepted == {"model": self.LONG}

    def test_an_undeclared_variant_is_still_refused(self):
        # `[200k]` does not exist — the provider refuses it, and so does the Hub, before spawning.
        _, rejection = validate_overrides("claude", {"model": f"{self.BASE}[200k]"})
        assert rejection is not None
        assert rejection.control == "model"

    def test_a_selected_window_is_carried_to_the_provider_unaltered(self):
        # "model" is applied by build_command's own path, so it must survive control rendering
        # untouched rather than being rewritten to the base id.
        assert render_control_args("claude", {"model": self.LONG}) == []
        accepted, _ = validate_overrides("claude", {"model": self.LONG})
        assert accepted["model"] == self.LONG

    def test_models_with_one_window_declare_no_variants(self):
        """Opus 5, Sonnet 5 and Fable 5 accept `[1m]` but return the same 1,000,000 their base ids
        already give on this subscription. Declaring two choices producing one outcome would put a
        control on screen that changes nothing."""
        entry = get_provider("claude")
        assert entry is not None
        for model_id in ("claude-opus-5", "claude-sonnet-5", "claude-fable-5"):
            model = entry.model(model_id)
            assert model is not None
            assert model.windows == ()

    def test_a_declared_window_matches_the_model_it_belongs_to(self):
        """A variant's default must agree with the model's own declared window, or the two would
        describe the same spawn differently."""
        for entry in CATALOG.values():
            for model in entry.models:
                if not model.windows:
                    continue
                default = next((w for w in model.windows if w.default), None)
                assert default is not None, f"{model.id} declares windows but no default"
                assert default.id == model.id
                assert default.context_window == model.context_window
