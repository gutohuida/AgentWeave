"""Tests for the watchdog's agent-to-agent ping callback."""

from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_ping_callback_and_fire(
    runner: str,
    tmp_path: Path,
    monkeypatch,
    recipient: str = "codex-backend",
):
    """Build a ping callback, fire an agent-to-agent message, and return captured values."""
    from agentweave import watchdog as wd
    from agentweave.session import Session

    monkeypatch.setattr(wd, "_check_cli_available", lambda agent: True)
    monkeypatch.setattr(wd, "_load_agent_session", lambda agent: "saved-thread")

    captured = {}

    def fake_ping_cmd(agent, prompt, session_id=None):
        captured["agent"] = agent
        captured["prompt"] = prompt
        captured["session_id"] = session_id
        return ["echo", "fake"]

    monkeypatch.setattr(wd, "_agent_ping_cmd", fake_ping_cmd)
    monkeypatch.setattr(wd, "_run_agent_subprocess", lambda *a, **kw: None)

    session = Session(
        {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "agents": {recipient: {"runner": runner}, "pm": {"runner": "claude"}},
        }
    )

    transport = MagicMock()
    transport.get_transport_type.return_value = "http"

    with patch("agentweave.watchdog.threading.Thread") as mock_thread:
        monkeypatch.setattr(Session, "load", staticmethod(lambda: session))
        mock_thread.return_value = MagicMock()
        cb = wd._make_ping_callback([recipient, "pm"], transport=transport)
        cb(
            "new_message",
            {
                "from": "pm",
                "to": recipient,
                "subject": "Task handoff",
                "id": "msg-agent-001",
                "content": "Please execute task-123",
            },
        )

    captured["transport"] = transport
    return captured


def test_agent_message_to_codex_uses_message_as_prompt(tmp_path, monkeypatch):
    captured = _make_ping_callback_and_fire(
        runner="codex",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert captured["agent"] == "codex-backend"
    assert captured["session_id"] == "saved-thread"
    assert captured["prompt"] == "\n".join(
        [
            "AgentWeave message",
            "",
            "From: pm",
            "To: codex-backend",
            "Subject: Task handoff",
            "",
            "Message:",
            "Please execute task-123",
        ]
    )
    captured["transport"].archive_message.assert_called_once_with("msg-agent-001")


def test_agent_message_to_non_codex_uses_inbox_prompt(tmp_path, monkeypatch):
    captured = _make_ping_callback_and_fire(
        runner="kimi",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        recipient="kimi-dev",
    )

    assert "Call get_inbox('kimi-dev')" in captured["prompt"]
    captured["transport"].archive_message.assert_not_called()
