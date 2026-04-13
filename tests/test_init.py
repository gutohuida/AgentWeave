"""Tests for agentweave init command with agentweave.yml generation."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import yaml


@pytest.fixture
def agentweave_installed():
    """Check if agentweave is installed."""
    result = subprocess.run(
        [sys.executable, "-m", "agentweave", "--version"],
        capture_output=True,
    )
    return result.returncode == 0


@pytest.mark.skipif(
    subprocess.run(
        [sys.executable, "-m", "agentweave", "--version"],
        capture_output=True,
    ).returncode
    != 0,
    reason="agentweave not installed",
)
class TestInitCommand:
    """Tests for the init command."""

    def test_init_creates_agentweave_yml(self, tmp_path, monkeypatch):
        """Test that init creates agentweave.yml with session agents."""
        monkeypatch.chdir(tmp_path)

        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "init", "--project", "TestProject"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Check agentweave.yml was created
        yml_path = tmp_path / "agentweave.yml"
        assert yml_path.exists(), "agentweave.yml was not created"

        # Parse and verify content
        content = yaml.safe_load(yml_path.read_text())
        assert content["project"]["name"] == "TestProject"
        assert content["project"]["mode"] == "hierarchical"
        assert content["hub"]["url"] == "http://localhost:8000"
        # Default agents: claude, kimi
        assert "claude" in content["agents"]
        assert "kimi" in content["agents"]

    def test_init_with_agents_flag_shows_deprecation(self, tmp_path, monkeypatch):
        """Test that using --agents flag shows deprecation warning."""
        monkeypatch.chdir(tmp_path)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agentweave",
                "init",
                "--project",
                "Test",
                "--agents",
                "claude,kimi,gemini",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Check deprecation warning is shown
        assert "deprecated" in result.stdout.lower() or "deprecated" in result.stderr.lower()

        # Verify agents are still created (backward compatibility)
        yml_path = tmp_path / "agentweave.yml"
        content = yaml.safe_load(yml_path.read_text())
        assert "gemini" in content["agents"]

    def test_init_migration_from_existing_session(self, tmp_path, monkeypatch):
        """Test that init detects existing session and generates agentweave.yml."""
        monkeypatch.chdir(tmp_path)

        # Create a session.json manually
        agentweave_dir = tmp_path / ".agentweave"
        agentweave_dir.mkdir()

        session_data = {
            "id": "test-session-123",
            "name": "Existing Project",
            "mode": "peer",
            "principal": "claude",
            "agents": {
                "claude": {"role": "principal", "runner": "claude", "yolo": True},
                "kimi": {"role": "delegate", "runner": "kimi", "pilot": True},
            },
            "created": "2026-01-01T00:00:00Z",
            "updated": "2026-01-01T00:00:00Z",
            "active_tasks": [],
            "completed_tasks": [],
        }
        session_file = agentweave_dir / "session.json"
        session_file.write_text(json.dumps(session_data))

        # Run init
        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "init"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Check migration message
        assert "existing session" in result.stdout.lower() or "generated" in result.stdout.lower()

        # Verify agentweave.yml was created with existing session data
        yml_path = tmp_path / "agentweave.yml"
        assert yml_path.exists()

        content = yaml.safe_load(yml_path.read_text())
        assert content["project"]["name"] == "Existing Project"
        assert content["project"]["mode"] == "peer"
        assert content["agents"]["claude"]["yolo"] is True
        assert content["agents"]["kimi"]["pilot"] is True

    def test_init_creates_yaml_with_header_comment(self, tmp_path, monkeypatch):
        """Test that created agentweave.yml includes header comment."""
        monkeypatch.chdir(tmp_path)

        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "init", "--project", "Test"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        yml_path = tmp_path / "agentweave.yml"
        content = yml_path.read_text()

        # Check header comments are present
        assert "AgentWeave Configuration" in content
        assert "SHOULD be committed" in content
        assert "Secret values" in content
        assert "NOT be added here" in content


class TestInitUnit:
    """Unit tests for init-related functions."""

    def test_generate_agentweave_yml_from_session(self, tmp_path, monkeypatch):
        """Test generate_agentweave_yml function directly."""
        monkeypatch.chdir(tmp_path)

        # Create a session
        from agentweave.session import Session
        from agentweave.config import generate_agentweave_yml

        session = Session.create(
            name="Unit Test Project",
            principal="claude",
            mode="peer",
            agents=["claude", "kimi"],
        )
        session._data["agents"]["claude"]["yolo"] = True
        session._data["agents"]["kimi"]["pilot"] = True

        # Generate YAML
        yml_path = generate_agentweave_yml(session)

        assert yml_path.exists()
        content = yaml.safe_load(yml_path.read_text())

        assert content["project"]["name"] == "Unit Test Project"
        assert content["project"]["mode"] == "peer"
        assert content["agents"]["claude"]["yolo"] is True
        assert content["agents"]["kimi"]["pilot"] is True

    def test_agentweave_yml_default_values(self, tmp_path, monkeypatch):
        """Test that agentweave.yml has correct default values."""
        monkeypatch.chdir(tmp_path)

        from agentweave.session import Session
        from agentweave.config import generate_agentweave_yml

        session = Session.create(name="Defaults Test")
        yml_path = generate_agentweave_yml(session)

        content = yaml.safe_load(yml_path.read_text())

        # Check defaults
        assert content["hub"]["url"] == "http://localhost:8000"
        assert content["agents"]["claude"]["runner"] == "claude"
        assert content["agents"]["kimi"]["runner"] == "kimi"
