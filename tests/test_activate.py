"""Tests for agentweave activate command."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import yaml

from agentweave.config import AgentWeaveConfig, AgentConfig, ProjectConfig, HubConfig


@pytest.fixture
def agentweave_installed():
    """Check if agentweave is installed."""
    result = subprocess.run(
        [sys.executable, "-m", "agentweave", "--version"],
        capture_output=True,
    )
    return result.returncode == 0


class TestActivateCommand:
    """Tests for the activate command."""

    def test_activate_requires_agentweave_yml(self, tmp_path, monkeypatch):
        """Test that activate fails without agentweave.yml."""
        monkeypatch.chdir(tmp_path)

        # Create .agentweave directory but no agentweave.yml
        (tmp_path / ".agentweave").mkdir()

        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "activate"],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert (
            "agentweave.yml" in result.stderr.lower() or "agentweave.yml" in result.stdout.lower()
        )

    def test_activate_creates_session(self, tmp_path, monkeypatch):
        """Test that activate creates session from agentweave.yml."""
        monkeypatch.chdir(tmp_path)

        # Create agentweave.yml
        config = {
            "project": {"name": "Activate Test", "mode": "hierarchical"},
            "hub": {"url": "http://localhost:8000"},
            "agents": {
                "claude": {"runner": "claude"},
                "kimi": {"runner": "kimi"},
            },
        }
        (tmp_path / "agentweave.yml").write_text(yaml.dump(config))

        # Run activate
        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "activate"],
            capture_output=True,
            text=True,
        )

        # Should succeed (though transport/watchdog might fail)
        # Check that session.json was created
        session_file = tmp_path / ".agentweave" / "session.json"
        assert session_file.exists(), "Session file should be created"

        # Verify session content
        session_data = json.loads(session_file.read_text())
        assert session_data["name"] == "Activate Test"
        assert "claude" in session_data["agents"]
        assert "kimi" in session_data["agents"]

    def test_activate_is_idempotent(self, tmp_path, monkeypatch):
        """Test that running activate twice is safe."""
        monkeypatch.chdir(tmp_path)

        # Create agentweave.yml
        config = {
            "project": {"name": "Idempotent Test", "mode": "hierarchical"},
            "hub": {"url": "http://localhost:8000"},
            "agents": {"claude": {"runner": "claude"}},
        }
        (tmp_path / "agentweave.yml").write_text(yaml.dump(config))

        # First activate
        result1 = subprocess.run(
            [sys.executable, "-m", "agentweave", "activate"],
            capture_output=True,
            text=True,
        )

        # Get session after first run
        session_file = tmp_path / ".agentweave" / "session.json"
        session1 = json.loads(session_file.read_text())

        # Second activate
        result2 = subprocess.run(
            [sys.executable, "-m", "agentweave", "activate"],
            capture_output=True,
            text=True,
        )

        # Get session after second run
        session2 = json.loads(session_file.read_text())

        # Sessions should be the same (idempotent)
        assert session1["id"] == session2["id"]
        assert session1["name"] == session2["name"]


class TestActivateUnit:
    """Unit tests for activate functionality."""

    def test_sync_agents_adds_new(self, tmp_path, monkeypatch):
        """Test that sync_agents adds new agents."""
        monkeypatch.chdir(tmp_path)

        from agentweave.session import Session

        session = Session.create(name="Test", agents=["claude"])

        declared = {
            "claude": {"runner": "claude"},
            "kimi": {"runner": "kimi"},
            "gemini": {"runner": "native"},
        }

        added, updated, orphaned = session.sync_agents(declared)

        assert "kimi" in added
        assert "gemini" in added
        assert "claude" not in added  # Already exists
        assert len(orphaned) == 0

        # Verify agents were added
        assert "kimi" in session.agents
        assert "gemini" in session.agents

    def test_sync_agents_detects_orphaned(self, tmp_path, monkeypatch):
        """Test that sync_agents detects orphaned agents."""
        monkeypatch.chdir(tmp_path)

        from agentweave.session import Session

        session = Session.create(name="Test", agents=["claude", "kimi", "gemini"])

        declared = {
            "claude": {"runner": "claude"},
        }

        added, updated, orphaned = session.sync_agents(declared)

        assert "kimi" in orphaned
        assert "gemini" in orphaned
        assert "claude" not in orphaned

    def test_sync_agents_updates_config(self, tmp_path, monkeypatch):
        """Test that sync_agents updates agent configuration."""
        monkeypatch.chdir(tmp_path)

        from agentweave.session import Session

        session = Session.create(name="Test", agents=["claude"])

        declared = {
            "claude": {
                "runner": "claude",
                "yolo": True,
                "pilot": True,
                "env": ["ANTHROPIC_API_KEY"],
            },
        }

        session.sync_agents(declared)

        # Verify configuration was applied
        agent_data = session.agents["claude"]
        assert agent_data.get("yolo") is True
        assert agent_data.get("pilot") is True
        assert "env_vars" in agent_data
        assert "ANTHROPIC_API_KEY" in agent_data["env_vars"]

    def test_activate_transport_step_skips_if_configured(self, tmp_path, monkeypatch):
        """Test that transport step skips if already configured."""
        monkeypatch.chdir(tmp_path)

        from agentweave.cli import _activate_transport
        from agentweave.utils import save_json

        # Create existing transport config
        agentweave_dir = tmp_path / ".agentweave"
        agentweave_dir.mkdir()
        save_json(
            agentweave_dir / "transport.json",
            {"type": "http", "url": "http://localhost:8000", "api_key": "test"},
        )

        config = MagicMock()
        config.hub.url = "http://localhost:8000"

        result = _activate_transport(config)
        assert result == 0


class TestActivateMcp:
    """Unit tests for _activate_mcp() — verifies MCP registration status
    is checked per-agent (not just the principal) so file-based runners
    like opencode don't get silently skipped when the principal is
    already registered via CLI.
    """

    @pytest.fixture
    def session_with_opencode(self, tmp_path, monkeypatch):
        """Create a session with one CLI-based agent (kimi, principal)
        and one file-based agent (opencode)."""
        monkeypatch.chdir(tmp_path)
        from agentweave.session import Session
        from agentweave.utils import save_json

        agentweave_dir = tmp_path / ".agentweave"
        agentweave_dir.mkdir()
        session = Session.create(
            name="Test",
            principal="kimi",
            agents=["kimi", "opencode"],
        )
        # Tag the agents with their runners
        session._data["agents"]["kimi"]["runner"] = "kimi"
        session._data["agents"]["opencode"]["runner"] = "opencode"
        save_json(agentweave_dir / "session.json", session.to_dict())
        return session

    def test_opencode_mcp_check_via_file_when_principal_already_registered(
        self, session_with_opencode, monkeypatch
    ):
        """Regression: principal (kimi) has MCP via CLI, but opencode's
        file-based MCP is missing. _activate_mcp must NOT report
        'Already registered' — it must run cmd_mcp_setup so opencode.json
        gets the mcp.agentweave block."""
        from agentweave.cli import _activate_mcp

        calls = {"cmd_mcp_setup": 0}

        def _fake_setup(args):
            calls["cmd_mcp_setup"] += 1
            # Simulate the file-based registration by writing opencode.json
            import json as _json
            (Path(".").resolve() / "opencode.json").write_text(
                _json.dumps({"mcp": {"agentweave": {"type": "local", "command": ["agentweave-mcp"]}}})
            )
            return 0

        # Simulate: kimi mcp list → contains 'agentweave' (principal registered)
        fake_kimi_mcp_list = subprocess.CompletedProcess(
            args=["kimi", "mcp", "list"],
            returncode=0,
            stdout="agentweave  stdio  agentweave-mcp",
            stderr="",
        )
        with patch("agentweave.cli.cmd_mcp_setup", _fake_setup), patch(
            "subprocess.run", return_value=fake_kimi_mcp_list
        ):
            result = _activate_mcp()

        # The fix: cmd_mcp_setup MUST be called even though the principal
        # is already registered, because opencode's file-based MCP is missing.
        assert calls["cmd_mcp_setup"] == 1
        assert result == 0
        # And the opencode.json should now have the MCP block
        data = json.loads(Path("opencode.json").read_text(encoding="utf-8"))
        assert "agentweave" in data["mcp"]

    def test_principal_only_session_skips_when_registered(self, tmp_path, monkeypatch):
        """When the only agent is the principal and it is already
        registered, _activate_mcp should report 'Already registered'
        without calling cmd_mcp_setup."""
        monkeypatch.chdir(tmp_path)
        from agentweave.cli import _activate_mcp
        from agentweave.session import Session
        from agentweave.utils import save_json

        agentweave_dir = tmp_path / ".agentweave"
        agentweave_dir.mkdir()
        session = Session.create(name="Test", principal="kimi", agents=["kimi"])
        session._data["agents"]["kimi"]["runner"] = "kimi"
        save_json(agentweave_dir / "session.json", session.to_dict())

        calls = {"cmd_mcp_setup": 0}

        def _fake_setup(args):
            calls["cmd_mcp_setup"] += 1
            return 0

        fake_kimi_mcp_list = subprocess.CompletedProcess(
            args=["kimi", "mcp", "list"],
            returncode=0,
            stdout="agentweave  stdio  agentweave-mcp",
            stderr="",
        )
        with patch("agentweave.cli.cmd_mcp_setup", _fake_setup), patch(
            "subprocess.run", return_value=fake_kimi_mcp_list
        ):
            result = _activate_mcp()

        assert calls["cmd_mcp_setup"] == 0
        assert result == 0

    def test_opencode_file_missing_triggers_registration(
        self, session_with_opencode, monkeypatch
    ):
        """When opencode.json is missing (or has no agentweave entry)
        and kimi is registered, _activate_mcp must still call
        cmd_mcp_setup to write the opencode MCP block."""
        from agentweave.cli import _activate_mcp

        calls = {"cmd_mcp_setup": 0}

        def _fake_setup(args):
            calls["cmd_mcp_setup"] += 1
            import json as _json
            (Path(".").resolve() / "opencode.json").write_text(
                _json.dumps({"mcp": {"agentweave": {"type": "local", "command": ["agentweave-mcp"]}}})
            )
            return 0

        fake_kimi_mcp_list = subprocess.CompletedProcess(
            args=["kimi", "mcp", "list"],
            returncode=0,
            stdout="agentweave  stdio  agentweave-mcp",
            stderr="",
        )
        # Pre-condition: opencode.json does NOT exist
        assert not Path("opencode.json").exists()
        with patch("agentweave.cli.cmd_mcp_setup", _fake_setup), patch(
            "subprocess.run", return_value=fake_kimi_mcp_list
        ):
            result = _activate_mcp()

        assert calls["cmd_mcp_setup"] == 1
        assert result == 0
        assert Path("opencode.json").exists()

    def test_all_agents_file_based_all_registered(self, tmp_path, monkeypatch):
        """All agents are opencode (file-based) and opencode.json has
        the MCP block. _activate_mcp reports 'Already registered'
        without calling cmd_mcp_setup."""
        monkeypatch.chdir(tmp_path)
        from agentweave.cli import _activate_mcp
        from agentweave.session import Session
        from agentweave.utils import save_json

        agentweave_dir = tmp_path / ".agentweave"
        agentweave_dir.mkdir()
        session = Session.create(name="Test", principal="opencode", agents=["opencode"])
        session._data["agents"]["opencode"]["runner"] = "opencode"
        save_json(agentweave_dir / "session.json", session.to_dict())

        # Write opencode.json with the agentweave block
        Path("opencode.json").write_text(
            json.dumps({"mcp": {"agentweave": {"type": "local", "command": ["agentweave-mcp"]}}})
        )

        calls = {"cmd_mcp_setup": 0}

        def _fake_setup(args):
            calls["cmd_mcp_setup"] += 1
            return 0

        with patch("agentweave.cli.cmd_mcp_setup", _fake_setup):
            result = _activate_mcp()

        assert calls["cmd_mcp_setup"] == 0
        assert result == 0

    def test_malformed_opencode_json_triggers_registration(
        self, session_with_opencode, monkeypatch
    ):
        """A malformed opencode.json must not be treated as 'registered';
        the activate should fall through to cmd_mcp_setup which will
        surface the error to the user."""
        from agentweave.cli import _activate_mcp

        calls = {"cmd_mcp_setup": 0}

        def _fake_setup(args):
            calls["cmd_mcp_setup"] += 1
            return 0

        fake_kimi_mcp_list = subprocess.CompletedProcess(
            args=["kimi", "mcp", "list"],
            returncode=0,
            stdout="agentweave  stdio  agentweave-mcp",
            stderr="",
        )
        Path("opencode.json").write_text("{ this is not json")
        with patch("agentweave.cli.cmd_mcp_setup", _fake_setup), patch(
            "subprocess.run", return_value=fake_kimi_mcp_list
        ):
            result = _activate_mcp()

        assert calls["cmd_mcp_setup"] == 1


class TestActivateValidation:
    """Tests for activate input validation."""

    def test_activate_rejects_invalid_yaml(self, tmp_path, monkeypatch):
        """Test that activate rejects invalid agentweave.yml."""
        monkeypatch.chdir(tmp_path)

        # Create invalid agentweave.yml (env as dict)
        config = {
            "project": {"name": "Test", "mode": "hierarchical"},
            "hub": {"url": "http://localhost:8000"},
            "agents": {
                "minimax": {
                    "runner": "claude_proxy",
                    "env": {"MINIMAX_API_KEY": "secret"},  # Invalid: should be list
                },
            },
        }
        (tmp_path / "agentweave.yml").write_text(yaml.dump(config))

        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "activate"],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        output = (result.stdout + result.stderr).lower()
        assert "env" in output or "key-value" in output

    def test_activate_rejects_invalid_mode(self, tmp_path, monkeypatch):
        """Test that activate rejects invalid mode in YAML."""
        monkeypatch.chdir(tmp_path)

        config = {
            "project": {"name": "Test", "mode": "invalid_mode"},
            "hub": {"url": "http://localhost:8000"},
            "agents": {},
        }
        (tmp_path / "agentweave.yml").write_text(yaml.dump(config))

        result = subprocess.run(
            [sys.executable, "-m", "agentweave", "activate"],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
