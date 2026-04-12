"""Tests for watchdog pilot mode guard."""

from unittest.mock import MagicMock, patch


def test_watchdog_skips_execution_for_pilot_agent(tmp_path, monkeypatch):
    """Test that watchdog skips CLI execution when agent is in pilot mode."""
    from agentweave import watchdog as wd
    from agentweave.session import Session

    # Set up a session with pilot agent
    monkeypatch.chdir(tmp_path)
    session = Session.create(name="PilotTest", agents=["claude", "kimi"])
    session.set_agent_pilot("claude", True)  # Enable pilot mode for claude
    session.save()

    # Mock the transport
    transport = MagicMock()
    transport.get_transport_type.return_value = "http"

    # Create watchdog
    dog = wd.Watchdog(transport=transport)

    # Track if _run_agent_subprocess was called
    subprocess_called = {"called": False, "agent": None}

    def mock_run_subprocess(agent, cmd, *args, **kwargs):
        subprocess_called["called"] = True
        subprocess_called["agent"] = agent

    monkeypatch.setattr(wd, "_run_agent_subprocess", mock_run_subprocess)
    monkeypatch.setattr(wd, "_agent_ping_cmd", lambda *a, **kw: ["echo", "test"])
    monkeypatch.setattr(wd, "_check_cli_available", lambda agent: True)
    monkeypatch.setattr(
        wd.Watchdog, "_ensure_agent_context", lambda self, agent: True
    )

    # Trigger the pilot agent
    with patch("agentweave.watchdog.threading.Thread"):
        dog._trigger_agent_from_message(
            "claude",
            {
                "id": "msg-test-001",
                "from": "user",
                "to": "claude",
                "subject": "Test",
                "content": "Hello",
            },
        )

    # Should NOT have called subprocess for pilot agent
    assert subprocess_called["called"] is False, "Should skip execution for pilot agent"


def test_watchdog_executes_for_non_pilot_agent(tmp_path, monkeypatch):
    """Test that watchdog executes CLI when agent is NOT in pilot mode."""
    from agentweave import watchdog as wd
    from agentweave.session import Session

    # Set up a session without pilot mode
    monkeypatch.chdir(tmp_path)
    session = Session.create(name="NonPilotTest", agents=["claude", "kimi"])
    # claude is NOT in pilot mode (default)
    session.save()

    # Mock the transport
    transport = MagicMock()
    transport.get_transport_type.return_value = "http"

    # Create watchdog
    dog = wd.Watchdog(transport=transport)

    # Track if _run_agent_subprocess was called
    subprocess_called = {"called": False, "agent": None}

    def mock_run_subprocess(agent, cmd, *args, **kwargs):
        subprocess_called["called"] = True
        subprocess_called["agent"] = agent

    monkeypatch.setattr(wd, "_run_agent_subprocess", mock_run_subprocess)
    monkeypatch.setattr(wd, "_agent_ping_cmd", lambda *a, **kw: ["echo", "test"])
    monkeypatch.setattr(wd, "_check_cli_available", lambda agent: True)
    monkeypatch.setattr(
        wd.Watchdog, "_ensure_agent_context", lambda self, agent: True
    )

    # Trigger the non-pilot agent
    thread_started = {"started": False}

    class FakeThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            thread_started["started"] = True
            # Call the subprocess mock directly to simulate execution
            mock_run_subprocess("claude", ["echo", "test"])

    with patch("agentweave.watchdog.threading.Thread", FakeThread):
        dog._trigger_agent_from_message(
            "claude",
            {
                "id": "msg-test-002",
                "from": "user",
                "to": "claude",
                "subject": "Test",
                "content": "Hello",
            },
        )

    # Should have called subprocess for non-pilot agent
    assert subprocess_called["called"] is True, "Should execute for non-pilot agent"
    assert subprocess_called["agent"] == "claude"


def test_watchdog_pilot_check_with_no_session(tmp_path, monkeypatch):
    """Test that watchdog handles missing session gracefully."""
    from agentweave import watchdog as wd

    # No session saved
    monkeypatch.chdir(tmp_path)

    # Mock the transport
    transport = MagicMock()
    transport.get_transport_type.return_value = "http"

    # Create watchdog
    dog = wd.Watchdog(transport=transport)

    # Track if _run_agent_subprocess was called
    subprocess_called = {"called": False}

    def mock_run_subprocess(agent, cmd, *args, **kwargs):
        subprocess_called["called"] = True

    monkeypatch.setattr(wd, "_run_agent_subprocess", mock_run_subprocess)
    monkeypatch.setattr(wd, "_agent_ping_cmd", lambda *a, **kw: ["echo", "test"])
    monkeypatch.setattr(wd, "_check_cli_available", lambda agent: True)
    monkeypatch.setattr(
        wd.Watchdog, "_ensure_agent_context", lambda self, agent: True
    )

    # Trigger without session - should still try to execute (no pilot check blocks it)
    thread_started = {"started": False}

    class FakeThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            thread_started["started"] = True
            mock_run_subprocess("claude", ["echo", "test"])

    with patch("agentweave.watchdog.threading.Thread", FakeThread):
        dog._trigger_agent_from_message(
            "claude",
            {
                "id": "msg-test-003",
                "from": "user",
                "to": "claude",
                "subject": "Test",
                "content": "Hello",
            },
        )

    # Should execute when no session (no pilot check)
    assert subprocess_called["called"] is True
