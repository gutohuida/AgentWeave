"""Tests for agentweave.yml configuration module."""

import pytest

from agentweave.config import (
    AgentConfig,
    AgentWeaveConfig,
    ConfigValidationError,
    HubConfig,
    JobConfig,
    ProjectConfig,
    QualityConfig,
    _validate_cron,
    _validate_env_field,
    load_agentweave_yml,
    save_agentweave_yml,
)


class TestCronValidation:
    """Tests for cron expression validation."""

    def test_valid_cron_expressions(self):
        """Test various valid cron expressions."""
        valid = [
            "0 9 * * 1-5",  # Weekdays at 9am
            "0 0 * * *",  # Daily at midnight
            "*/5 * * * *",  # Every 5 minutes
            "0 0 1 * *",  # Monthly on the 1st
            "0 0 * * 0",  # Weekly on Sunday
        ]
        for expr in valid:
            assert _validate_cron(expr), f"Should be valid: {expr}"

    def test_invalid_cron_expressions(self):
        """Test various invalid cron expressions."""
        invalid = [
            "0 9 * *",  # Missing field
            "0 9 * * * *",  # Extra field
            "",  # Empty
            "invalid",  # Not a cron expression
        ]
        for expr in invalid:
            assert not _validate_cron(expr), f"Should be invalid: {expr}"


class TestEnvValidation:
    """Tests for env field validation."""

    def test_valid_env_list(self):
        """Test that a list of strings is valid."""
        result = _validate_env_field(["MINIMAX_API_KEY", "ANTHROPIC_API_KEY"], "test")
        assert result == ["MINIMAX_API_KEY", "ANTHROPIC_API_KEY"]

    def test_empty_env_list(self):
        """Test that an empty list is valid."""
        result = _validate_env_field([], "test")
        assert result == []

    def test_env_dict_rejected(self):
        """Test that a dict is rejected with clear error."""
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_env_field({"MINIMAX_API_KEY": "secret"}, "agents.minimax.env")
        assert "list of variable names" in str(exc_info.value)
        assert "not key-value pairs" in str(exc_info.value)

    def test_env_non_string_items_rejected(self):
        """Test that non-string items are rejected."""
        with pytest.raises(ConfigValidationError) as exc_info:
            _validate_env_field(["MINIMAX_API_KEY", 123], "test")
        assert "env items must be strings" in str(exc_info.value)


