"""Tests for the model catalog (2026-08-04-hub-model-control-and-provisioning)."""

from hub.db.models import RUNNER_CLIS
from hub.model_catalog import (
    CATALOG,
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

    def test_unknown_context_window_is_none_not_a_substitute(self):
        # Opus 5 and Fable 5 have no live-verified context window on this machine.
        assert model_context_window("claude", "claude-opus-5") is None
        assert model_context_window("claude", "claude-fable-5") is None
        # Sonnet 5 and Haiku 4.5 do — live-verified via Claude's own result event.
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
