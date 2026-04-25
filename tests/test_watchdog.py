"""Tests for watchdog dispatch logic."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentweave.watchdog import _agent_ping_cmd


class TestAgentPingCmdOpencode:
    """Tests for _agent_ping_cmd with opencode runner."""

    @pytest.fixture(autouse=True)
    def setup_session(self, tmp_path):
        """Set up a temporary session with an opencode agent."""
        self.tmp_path = tmp_path
        self.session_dir = tmp_path / ".agentweave"
        self.session_dir.mkdir()
        self.agents_dir = self.session_dir / "agents"
        self.agents_dir.mkdir()
        self.context_dir = self.session_dir / "context"
        self.context_dir.mkdir()

        session_data = {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "principal": "claude",
            "agents": {
                "opencode-dev": {"runner": "opencode", "model": "ollama/qwen2.5-coder:7b"},
                "opencode-qa": {"runner": "opencode"},
            },
        }
        session_file = self.session_dir / "session.json"
        session_file.write_text(json.dumps(session_data))

        from agentweave.session import Session

        self.session = Session(session_data)

        with patch("agentweave.watchdog.AGENTS_DIR", self.agents_dir):
            with patch("agentweave.watchdog.AGENT_CONTEXT_DIR", self.context_dir):
                with patch("agentweave.session.Session.load", return_value=self.session):
                    yield

    def test_opencode_basic_no_session_no_model(self):
        """Basic dispatch without session or model."""
        cmd = _agent_ping_cmd("opencode-qa", "do the task")
        assert cmd[0] == "opencode"
        assert cmd[1] == "run"
        assert cmd[2] == "--session"
        assert cmd[3] == "agentweave-opencode-qa"
        assert cmd[4] == "--format"
        assert cmd[5] == "json"
        assert cmd[6] == "do the task"

    def test_opencode_with_model(self):
        """Dispatch with model flag when agent config has a model."""
        cmd = _agent_ping_cmd("opencode-dev", "do the task")
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "ollama/qwen2.5-coder:7b"

    def test_opencode_with_context_file(self):
        """Role file injected when present."""
        context_file = self.context_dir / "opencode-dev.md"
        context_file.write_text("# Context")
        cmd = _agent_ping_cmd("opencode-dev", "do the task")
        assert "--file" in cmd
        idx = cmd.index("--file")
        assert cmd[idx + 1] == str(context_file)

    def test_opencode_without_context_file(self):
        """No --file flag when context file does not exist."""
        cmd = _agent_ping_cmd("opencode-qa", "do the task")
        assert "--file" not in cmd

    def test_opencode_preserves_provided_session_id(self):
        """When a session_id is provided, it is used instead of computing stable id."""
        cmd = _agent_ping_cmd("opencode-dev", "do the task", session_id="custom-session-123")
        assert "--session" in cmd
        idx = cmd.index("--session")
        assert cmd[idx + 1] == "custom-session-123"

    def test_opencode_saves_stable_session_id(self):
        """Stable session ID is saved to agent session file."""
        session_file = self.agents_dir / "opencode-qa-session.json"
        assert not session_file.exists()
        _agent_ping_cmd("opencode-qa", "do the task")
        assert session_file.exists()
        data = json.loads(session_file.read_text())
        assert data["session_id"] == "agentweave-opencode-qa"