class TestLoadAgentweaveYml:
    """Tests for loading agentweave.yml."""

    def test_load_minimal_config(self, tmp_path):
        """Test loading a minimal valid configuration."""
        config_file = tmp_path / "agentweave.yml"
        config_file.write_text("""
project:
  name: Test Project
  mode: hierarchical

hub:
  url: http://localhost:8000

agents:
  claude:
    runner: claude
  kimi:
    runner: kimi
""")

        config = load_agentweave_yml(config_file)
        assert config.project.name == "Test Project"
        assert config.project.mode == "hierarchical"
        assert config.hub.url == "http://localhost:8000"
        assert "claude" in config.agents
        assert "kimi" in config.agents
        assert config.agents["claude"].runner == "claude"
        assert config.agents["kimi"].runner == "kimi"

    def test_load_full_config(self, tmp_path):
        """Test loading a configuration with all fields."""
        config_file = tmp_path / "agentweave.yml"
        config_file.write_text("""
project:
  name: Full Test
  mode: peer

hub:
  url: http://hub.example.com:8000

agents:
  claude:
    runner: claude
    roles:
      - tech_lead
      - backend_dev
    yolo: true
    pilot: false
  minimax:
    runner: claude_proxy
    model: MiniMax-M2.7
    env:
      - MINIMAX_API_KEY
    yolo: false
    pilot: true

jobs:
  daily-report:
    schedule: "0 9 * * 1-5"
    agent: claude
    prompt: "Generate daily status report"
    enabled: true
""")

        config = load_agentweave_yml(config_file)
        assert config.project.name == "Full Test"
        assert config.project.mode == "peer"
        assert config.agents["claude"].yolo is True
        assert config.agents["claude"].roles == ["tech_lead", "backend_dev"]
        assert config.agents["minimax"].runner == "claude_proxy"
        assert config.agents["minimax"].env == ["MINIMAX_API_KEY"]

        assert config.jobs is not None
        assert "daily-report" in config.jobs
        assert config.jobs["daily-report"].schedule == "0 9 * * 1-5"
        assert config.jobs["daily-report"].enabled is True

    def test_env_as_dict_rejected(self, tmp_path):
        """Test that env as dict is rejected."""
        config_file = tmp_path / "agentweave.yml"
        config_file.write_text("""
project:
  name: Test

hub:
  url: http://localhost:8000

agents:
  minimax:
    runner: claude_proxy
    env:
      MINIMAX_API_KEY: secret_value
""")

        with pytest.raises(ConfigValidationError) as exc_info:
            load_agentweave_yml(config_file)
        assert "list of variable names" in str(exc_info.value)
        assert "not key-value pairs" in str(exc_info.value)

    def test_invalid_runner_rejected(self, tmp_path):
        """Test that invalid runner values are rejected."""
        config_file = tmp_path / "agentweave.yml"
        config_file.write_text("""
project:
  name: Test

hub:
  url: http://localhost:8000

agents:
  claude:
    runner: invalid_runner
""")

        with pytest.raises(ConfigValidationError) as exc_info:
            load_agentweave_yml(config_file)
        assert "invalid runner" in str(exc_info.value).lower()

    def test_invalid_mode_rejected(self, tmp_path):
        """Test that invalid mode values are rejected."""
        config_file = tmp_path / "agentweave.yml"
        config_file.write_text("""
project:
  name: Test
  mode: invalid_mode

hub:
  url: http://localhost:8000

agents: {}
""")

        with pytest.raises(ConfigValidationError) as exc_info:
            load_agentweave_yml(config_file)
        assert "invalid mode" in str(exc_info.value).lower()

    def test_invalid_cron_rejected(self, tmp_path):
        """Test that invalid cron expressions are rejected."""
        config_file = tmp_path / "agentweave.yml"
        config_file.write_text("""
project:
  name: Test

hub:
  url: http://localhost:8000

agents: {}

jobs:
  bad-job:
    schedule: "not-a-cron"
    agent: claude
    prompt: "test"
""")

        with pytest.raises(ConfigValidationError) as exc_info:
            load_agentweave_yml(config_file)
        assert "invalid cron" in str(exc_info.value).lower()

    def test_yaml_parse_error(self, tmp_path):
        """Test that YAML parse errors are reported with line numbers."""
        config_file = tmp_path / "agentweave.yml"
        config_file.write_text("""
project:
  name: Test
  mode: hierarchical
  invalid: [
    unclosed bracket
""")

        with pytest.raises(ConfigValidationError) as exc_info:
            load_agentweave_yml(config_file)
        assert "YAML parse error" in str(exc_info.value)

    def test_file_not_found(self, tmp_path):
        """Test that FileNotFoundError is raised for missing files."""
        config_file = tmp_path / "nonexistent.yml"

        with pytest.raises(FileNotFoundError):
            load_agentweave_yml(config_file)


class TestSaveAgentweaveYml:
    """Tests for saving agentweave.yml."""

    def test_save_and_load_roundtrip(self, tmp_path):
        """Test that saving and loading produces the same config."""
        config = AgentWeaveConfig(
            project=ProjectConfig(name="Roundtrip Test", mode="peer"),
            hub=HubConfig(url="http://example.com"),
            agents={
                "claude": AgentConfig(
                    runner="claude",
                    roles=["tech_lead"],
                    yolo=True,
                ),
                "kimi": AgentConfig(
                    runner="kimi",
                    pilot=True,
                ),
            },
            jobs={
                "daily": JobConfig(
                    schedule="0 9 * * *",
                    agent="claude",
                    prompt="Daily report",
                    enabled=True,
                ),
            },
        )

        config_file = tmp_path / "agentweave.yml"
        save_agentweave_yml(config, config_file)

        # Load it back and verify
        loaded = load_agentweave_yml(config_file)
        assert loaded.project.name == config.project.name
        assert loaded.project.mode == config.project.mode
        assert loaded.hub.url == config.hub.url
        assert "claude" in loaded.agents
        assert "kimi" in loaded.agents
        assert loaded.agents["claude"].yolo is True
        assert loaded.agents["kimi"].pilot is True

    def test_save_includes_header_comment(self, tmp_path):
        """Test that saved file includes the header comment."""
        config = AgentWeaveConfig()
        config_file = tmp_path / "agentweave.yml"
        save_agentweave_yml(config, config_file)

        content = config_file.read_text()
        assert "AgentWeave Configuration" in content
        assert "SHOULD be committed" in content
        assert "Secret values" in content
        assert "NOT be added here" in content


