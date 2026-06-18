"""Tests for agentweave.logging_handlers.

Covers the two custom logging handlers and the one-shot _configure_logging
helper that wires them up. These handlers were untested before PR 12 and
form the spine of the structured-events pipeline (JSONL file + Hub
forwarding), so a small regression here would break every AgentWeave
process that emits an event.

  JSONRotatingFileHandler — writes {ts, event, severity, ...} per line;
                            rotates at 10 MB; WARNING normalizes to "warn".
  HubHandler              — forwards INFO/WARNING/ERROR to Hub transport;
                            never raises; drops DEBUG.
  _configure_logging      — idempotent setup honoring AW_LOG_LEVEL /
                            AW_LOG_FILE env vars.
"""

import json
import logging
import logging.handlers

import pytest

from agentweave import logging_handlers
from agentweave.constants import LOGS_DIR


# ---------------------------------------------------------------------------
# JSONRotatingFileHandler
# ---------------------------------------------------------------------------


def _make_record(level=logging.INFO, msg="hello", event="evt", data=None):
    """Build a LogRecord carrying the structured-event extras."""
    record = logging.LogRecord(
        name="agentweave",
        level=level,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    record.event = event
    if data is not None:
        record.data = data
    return record


def test_json_handler_writes_one_json_object_per_line(tmp_path, monkeypatch):
    """emit() must write exactly one valid JSON object per line."""
    monkeypatch.chdir(tmp_path)
    log_path = tmp_path / "events.jsonl"
    handler = logging_handlers.JSONRotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    try:
        handler.emit(_make_record(level=logging.INFO, msg="ignored", event="msg_sent"))
        handler.emit(_make_record(level=logging.INFO, msg="ignored", event="ping"))
    finally:
        handler.close()

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2, f"expected 2 lines, got {len(lines)}"
    for line in lines:
        entry = json.loads(line)
        assert "ts" in entry
        assert entry["event"] in ("msg_sent", "ping")
        assert entry["severity"] in ("info", "warn", "error", "debug")


def test_json_handler_normalizes_warning_to_warn(tmp_path):
    """WARNING level must serialize as severity='warn' (matches legacy schema)."""
    log_path = tmp_path / "events.jsonl"
    handler = logging_handlers.JSONRotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    try:
        handler.emit(_make_record(level=logging.WARNING, msg="warned", event="watch"))
    finally:
        handler.close()

    line = log_path.read_text(encoding="utf-8").splitlines()[0]
    entry = json.loads(line)
    assert entry["severity"] == "warn", f"expected 'warn', got {entry['severity']!r}"


def test_json_handler_merges_data_extras_into_entry(tmp_path):
    """Extras passed via record.data must appear as top-level keys."""
    log_path = tmp_path / "events.jsonl"
    handler = logging_handlers.JSONRotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    try:
        handler.emit(
            _make_record(
                level=logging.INFO,
                msg="sent",
                event="msg_sent",
                data={"agent": "claude", "msg_id": "m-1"},
            )
        )
    finally:
        handler.close()

    entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert entry.get("agent") == "claude"
    assert entry.get("msg_id") == "m-1"


# ---------------------------------------------------------------------------
# HubHandler
# ---------------------------------------------------------------------------


def _make_hub_handler(monkeypatch, transport_obj):
    """Build a HubHandler whose get_transport() returns the given object."""
    monkeypatch.setattr("agentweave.transport.get_transport", lambda: transport_obj)
    return logging_handlers.HubHandler()


def test_hub_handler_drops_debug_records(monkeypatch):
    """DEBUG records must NOT be forwarded to the Hub (only INFO+)."""
    transport = type("T", (), {"push_log": lambda *a, **k: None})()
    handler = _make_hub_handler(monkeypatch, transport)
    calls = []
    monkeypatch.setattr(transport, "push_log", lambda *a, **k: calls.append((a, k)))
    handler.emit(_make_record(level=logging.DEBUG, msg="dbg", event="low"))
    assert calls == [], f"DEBUG must not be forwarded, got {calls!r}"


def test_hub_handler_forwards_info_to_transport(monkeypatch):
    """INFO records must call transport.push_log exactly once with the
    event name, agent (from data), data dict, and severity."""
    transport = type("T", (), {"push_log": lambda *a, **k: None})()
    calls = []
    monkeypatch.setattr(transport, "push_log", lambda *a, **k: calls.append((a, k)))
    handler = _make_hub_handler(monkeypatch, transport)
    handler.emit(
        _make_record(
            level=logging.INFO,
            msg="sent",
            event="msg_sent",
            data={"agent": "kimi", "msg_id": "m-9"},
        )
    )
    assert len(calls) == 1, f"expected 1 push_log call, got {len(calls)}"
    args = calls[0][0]
    assert args[0] == "msg_sent"
    assert args[1] == "kimi"
    assert args[2] == {"agent": "kimi", "msg_id": "m-9"}
    assert args[3] == "info"


def test_hub_handler_swallows_transport_exceptions(monkeypatch):
    """A transport exception must NEVER propagate out of emit() —
    logging failures must not crash the caller."""
    transport = type(
        "T", (), {"push_log": lambda *a, **k: (_ for _ in ()).throw(RuntimeError("hub down"))}
    )()
    handler = _make_hub_handler(monkeypatch, transport)
    # If this raises, the test fails.
    handler.emit(_make_record(level=logging.INFO, msg="x", event="boom"))


# ---------------------------------------------------------------------------
# _configure_logging
# ---------------------------------------------------------------------------


def test_configure_logging_is_idempotent(monkeypatch):
    """A second call to _configure_logging must not add a second set of handlers."""
    # Reset any handlers that may have been installed by a previous test/import.
    root = logging.getLogger("agentweave")
    saved = list(root.handlers)
    root.handlers = []
    try:
        logging_handlers._configure_logging()
        first = list(root.handlers)
        assert first, "_configure_logging must install at least one handler"
        logging_handlers._configure_logging()
        second = list(root.handlers)
        assert len(second) == len(first), (
            f"_configure_logging is not idempotent: "
            f"first={len(first)} handlers, second={len(second)} handlers"
        )
    finally:
        root.handlers = saved


def test_configure_logging_honors_aw_log_level(monkeypatch, tmp_path):
    """AW_LOG_LEVEL=DEBUG must produce a stderr handler at DEBUG level."""
    monkeypatch.setenv("AW_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("AW_LOG_FILE", str(tmp_path / "dev.log"))
    # Reset handlers
    root = logging.getLogger("agentweave")
    saved = list(root.handlers)
    root.handlers = []
    try:
        logging_handlers._configure_logging()
        dev_handlers = [
            h
            for h in root.handlers
            if isinstance(h, (logging.FileHandler, logging.StreamHandler))
            and not isinstance(h, logging_handlers.JSONRotatingFileHandler)
            and not isinstance(h, logging_handlers.HubHandler)
        ]
        assert dev_handlers, "expected at least one stderr/File handler"
        assert dev_handlers[0].level == logging.DEBUG
    finally:
        for h in list(root.handlers):
            try:
                h.close()
            except Exception:
                pass
        root.handlers = saved


def test_configure_logging_creates_logs_dir(tmp_path, monkeypatch):
    """_configure_logging must ensure LOGS_DIR exists (mkdir parents=True)."""
    # LOGS_DIR is `.agentweave/logs`; monkeypatch chdir to tmp_path so the
    # directory is created inside the test sandbox.
    monkeypatch.chdir(tmp_path)
    root = logging.getLogger("agentweave")
    saved = list(root.handlers)
    root.handlers = []
    try:
        logging_handlers._configure_logging()
        assert (LOGS_DIR).exists(), (
            f"LOGS_DIR ({LOGS_DIR}) must be created by _configure_logging"
        )
    finally:
        for h in list(root.handlers):
            try:
                h.close()
            except Exception:
                pass
        root.handlers = saved
