"""Tests for CLI helpers."""

import json
from pathlib import Path

import pytest

from agentweave.cli import _write_opencode_mcp_config


class TestWriteOpencodeMcpConfig:
    """Tests for _write_opencode_mcp_config helper."""

    def test_creates_new_file_when_missing(self, tmp_path, monkeypatch):
        """When opencode.json does not exist, create from scratch."""
        monkeypatch.chdir(tmp_path)
        ok, path, msg = _write_opencode_mcp_config("agentweave-mcp")
        assert ok is True
        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["mcp"]["agentweave"]["type"] == "local"
        assert data["mcp"]["agentweave"]["command"] == ["agentweave-mcp"]

    def test_merges_into_existing_file(self, tmp_path, monkeypatch):
        """When opencode.json exists with other keys, preserve them."""
        monkeypatch.chdir(tmp_path)
        existing = {"theme": "dark", "editor": {"fontSize": 14}}
        Path("opencode.json").write_text(json.dumps(existing))
        ok, path, msg = _write_opencode_mcp_config("agentweave-mcp")
        assert ok is True
        data = json.loads(Path(path).read_text())
        assert data["theme"] == "dark"
        assert data["editor"]["fontSize"] == 14
        assert data["mcp"]["agentweave"]["type"] == "local"

    def test_overwrites_existing_agentweave_entry(self, tmp_path, monkeypatch):
        """Overwrite existing mcp.agentweave entry while preserving other keys."""
        monkeypatch.chdir(tmp_path)
        existing = {
            "mcp": {
                "agentweave": {"type": "old", "command": ["old-cmd"]},
                "other": {"type": "local", "command": ["other-cmd"]},
            }
        }
        Path("opencode.json").write_text(json.dumps(existing))
        ok, path, msg = _write_opencode_mcp_config("agentweave-mcp")
        assert ok is True
        data = json.loads(Path(path).read_text())
        assert data["mcp"]["agentweave"]["command"] == ["agentweave-mcp"]
        assert data["mcp"]["other"]["command"] == ["other-cmd"]

    def test_handles_malformed_json(self, tmp_path, monkeypatch, capsys):
        """Malformed JSON prints error, returns failure, does not overwrite."""
        monkeypatch.chdir(tmp_path)
        Path("opencode.json").write_text("{not valid json")
        ok, path, msg = _write_opencode_mcp_config("agentweave-mcp")
        assert ok is False
        captured = capsys.readouterr()
        assert "Malformed opencode.json" in captured.out
        # File should still contain the malformed content
        assert "not valid json" in Path(path).read_text()

    def test_handles_non_object_json(self, tmp_path, monkeypatch, capsys):
        """JSON that is not an object returns failure."""
        monkeypatch.chdir(tmp_path)
        Path("opencode.json").write_text("[1, 2, 3]")
        ok, path, msg = _write_opencode_mcp_config("agentweave-mcp")
        assert ok is False
        captured = capsys.readouterr()
        assert "not a JSON object" in captured.out


class TestMcpSetupCodex:
    """Tests for cmd_mcp_setup with codex runner."""

    def test_mcp_setup_produces_codex_command(self, tmp_path, monkeypatch):
        """cmd_mcp_setup builds correct 'codex mcp add' for codex agent."""
        import argparse
        import json

        from agentweave.cli import cmd_mcp_setup

        monkeypatch.chdir(tmp_path)
        session_dir = tmp_path / ".agentweave"
        session_dir.mkdir()
        session_data = {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "principal": "claude",
            "agents": {
                "codex-dev": {"runner": "codex"},
            },
        }
        (session_dir / "session.json").write_text(json.dumps(session_data))

        # Mock subprocess to avoid actually running codex CLI
        import subprocess
        original_run = subprocess.run

        def mock_run(cmd, **kwargs):
            class Result:
                returncode = 0
                stdout = ""
                stderr = ""
            # Simulate --version check
            if "--version" in cmd:
                r = Result()
                r.returncode = 0
                return r
            # Capture the actual mcp add command
            if "mcp" in cmd and "add" in cmd:
                self.captured_cmd = cmd
                r = Result()
                r.returncode = 0
                return r
            return original_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", mock_run)

        args = argparse.Namespace()
        result = cmd_mcp_setup(args)
        assert result == 0
        assert hasattr(self, "captured_cmd")
        assert self.captured_cmd == ["codex", "mcp", "add", "agentweave", "--", "agentweave-mcp"]