class TestConfigDataclasses:
    """Tests for config dataclass methods."""

    def test_agent_config_to_dict(self):
        """Test AgentConfig.to_dict()."""
        config = AgentConfig(runner="claude", model="claude-4", yolo=True)
        result = config.to_dict()
        assert result["runner"] == "claude"
        assert result["model"] == "claude-4"
        assert result["yolo"] is True
        # Empty/default fields should be omitted
        assert "roles" not in result
        assert "env" not in result
        assert "pilot" not in result

    def test_job_config_to_dict(self):
        """Test JobConfig.to_dict()."""
        config = JobConfig(
            schedule="0 9 * * *",
            agent="claude",
            prompt="test",
            enabled=False,
        )
        result = config.to_dict()
        assert result["schedule"] == "0 9 * * *"
        assert result["agent"] == "claude"
        assert result["prompt"] == "test"
        assert result["enabled"] is False

    def test_full_config_to_dict(self):
        """Test AgentWeaveConfig.to_dict()."""
        config = AgentWeaveConfig(
            project=ProjectConfig(name="Test", mode="peer"),
            hub=HubConfig(url="http://localhost:8000"),
            agents={"claude": AgentConfig(runner="claude")},
        )
        result = config.to_dict()
        assert result["project"]["name"] == "Test"
        assert result["project"]["mode"] == "peer"
        assert result["hub"]["url"] == "http://localhost:8000"
        assert "claude" in result["agents"]
        assert "jobs" not in result  # None should be omitted


class TestQualityConfig:
    """Tests for QualityConfig parsing, defaults, and validation."""

    def test_defaults(self):
        """QualityConfig should have safe all-off defaults."""
        q = QualityConfig()
        assert q.review_required is False
        assert q.docs_path is None
        assert q.docs_threshold == "never"
        assert q.echo_chamber_guard == "off"
        assert q.attribution_tag is False
        assert q.dependency_check is False

    def test_to_dict_omits_defaults(self):
        """to_dict() should omit fields that match safe defaults."""
        result = QualityConfig().to_dict()
        assert result == {}

    def test_to_dict_includes_set_values(self):
        """to_dict() should include only non-default values."""
        q = QualityConfig(
            review_required=True,
            docs_path="code-docs",
            docs_threshold="non_trivial",
            echo_chamber_guard="enforce",
            attribution_tag=True,
            dependency_check=True,
        )
        result = q.to_dict()
        assert result["review_required"] is True
        assert result["docs_path"] == "code-docs"
        assert result["docs_threshold"] == "non_trivial"
        assert result["echo_chamber_guard"] == "enforce"
        assert result["attribution_tag"] is True
        assert result["dependency_check"] is True

    def test_quality_in_agentweave_config_to_dict(self):
        """AgentWeaveConfig.to_dict() should include quality when set."""
        config = AgentWeaveConfig(
            quality=QualityConfig(review_required=True, docs_threshold="non_trivial"),
        )
        result = config.to_dict()
        assert "quality" in result
        assert result["quality"]["review_required"] is True

    def test_quality_absent_when_none(self):
        """AgentWeaveConfig.to_dict() should omit quality when None."""
        config = AgentWeaveConfig()
        result = config.to_dict()
        assert "quality" not in result

    def test_load_valid_quality_section(self, tmp_path):
        """load_agentweave_yml() should parse a valid quality section."""
        yml = tmp_path / "agentweave.yml"
        yml.write_text(
            "project:\n  name: Test\nquality:\n"
            "  review_required: true\n"
            "  docs_threshold: non_trivial\n"
            "  echo_chamber_guard: warn\n"
        )
        config = load_agentweave_yml(yml)
        assert config.quality is not None
        assert config.quality.review_required is True
        assert config.quality.docs_threshold == "non_trivial"
        assert config.quality.echo_chamber_guard == "warn"

    def test_load_missing_quality_section_uses_none(self, tmp_path):
        """load_agentweave_yml() should return quality=None when section absent."""
        yml = tmp_path / "agentweave.yml"
        yml.write_text("project:\n  name: Test\n")
        config = load_agentweave_yml(yml)
        assert config.quality is None

    def test_invalid_docs_threshold_raises(self, tmp_path):
        """Invalid docs_threshold should raise ConfigValidationError."""
        yml = tmp_path / "agentweave.yml"
        yml.write_text("project:\n  name: Test\nquality:\n  docs_threshold: sometimes\n")
        with pytest.raises(ConfigValidationError, match="docs_threshold"):
            load_agentweave_yml(yml)

    def test_invalid_echo_chamber_guard_raises(self, tmp_path):
        """Invalid echo_chamber_guard should raise ConfigValidationError."""
        yml = tmp_path / "agentweave.yml"
        yml.write_text("project:\n  name: Test\nquality:\n  echo_chamber_guard: strict\n")
        with pytest.raises(ConfigValidationError, match="echo_chamber_guard"):
            load_agentweave_yml(yml)


