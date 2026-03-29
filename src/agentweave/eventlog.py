"""Structured event log utilities for AgentWeave.

The write path (previously log_event()) has been replaced by Python's standard
logging module with two custom handlers:

    JSONRotatingFileHandler  — writes to .agentweave/logs/events.jsonl
    HubHandler               — forwards to Hub when HTTP transport is active

See src/agentweave/logging_handlers.py for the handlers and _configure_logging().

This module retains the read-path utilities (get_events, format_event) and the
watchdog heartbeat helpers — none of those are affected by the logging migration.
"""

import contextlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from .constants import EVENTS_LOG_FILE, WATCHDOG_HEARTBEAT_FILE


def write_heartbeat() -> None:
    """Write current timestamp to the watchdog heartbeat file."""
    with contextlib.suppress(Exception):
        WATCHDOG_HEARTBEAT_FILE.write_text(
            datetime.now().isoformat(timespec="seconds"), encoding="utf-8"
        )


def get_heartbeat_age() -> Optional[float]:
    """Return seconds since last watchdog heartbeat, or None if no file."""
    try:
        if not WATCHDOG_HEARTBEAT_FILE.exists():
            return None
        ts = WATCHDOG_HEARTBEAT_FILE.read_text(encoding="utf-8").strip()
        last = datetime.fromisoformat(ts)
        return (datetime.now() - last).total_seconds()
    except Exception:
        return None


def get_events(
    n: int = 50,
    event_type: Optional[str] = None,
    agent: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Read last N events, optionally filtered by event type or agent."""
    if not EVENTS_LOG_FILE.exists():
        return []
    events: List[Dict[str, Any]] = []
    try:
        with open(EVENTS_LOG_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                with contextlib.suppress(json.JSONDecodeError):
                    events.append(json.loads(line))
    except OSError:
        return []

    if event_type:
        events = [e for e in events if e.get("event") == event_type]
    if agent:
        events = [
            e
            for e in events
            if agent in (e.get("from"), e.get("to"), e.get("agent"), e.get("assignee"))
        ]

    return events[-n:]


def format_event(entry: Dict[str, Any]) -> str:
    """Format a single event entry as a human-readable line."""
    ts = entry.get("ts", "?")[:19]
    ev = entry.get("event", "?")

    if ev == "msg_sent":
        subj = entry.get("subject") or "(no subject)"
        return (
            f"[{ts}] MSG   {entry.get('from','?')} -> {entry.get('to','?')}"
            f"  SENT    {entry.get('msg_id','?')}  \"{subj}\""
        )
    if ev == "msg_read":
        return (
            f"[{ts}] MSG   {entry.get('agent','?')}"
            f"  READ    {entry.get('msg_id','?')}  from {entry.get('from','?')}"
        )
    if ev == "task_created":
        return (
            f"[{ts}] TASK  {entry.get('assignee') or 'unassigned'}"
            f"  CREATED {entry.get('task_id','?')}  \"{entry.get('title','?')}\""
        )
    if ev == "task_status":
        return (
            f"[{ts}] TASK  {entry.get('agent') or '?'}"
            f"  STATUS  {entry.get('task_id','?')}"
            f"  {entry.get('prev','?')} -> {entry.get('status','?')}"
        )
    if ev == "msg_detected":
        subj = entry.get("subject") or "(no subject)"
        return (
            f"[{ts}] MSG   {entry.get('from','?')} -> {entry.get('to','?')}"
            f"  DETECTED  {entry.get('msg_id','?')}  \"{subj}\""
        )
    if ev == "watchdog_started":
        return f"[{ts}] WATCH STARTED  transport={entry.get('transport','local')}"
    if ev == "watchdog_stopped":
        return f"[{ts}] WATCH STOPPED"
    if ev == "watchdog_ping":
        return f"[{ts}] WATCH PING -> {entry.get('agent','?')}" f"  msg={entry.get('msg_id','?')}"
    if ev == "ping_skipped":
        return (
            f"[{ts}] WATCH PING SKIPPED -> {entry.get('agent','?')}"
            f"  msg={entry.get('msg_id','?')}  reason={entry.get('reason','?')}"
        )
    # Generic fallback
    rest = {k: v for k, v in entry.items() if k not in ("ts", "event")}
    return f"[{ts}] {ev.upper()}  {rest}"
