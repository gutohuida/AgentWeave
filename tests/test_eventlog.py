"""Tests for the eventlog heartbeat read/write pair (M3/M4).

Covers the contract that:
- write_heartbeat() produces a UTC-aware ISO timestamp.
- get_heartbeat_age() reads a recent heartbeat and returns a positive
  number of seconds (proves the two sides agree on UTC-aware datetimes
  and don't crash with a naive/aware TypeError).
- get_heartbeat_age() returns None for a missing or malformed file
  without raising.

The pre-fix bug: write_heartbeat used datetime.now() (naive local time)
and get_heartbeat_age subtracted a naive timestamp from datetime.now(),
so it happened to work. But the M3 audit ask is to standardize on
UTC-aware everywhere (datetime.now(timezone.utc)) — the fix is safe
only if both sides are updated together and round-trip cleanly.
"""

from datetime import datetime, timezone

import pytest

from agentweave import eventlog
from agentweave.constants import WATCHDOG_HEARTBEAT_FILE


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