class TestQualitySessionSerialization:
    """Tests for quality config serialization into session data."""

    def test_quality_key_in_session_data(self):
        """Quality config to_dict() output should be embeddable in session data."""
        q = QualityConfig(
            review_required=True,
            docs_threshold="non_trivial",
            echo_chamber_guard="warn",
        )
        session_data: dict = {}
        session_data["quality"] = q.to_dict()

        assert session_data["quality"]["review_required"] is True
        assert session_data["quality"]["docs_threshold"] == "non_trivial"
        assert session_data["quality"]["echo_chamber_guard"] == "warn"
        assert "docs_path" not in session_data["quality"]

    def test_quality_key_removed_when_none(self):
        """When quality is None the key should be removed from session data."""
        session_data: dict = {"quality": {"review_required": True}}
        # Simulate _activate_agents() branch when config.quality is None
        if "quality" in session_data:
            del session_data["quality"]
        assert "quality" not in session_data

    def test_quality_defaults_produce_empty_dict(self):
        """Default QualityConfig serializes to {} — no noise in session data."""
        q = QualityConfig()
        assert q.to_dict() == {}


class TestEchoChamberGuardDegradation:
    """Tests for echo_chamber_guard single-agent degradation logic."""

    def test_enforce_with_single_agent_degrades_to_warn(self):
        """enforce guard with one active agent should degrade to warn level."""
        q = QualityConfig(echo_chamber_guard="enforce")
        active_agents = ["claude"]

        effective = q.echo_chamber_guard
        if effective == "enforce" and len(active_agents) <= 1:
            effective = "warn"

        assert effective == "warn"

    def test_enforce_with_multiple_agents_stays_enforce(self):
        """enforce guard with multiple agents should remain enforce."""
        q = QualityConfig(echo_chamber_guard="enforce")
        active_agents = ["claude", "gemini"]

        effective = q.echo_chamber_guard
        if effective == "enforce" and len(active_agents) <= 1:
            effective = "warn"

        assert effective == "enforce"

    def test_warn_unaffected_by_agent_count(self):
        """warn guard should not change regardless of agent count."""
        q = QualityConfig(echo_chamber_guard="warn")
        for count in [1, 2, 5]:
            active_agents = [f"agent{i}" for i in range(count)]
            effective = q.echo_chamber_guard
            if effective == "enforce" and len(active_agents) <= 1:
                effective = "warn"
            assert effective == "warn"


class TestGenerateAgentweaveYml:
    """Tests for generate_agentweave_yml quality comment block."""

    def test_generated_file_includes_quality_comment(self, tmp_path):
        """Generated agentweave.yml should include commented-out quality section."""
        from agentweave.config import generate_agentweave_yml
        from agentweave.session import Session

        session = Session(data={
            "name": "Test Project",
            "mode": "hierarchical",
            "agents": {
                "claude": {"runner": "claude", "yolo": False, "pilot": False},
            },
        })

        out_path = tmp_path / "agentweave.yml"
        generate_agentweave_yml(session, path=out_path)

        content = out_path.read_text()
        assert "quality:" in content
        assert "review_required" in content
        assert "docs_threshold" in content
        assert "echo_chamber_guard" in content
        assert "dependency_check" in content
