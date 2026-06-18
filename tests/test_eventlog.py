"""Tests for the eventlog heartbeat read/write pair (M3/M4/M6).

Covers the contract that:
- write_heartbeat() produces a UTC-aware ISO timestamp.
- get_heartbeat_age() reads a recent heartbeat and returns a positive
  number of seconds (proves the two sides agree on UTC-aware datetimes
  and don't crash with a naive/aware TypeError).
- get_heartbeat_age() returns None for a missing or malformed file
  without raising.
- The new logger-based write path round-trips through get_events() —
  proves the M3/M4/M6 migration from eventlog.log_event() to the
  standard-logging pipeline is drop-in compatible.

The pre-fix bug: write_heartbeat used datetime.now() (naive local time)
and get_heartbeat_age subtracted a naive timestamp from datetime.now(),
so it happened to work. But the M3 audit ask is to standardize on
UTC-aware everywhere (datetime.now(timezone.utc)) — the fix is safe
only if both sides are updated together and round-trip cleanly.
"""

import logging
from datetime import datetime, timezone

import pytest

from agentweave import eventlog, logging_handlers
from agentweave.constants import EVENTS_LOG_FILE, WATCHDOG_HEARTBEAT_FILE


@pytest.fixture
def heartbeat_path(tmp_path, monkeypatch):
    """Redirect the watchdog heartbeat file to a temp path."""
    p = tmp_path / "watchdog.heartbeat"
    monkeypatch.setattr(eventlog, "WATCHDOG_HEARTBEAT_FILE", p)
    # also patch the constants module reference (eventlog imported it
    # at import time, so monkeypatching the module attr above is enough).
    return p


def test_write_heartbeat_uses_tz_aware_iso(heartbeat_path):
    """write_heartbeat must produce a UTC-aware ISO timestamp with offset."""
    eventlog.write_heartbeat()
    assert heartbeat_path.exists()
    text = heartbeat_path.read_text(encoding="utf-8").strip()
    parsed = datetime.fromisoformat(text)
    assert parsed.tzinfo is not None, (
        f"write_heartbeat produced a naive timestamp: {text!r}"
    )
    # And it should round-trip as UTC (offset of 0)
    assert parsed.utcoffset().total_seconds() == 0, (
        f"write_heartbeat produced non-UTC timestamp: {text!r}"
    )


def test_get_heartbeat_age_returns_positive_float_for_recent_heartbeat(
    heartbeat_path,
):
    """A heartbeat written just now should report a small positive age."""
    eventlog.write_heartbeat()
    age = eventlog.get_heartbeat_age()
    assert age is not None, "get_heartbeat_age returned None for a fresh heartbeat"
    assert isinstance(age, float)
    assert 0.0 <= age < 60.0, f"unexpected heartbeat age: {age!r}"


def test_get_heartbeat_age_returns_none_for_missing_file(heartbeat_path):
    """No heartbeat file at all -> None, not a crash."""
    assert not heartbeat_path.exists()
    assert eventlog.get_heartbeat_age() is None


def test_get_heartbeat_age_returns_none_for_malformed_file(heartbeat_path):
    """A heartbeat file with garbage content -> None, not a crash."""
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.write_text("not-a-timestamp", encoding="utf-8")
    assert eventlog.get_heartbeat_age() is None


def test_logger_write_path_round_trips_through_get_events(tmp_path, monkeypatch):
    """M3/M4/M6 regression guard: an event written via the new
    JSONRotatingFileHandler pipeline must be readable by get_events() with
    the same JSON shape, so the read path stays compatible after the
    migration from log_event() to logger.info(...).
    """
    monkeypatch.chdir(tmp_path)
    # Wire up the JSONRotatingFileHandler so it writes to a tmp path,
    # mirroring what _configure_logging() does in production.
    EVENTS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging_handlers.JSONRotatingFileHandler(
        EVENTS_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=1, encoding="utf-8"
    )
    logger = logging.getLogger("agentweave.test_roundtrip")
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    try:
        logger.info("msg_sent", extra={"event": "msg_sent", "data": {
            "from": "claude", "to": "kimi", "msg_id": "m-1", "subject": "hi"
        }})
        logger.flush() if hasattr(logger, "flush") else None
    finally:
        logger.removeHandler(file_handler)
        file_handler.close()

    # Read back via the legacy read path.
    events = eventlog.get_events()
    assert len(events) == 1
    e = events[0]
    assert e["event"] == "msg_sent"
    assert e.get("from") == "claude"
    assert e.get("to") == "kimi"
    assert e.get("msg_id") == "m-1"
    assert e.get("subject") == "hi"
