"""Tests for agentweave init command with agentweave.yml generation."""

import json
import subprocess
import sys

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

    def test_init_creates_gitignore_with_agentweave_runtime_state(self, tmp_path, monkeypatch):
        """Test that init creates .gitignore entries for local AgentWeave state."""
        monkeypatch.chdir(tmp_path)

        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "init", "--project", "TestProject"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        gitignore_path = tmp_path / ".gitignore"
        assert gitignore_path.exists()
        content = gitignore_path.read_text()
        assert "# AgentWeave runtime state" in content
        assert ".agentweave/session.json" in content
        assert ".agentweave/transport.json" in content
        assert ".agentweave/tasks/*/" in content
        assert ".agentweave/messages/*/" in content
        assert ".agentweave/logs/" in content
        assert ".agentweave/project_instructions.md" in content
        assert ".env" in content
        assert "kimichanges.md" in content
        assert "kimiwork.md" in content

    def test_init_creates_env_file(self, tmp_path, monkeypatch):
        """Test that init creates a local .env scaffold for secrets."""
        monkeypatch.chdir(tmp_path)

        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "init", "--project", "TestProject"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        env_path = tmp_path / ".env"
        assert env_path.exists()
        content = env_path.read_text()
        assert "AgentWeave local environment variables" in content
        assert "MINIMAX_API_KEY" in content
        assert "OPENAI_API_KEY" in content
        assert ".env" in (tmp_path / ".gitignore").read_text()

    def test_init_does_not_overwrite_existing_env_file(self, tmp_path, monkeypatch):
        """Test that init preserves an existing .env file."""
        monkeypatch.chdir(tmp_path)
        env_path = tmp_path / ".env"
        env_path.write_text("CUSTOM_KEY=value\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "init", "--project", "TestProject"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        assert env_path.read_text() == "CUSTOM_KEY=value\n"

    def test_init_preserves_existing_gitignore_content(self, tmp_path, monkeypatch):
        """Test that init appends the AgentWeave block without overwriting user entries."""
        monkeypatch.chdir(tmp_path)
        gitignore_path = tmp_path / ".gitignore"
        gitignore_path.write_text("node_modules/\n.env\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "init", "--project", "TestProject"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        content = gitignore_path.read_text()
        assert "node_modules/" in content
        assert ".env" in content
        assert "# AgentWeave runtime state" in content
        assert ".agentweave/session.json" in content

    def test_init_refreshes_existing_agentweave_gitignore_block(self, tmp_path, monkeypatch):
        """Test that init updates an existing managed block instead of duplicating it."""
        monkeypatch.chdir(tmp_path)
        gitignore_path = tmp_path / ".gitignore"
        gitignore_path.write_text(
            "dist/\n\n"
            "# AgentWeave runtime state\n"
            ".agentweave/session.json\n"
            "# End AgentWeave runtime state\n"
            "\ncoverage/\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "init", "--project", "TestProject"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        content = gitignore_path.read_text()
        assert content.count("# AgentWeave runtime state") == 1
        assert "dist/" in content
        assert "coverage/" in content
        assert ".agentweave/transport.json" in content
        assert ".agentweave/tasks/*/" in content

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
        assert (tmp_path / ".gitignore").exists()
        assert ".agentweave/session.json" in (tmp_path / ".gitignore").read_text()
        assert (tmp_path / ".env").exists()

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
        assert "COMMIT this file" in content
        assert "Never put secrets here" in content

    def test_init_creates_project_instructions(self, tmp_path, monkeypatch):
        """Test that init creates .agentweave/project_instructions.md."""
        monkeypatch.chdir(tmp_path)

        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "init", "--project", "Test"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        instructions_path = tmp_path / ".agentweave" / "project_instructions.md"
        assert instructions_path.exists()
        content = instructions_path.read_text()
        assert "Project Instructions" in content
        assert "project-wide rules" in content

    def test_init_does_not_overwrite_project_instructions(self, tmp_path, monkeypatch):
        """Test that re-init with --force does not overwrite project_instructions.md."""
        monkeypatch.chdir(tmp_path)

        # First init
        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "init", "--project", "Test"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        instructions_path = tmp_path / ".agentweave" / "project_instructions.md"
        instructions_path.write_text("Custom content")

        # Re-init with --force
        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "init", "--project", "Test", "--force"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        assert instructions_path.read_text() == "Custom content"

    def test_build_agent_context_prepends_instructions(self, tmp_path, monkeypatch):
        """Test that _build_agent_context prepends project instructions before role guides."""
        monkeypatch.chdir(tmp_path)

        import json as _json

        from agentweave.cli import _build_agent_context
        from agentweave.constants import AGENTWEAVE_DIR, ROLES_CONFIG_FILE, ROLES_DIR
        from agentweave.session import Session

        # Create a session with one agent
        session = Session.create(
            name="Test Project",
            principal="claude",
            mode="hierarchical",
            agents=["claude"],
        )
        session.save()

        # Assign a role to claude
        AGENTWEAVE_DIR.mkdir(parents=True, exist_ok=True)
        roles_config = {
            "version": 1,
            "agent_assignments": {"claude": "backend_dev"},
            "agent_roles": {"claude": ["backend_dev"]},
            "roles": {"backend_dev": {"label": "Backend Developer"}},
        }
        ROLES_CONFIG_FILE.write_text(_json.dumps(roles_config), encoding="utf-8")

        # Create a project instructions file
        instructions_path = AGENTWEAVE_DIR / "project_instructions.md"
        instructions_path.write_text("# Global Rules\n\nAlways write tests.")

        # Create a role guide file
        ROLES_DIR.mkdir(parents=True, exist_ok=True)
        role_path = ROLES_DIR / "backend_dev.md"
        role_path.write_text("# Backend Dev\n\nUse FastAPI.")

        # Build context
        content = _build_agent_context("claude", session, "v-test")

        # Verify instructions are prepended before role guide
        instructions_idx = content.find("# Global Rules")
        role_idx = content.find("# Backend Dev")
        assert instructions_idx != -1, "Instructions not found in context"
        assert role_idx != -1, "Role guide not found in context"
        assert instructions_idx < role_idx, "Instructions should appear before role guide"
        assert "---" in content, "Separator should be present between instructions and role guide"

    def test_get_project_instructions_local_file(self, tmp_path, monkeypatch):
        """Test _get_project_instructions reads local file."""
        monkeypatch.chdir(tmp_path)

        from agentweave.cli import _get_project_instructions
        from agentweave.constants import AGENTWEAVE_DIR

        AGENTWEAVE_DIR.mkdir(parents=True, exist_ok=True)
        instructions_path = AGENTWEAVE_DIR / "project_instructions.md"
        instructions_path.write_text("Local instructions")

        result = _get_project_instructions()
        assert result == "Local instructions"

    def test_get_project_instructions_empty_when_no_file(self, tmp_path, monkeypatch):
        """Test _get_project_instructions returns empty when no file exists."""
        monkeypatch.chdir(tmp_path)

        from agentweave.cli import _get_project_instructions

        result = _get_project_instructions()
        assert result == ""


class TestInitUnit:
    """Unit tests for init-related functions."""

    def test_generate_agentweave_yml_from_session(self, tmp_path, monkeypatch):
        """Test generate_agentweave_yml function directly."""
        monkeypatch.chdir(tmp_path)

        # Create a session
        from agentweave.config import generate_agentweave_yml
        from agentweave.session import Session

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

        from agentweave.config import generate_agentweave_yml
        from agentweave.session import Session

        session = Session.create(name="Defaults Test")
        yml_path = generate_agentweave_yml(session)

        content = yaml.safe_load(yml_path.read_text())

        # Check defaults
        assert content["hub"]["url"] == "http://localhost:8000"
        assert content["agents"]["claude"]["runner"] == "claude"
        assert content["agents"]["kimi"]["runner"] == "kimi"
