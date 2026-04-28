"""Tests for watchdog direct-trigger session continuity and persistence helpers."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers: _load_triggered_ids / _save_triggered_id
# ---------------------------------------------------------------------------


def test_load_triggered_ids_returns_empty_when_file_missing(tmp_path, monkeypatch):
    from agentweave import watchdog as wd

    monkeypatch.setattr(wd, "TRIGGERED_DIRECT_FILE", tmp_path / "triggered_direct.json")
    result = wd._load_triggered_ids()
    assert result == set()


def test_load_triggered_ids_returns_recent_ids(tmp_path, monkeypatch):
    from agentweave import watchdog as wd

    f = tmp_path / "triggered_direct.json"
    monkeypatch.setattr(wd, "TRIGGERED_DIRECT_FILE", f)

    now = datetime.now(timezone.utc)
    recent_ts = now.isoformat()
    old_ts = (now - timedelta(hours=25)).isoformat()

    f.write_text(json.dumps({"msg-recent": recent_ts, "msg-old": old_ts}))

    result = wd._load_triggered_ids(max_age_hours=24)
    assert "msg-recent" in result
    assert "msg-old" not in result


def test_load_triggered_ids_prunes_old_entries(tmp_path, monkeypatch):
    from agentweave import watchdog as wd

    f = tmp_path / "triggered_direct.json"
    monkeypatch.setattr(wd, "TRIGGERED_DIRECT_FILE", f)

    now = datetime.now(timezone.utc)
    recent_ts = now.isoformat()
    old_ts = (now - timedelta(hours=25)).isoformat()

    f.write_text(json.dumps({"msg-recent": recent_ts, "msg-old": old_ts}))

    wd._load_triggered_ids(max_age_hours=24)

    remaining = json.loads(f.read_text())
    assert "msg-recent" in remaining
    assert "msg-old" not in remaining


def test_save_triggered_id_writes_entry(tmp_path, monkeypatch):
    from agentweave import watchdog as wd

    f = tmp_path / "triggered_direct.json"
    monkeypatch.setattr(wd, "TRIGGERED_DIRECT_FILE", f)

    wd._save_triggered_id("msg-123")

    data = json.loads(f.read_text())
    assert "msg-123" in data
    # Timestamp should be parseable ISO
    datetime.fromisoformat(data["msg-123"])


def test_save_triggered_id_appends_to_existing(tmp_path, monkeypatch):
    from agentweave import watchdog as wd

    f = tmp_path / "triggered_direct.json"
    monkeypatch.setattr(wd, "TRIGGERED_DIRECT_FILE", f)

    now = datetime.now(timezone.utc).isoformat()
    f.write_text(json.dumps({"msg-existing": now}))

    wd._save_triggered_id("msg-new")

    data = json.loads(f.read_text())
    assert "msg-existing" in data
    assert "msg-new" in data


def test_save_triggered_id_suppresses_exceptions(tmp_path, monkeypatch):
    from agentweave import watchdog as wd

    # Point at a path that can't be written (directory instead of file)
    monkeypatch.setattr(wd, "TRIGGERED_DIRECT_FILE", tmp_path)

    # Must not raise
    wd._save_triggered_id("msg-fail")


# ---------------------------------------------------------------------------
# Callback session logic: [Session:], [NewSession], fallback
# ---------------------------------------------------------------------------


def _make_callback_and_fire(
    content: str,
    saved_session: Optional[str],
    tmp_path: Path,
    monkeypatch,
    recipient: str = "kimi",
    runner: str = "kimi",
):
    """Helper: build a direct trigger callback, fire it with the given message content,
    and return the values passed to _agent_ping_cmd."""
    from agentweave import watchdog as wd
    from agentweave.session import Session

    monkeypatch.setattr(wd, "TRIGGERED_DIRECT_FILE", tmp_path / "triggered_direct.json")
    monkeypatch.setattr(wd, "_load_triggered_ids", lambda max_age_hours=24: set())
    monkeypatch.setattr(wd, "_save_triggered_id", lambda msg_id: None)
    monkeypatch.setattr(wd, "_check_cli_available", lambda agent: True)

    # Patch _load_agent_session to return the given saved_session
    monkeypatch.setattr(wd, "_load_agent_session", lambda agent: saved_session)

    captured = {}

    def fake_ping_cmd(agent, prompt, session_id=None):
        captured["agent"] = agent
        captured["prompt"] = prompt
        captured["session_id"] = session_id
        return ["echo", "fake"]

    monkeypatch.setattr(wd, "_agent_ping_cmd", fake_ping_cmd)
    monkeypatch.setattr(wd, "_run_agent_subprocess", lambda *a, **kw: None)

    # Minimal mock transport
    transport = MagicMock()
    transport.get_transport_type.return_value = "http"

    session = Session(
        {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "agents": {recipient: {"runner": runner}},
        }
    )

    with patch("agentweave.watchdog.threading.Thread") as mock_thread:
        monkeypatch.setattr(Session, "load", staticmethod(lambda: session))
        mock_thread.return_value = MagicMock()
        cb = wd._make_direct_trigger_callback(transport=transport)
        cb(
            "new_message",
            {
                "from": "user",
                "to": recipient,
                "subject": "Direct message from Hub",
                "id": "msg-test-001",
                "content": content,
            },
        )

    captured["transport"] = transport
    return captured


def test_direct_trigger_resumes_explicit_session(tmp_path, monkeypatch):
    captured = _make_callback_and_fire(
        content="Hello\n\n[Session: sess-abc-123]",
        saved_session="sess-saved-999",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert captured["session_id"] == "sess-abc-123"


def test_direct_trigger_new_session_marker_creates_new(tmp_path, monkeypatch):
    captured = _make_callback_and_fire(
        content="Hello\n\n[NewSession]",
        saved_session="sess-saved-999",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert captured["session_id"] is None


def test_direct_trigger_no_tag_falls_back_to_saved_session(tmp_path, monkeypatch):
    captured = _make_callback_and_fire(
        content="Hello, no tags here",
        saved_session="sess-saved-999",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert captured["session_id"] == "sess-saved-999"


def test_direct_trigger_no_tag_no_saved_session_creates_new(tmp_path, monkeypatch):
    captured = _make_callback_and_fire(
        content="Hello, no tags here",
        saved_session=None,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert captured["session_id"] is None


def test_direct_trigger_non_codex_mcp_uses_inbox_prompt(tmp_path, monkeypatch):
    captured = _make_callback_and_fire(
        content="Proceed with task-123\n\n[Session: sess-abc-123]",
        saved_session=None,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        recipient="kimi",
        runner="kimi",
    )

    assert "Call get_inbox('kimi')" in captured["prompt"]
    captured["transport"].archive_message.assert_not_called()


def test_direct_trigger_codex_uses_message_as_prompt(tmp_path, monkeypatch):
    captured = _make_callback_and_fire(
        content="Proceed with task-123\n\n[Session: thread-123]",
        saved_session=None,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        recipient="codex-backend",
        runner="codex",
    )

    assert captured["agent"] == "codex-backend"
    assert captured["session_id"] == "thread-123"
    assert captured["prompt"] == "\n".join(
        [
            "AgentWeave direct message",
            "",
            "From: user",
            "To: codex-backend",
            "Subject: Direct message from Hub",
            "",
            "Message:",
            "Proceed with task-123",
        ]
    )
    captured["transport"].archive_message.assert_called_once_with("msg-test-001")


def test_direct_trigger_codex_mcp_uses_message_as_prompt(tmp_path, monkeypatch):
    captured = _make_callback_and_fire(
        content="Proceed with task-123\n\n[Session: thread-123]",
        saved_session=None,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        recipient="codex-backend",
        runner="codex_mcp",
    )

    assert captured["agent"] == "codex-backend"
    assert captured["session_id"] == "thread-123"
    assert captured["prompt"] == "\n".join(
        [
            "AgentWeave direct message",
            "",
            "From: user",
            "To: codex-backend",
            "Subject: Direct message from Hub",
            "",
            "Message:",
            "Proceed with task-123",
        ]
    )
    captured["transport"].archive_message.assert_called_once_with("msg-test-001")


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
