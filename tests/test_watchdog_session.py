"""Tests for watchdog direct-trigger session continuity and persistence helpers."""

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest


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
    content: str, saved_session: Optional[str], tmp_path: Path, monkeypatch
):
    """Helper: build a direct trigger callback, fire it with the given message content,
    and return the session_id that was passed to _agent_ping_cmd."""
    from agentweave import watchdog as wd

    monkeypatch.setattr(wd, "TRIGGERED_DIRECT_FILE", tmp_path / "triggered_direct.json")
    monkeypatch.setattr(wd, "_load_triggered_ids", lambda max_age_hours=24: set())
    monkeypatch.setattr(wd, "_save_triggered_id", lambda msg_id: None)
    monkeypatch.setattr(wd, "_check_cli_available", lambda agent: True)

    # Patch _load_agent_session to return the given saved_session
    monkeypatch.setattr(wd, "_load_agent_session", lambda agent: saved_session)

    captured = {}

    def fake_ping_cmd(agent, prompt, session_id=None):
        captured["session_id"] = session_id
        return ["echo", "fake"]

    monkeypatch.setattr(wd, "_agent_ping_cmd", fake_ping_cmd)
    monkeypatch.setattr(wd, "_run_agent_subprocess", lambda *a, **kw: None)

    # Minimal mock transport
    transport = MagicMock()
    transport.get_transport_type.return_value = "http"

    # Patch Session.load to return None (no runner config needed)
    with patch("agentweave.watchdog.threading.Thread") as mock_thread:
        mock_thread.return_value = MagicMock()
        cb = wd._make_direct_trigger_callback(transport=transport)
        cb(
            "new_message",
            {
                "from": "user",
                "to": "kimi",
                "subject": "Direct message from Hub",
                "id": "msg-test-001",
                "content": content,
            },
        )

    return captured.get("session_id")


def test_direct_trigger_resumes_explicit_session(tmp_path, monkeypatch):
    session_id = _make_callback_and_fire(
        content="Hello\n\n[Session: sess-abc-123]",
        saved_session="sess-saved-999",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert session_id == "sess-abc-123"


def test_direct_trigger_new_session_marker_creates_new(tmp_path, monkeypatch):
    session_id = _make_callback_and_fire(
        content="Hello\n\n[NewSession]",
        saved_session="sess-saved-999",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert session_id is None


def test_direct_trigger_no_tag_falls_back_to_saved_session(tmp_path, monkeypatch):
    session_id = _make_callback_and_fire(
        content="Hello, no tags here",
        saved_session="sess-saved-999",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert session_id == "sess-saved-999"


def test_direct_trigger_no_tag_no_saved_session_creates_new(tmp_path, monkeypatch):
    session_id = _make_callback_and_fire(
        content="Hello, no tags here",
        saved_session=None,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert session_id is None
