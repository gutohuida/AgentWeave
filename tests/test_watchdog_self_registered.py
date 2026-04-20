"""Tests for watchdog self-registration guard."""

from unittest.mock import MagicMock, patch


def test_watchdog_skips_self_registered_poll_agent(tmp_path, monkeypatch):
    """Self-registered poll agent should be skipped by the watchdog."""
    from agentweave import watchdog as wd

    monkeypatch.chdir(tmp_path)

    transport = MagicMock()
    transport.get_transport_type.return_value = "http"
    transport.get_agent_registration.return_value = {
        "self_registered": True,
        "contact_mode": "poll",
    }

    dog = wd.Watchdog(transport=transport)

    subprocess_called = {"called": False}

    def mock_run_subprocess(agent, cmd, *args, **kwargs):
        subprocess_called["called"] = True

    monkeypatch.setattr(wd, "_run_agent_subprocess", mock_run_subprocess)
    monkeypatch.setattr(wd, "_agent_ping_cmd", lambda *a, **kw: ["echo", "test"])
    monkeypatch.setattr(wd, "_check_cli_available", lambda agent: True)
    monkeypatch.setattr(wd.Watchdog, "_ensure_agent_context", lambda self, agent: True)

    dog._trigger_agent_from_message(
        "hermes",
        {
            "id": "msg-test-001",
            "from": "user",
            "to": "hermes",
            "subject": "Test",
            "content": "Hello",
        },
    )

    assert subprocess_called["called"] is False, "Should skip self-registered poll agent"


def test_watchdog_does_not_skip_claude_or_kimi(tmp_path, monkeypatch):
    """Configured agents like Claude and Kimi should NOT be skipped."""
    from agentweave import watchdog as wd

    monkeypatch.chdir(tmp_path)

    transport = MagicMock()
    transport.get_transport_type.return_value = "http"
    transport.get_agent_registration.return_value = None  # No self-registration record

    dog = wd.Watchdog(transport=transport)

    subprocess_called = {"called": False, "agent": None}

    def mock_run_subprocess(agent, cmd, *args, **kwargs):
        subprocess_called["called"] = True
        subprocess_called["agent"] = agent

    monkeypatch.setattr(wd, "_run_agent_subprocess", mock_run_subprocess)
    monkeypatch.setattr(wd, "_agent_ping_cmd", lambda *a, **kw: ["echo", "test"])
    monkeypatch.setattr(wd, "_check_cli_available", lambda agent: True)
    monkeypatch.setattr(wd.Watchdog, "_ensure_agent_context", lambda self, agent: True)

    thread_started = {"started": False}

    class FakeThread:
        def __init__(self, target, args, **kwargs):
            self.target = target
            self.args = args

        def start(self):
            thread_started["started"] = True
            mock_run_subprocess(self.args[0], ["echo", "test"])

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

    assert subprocess_called["called"] is True, "Should execute for configured agent claude"
    assert subprocess_called["agent"] == "claude"

    # Reset and test kimi
    subprocess_called["called"] = False
    subprocess_called["agent"] = None

    with patch("agentweave.watchdog.threading.Thread", FakeThread):
        dog._trigger_agent_from_message(
            "kimi",
            {
                "id": "msg-test-003",
                "from": "user",
                "to": "kimi",
                "subject": "Test",
                "content": "Hello",
            },
        )

    assert subprocess_called["called"] is True, "Should execute for configured agent kimi"
    assert subprocess_called["agent"] == "kimi"


def test_watchdog_job_skips_self_registered_poll_agent(tmp_path, monkeypatch):
    """Scheduled jobs should skip self-registered poll agents."""
    from agentweave import watchdog as wd
    from agentweave.jobs import Job

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Job, "validate_cron", staticmethod(lambda cron: None))

    transport = MagicMock()
    transport.get_transport_type.return_value = "http"
    transport.get_agent_registration.return_value = {
        "self_registered": True,
        "contact_mode": "poll",
    }

    dog = wd.Watchdog(transport=transport)

    job = Job.create(name="Test Job", agent="hermes", message="Hello", cron="0 0 * * *")

    monkeypatch.setattr(wd, "_check_cli_available", lambda agent: True)

    result = dog._fire_job(job, trigger="manual")

    assert result is False, "Should skip firing job for self-registered poll agent"
