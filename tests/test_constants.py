"""Tests for constants module."""

from agentweave.constants import (
    AGENT_RUNNER_DEFAULTS,
    KNOWN_AGENTS,
    RUNNER_CONFIGS,
    RUNNER_TYPES,
)


class TestOpencodeConstants:
    """Tests that opencode is properly registered in constants."""

    def test_opencode_in_runner_types(self):
        """opencode must be in RUNNER_TYPES."""
        assert "opencode" in RUNNER_TYPES

    def test_opencode_in_runner_configs(self):
        """opencode must have a complete RUNNER_CONFIGS entry."""
        assert "opencode" in RUNNER_CONFIGS
        cfg = RUNNER_CONFIGS["opencode"]
        assert cfg["cli"] == "opencode"
        assert cfg["subcommand"] == "run"
        assert cfg["session_flag"] == "--session"
        assert cfg["output_format"] == "json"
        assert cfg["context_flag"] == "--file"
        assert cfg["model_flag"] == "--model"
        assert cfg["mcp_add_cmd"] is None

    def test_opencode_in_agent_runner_defaults(self):
        """opencode must be in AGENT_RUNNER_DEFAULTS."""
        assert "opencode" in AGENT_RUNNER_DEFAULTS
        assert AGENT_RUNNER_DEFAULTS["opencode"] == "opencode"

    def test_opencode_in_known_agents(self):
        """opencode must be in KNOWN_AGENTS."""
        assert "opencode" in KNOWN_AGENTS


class TestKimiConstants:
    """Tests that kimi exposes model selection metadata."""

    def test_kimi_has_model_flag(self):
        """Kimi supports the same model flag wiring as other model-selectable runners."""
        assert RUNNER_CONFIGS["kimi"]["model_flag"] == "--model"
