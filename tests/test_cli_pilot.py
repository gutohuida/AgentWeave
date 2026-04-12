"""Integration tests for pilot mode CLI commands."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


# Skip all tests if agentweave is not installed
agentweave_installed = subprocess.run(
    [sys.executable, "-m", "agentweave", "--version"],
    capture_output=True,
).returncode == 0


@pytest.mark.skipif(not agentweave_installed, reason="agentweave not installed")
def test_agent_configure_pilot_flag(tmp_path, monkeypatch):
    """Test that 'agentweave agent configure <agent> --pilot' updates session.json."""
    monkeypatch.chdir(tmp_path)

    # Initialize a session
    result = subprocess.run(
        [sys.executable, "-m", "agentweave", "init", "--project", "PilotTest"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Init failed: {result.stderr}"

    # Enable pilot mode for claude
    result = subprocess.run(
        [sys.executable, "-m", "agentweave", "agent", "configure", "claude", "--pilot"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Configure --pilot failed: {result.stderr}"
    assert "pilot mode enabled" in result.stdout.lower() or "Pilot mode enabled" in result.stdout

    # Check session.json
    session_file = tmp_path / ".agentweave" / "session.json"
    assert session_file.exists()
    session_data = json.loads(session_file.read_text())
    assert session_data["agents"]["claude"]["pilot"] is True
    assert session_data["agents"]["kimi"].get("pilot", False) is False

    # Disable pilot mode
    result = subprocess.run(
        [sys.executable, "-m", "agentweave", "agent", "configure", "claude", "--no-pilot"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Configure --no-pilot failed: {result.stderr}"

    # Check session.json again
    session_data = json.loads(session_file.read_text())
    assert session_data["agents"]["claude"]["pilot"] is False


@pytest.mark.skipif(not agentweave_installed, reason="agentweave not installed")
def test_session_register_prints_launch_command_claude(tmp_path, monkeypatch):
    """Test that 'session register' prints correct launch command for claude."""
    monkeypatch.chdir(tmp_path)

    # Initialize a session
    result = subprocess.run(
        [sys.executable, "-m", "agentweave", "init", "--project", "PilotTest"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Register a session for claude
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentweave",
            "session",
            "register",
            "--agent",
            "claude",
            "--session",
            "sess-abc123",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Session register failed: {result.stderr}"

    # Check output contains claude launch command
    assert "sess-abc123" in result.stdout
    assert "claude" in result.stdout.lower()
    assert "--resume" in result.stdout
    assert "--append-system-prompt-file" in result.stdout

    # Check local session file was created
    agent_session_file = tmp_path / ".agentweave" / "agents" / "claude-session.json"
    assert agent_session_file.exists()
    session_data = json.loads(agent_session_file.read_text())
    assert session_data["session_id"] == "sess-abc123"


@pytest.mark.skipif(not agentweave_installed, reason="agentweave not installed")
def test_session_register_prints_launch_command_kimi(tmp_path, monkeypatch):
    """Test that 'session register' prints correct launch command for kimi."""
    monkeypatch.chdir(tmp_path)

    # Initialize a session
    result = subprocess.run(
        [sys.executable, "-m", "agentweave", "init", "--project", "PilotTest"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Register a session for kimi
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentweave",
            "session",
            "register",
            "--agent",
            "kimi",
            "--session",
            "kimi-session-xyz",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Session register failed: {result.stderr}"

    # Check output contains kimi launch command
    assert "kimi-session-xyz" in result.stdout
    assert "kimi" in result.stdout.lower()
    assert "--session" in result.stdout

    # Check context regeneration note
    assert ".agentweave/context/kimi.md" in result.stdout or "agent context" in result.stdout.lower()


@pytest.mark.skipif(not agentweave_installed, reason="agentweave not installed")
def test_session_register_invalid_agent(tmp_path, monkeypatch):
    """Test that 'session register' fails for agent not in session."""
    monkeypatch.chdir(tmp_path)

    # Initialize a session
    result = subprocess.run(
        [sys.executable, "-m", "agentweave", "init", "--project", "PilotTest"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Try to register for unknown agent
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentweave",
            "session",
            "register",
            "--agent",
            "unknown_agent",
            "--session",
            "sess-123",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "not in the current session" in result.stderr.lower() or "not in session" in result.stdout.lower()
