"""Which Hub events call the operator, and the one notice each publishes.

Change `windows-notifications-for-what-calls-the-operator` (D1, operator 2026-11-08): these rules
moved here from the page (`hub/ui/src/lib/notify/classify.ts`), so the in-app toast and a Windows
notification are drawn from the same notice and cannot drift apart. `SSEManager.publish` runs
`notice_for` on every event and publishes an `operator_notice` beside it.

The kinds are the brand's notification sounds (brand/sound/README.md): `ask` when an agent needs the
operator (non-blocking questions included -- the page never read `blocking`), `fail` when work
stalled or failed, `done` when something finished, `reply` when an agent finished a turn the
operator started in a conversation. Everything else stays silent.

It also holds the operator's per-kind choice of what reaches Windows (D2): instance-wide, in a small
file beside the Hub's database, so a watcher with no window open can apply it and it survives a
restart.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from .config import settings

logger = logging.getLogger(__name__)

NOTICE_EVENT = "operator_notice"
KINDS = ("ask", "fail", "done", "reply")

#: `loop_ending.QUEUE_DRAINED_REASON`: the one stop that is finished work, not a failure.
QUEUE_DRAINED_REASON = "loop queue is empty"

#: The headline a notice carries for each kind; the sentence saying who and why is its `text`.
TITLES = {
    "ask": "An agent needs you",
    "fail": "Something stalled or failed",
    "done": "Something finished",
    "reply": "An agent replied",
}

TEXT_LIMIT = 140


def _str(d: Dict[str, Any], key: str) -> str:
    v = d.get(key)
    return v if isinstance(v, str) else ""


def _classify(event_type: str, d: Dict[str, Any]) -> Optional[tuple[str, str, str]]:
    """`(kind, text, agent)` for an event that calls the operator, else None."""
    if event_type == "run_completed":
        # Only a turn the operator started: `initiator` is "operator" when the operator's message
        # controlled the turn. Every other completed run is everyday traffic.
        if _str(d, "initiator") != "operator" or not _str(d, "conversation_id"):
            return None
        agent = _str(d, "agent")
        return "reply", f"{agent or 'An agent'} replied", agent
    if event_type == "question_asked":
        agent = _str(d, "from_agent")
        return "ask", f"{agent or 'An agent'} asked you a question", agent
    if event_type == "permission_requested":
        agent, tool = _str(d, "agent"), _str(d, "tool_name")
        suffix = f" for {tool}" if tool else ""
        return "ask", f"{agent or 'An agent'} wants permission{suffix}", agent
    if event_type == "task_checks_finished":
        # The checks a landing waited on have decided: the operator can press Land, or must act.
        task = _str(d, "task_title") or _str(d, "task_id") or "A task"
        if _str(d, "state") == "passed":
            return "done", f"Checks passed for {task}: it can be landed", ""
        return "fail", f"Checks did not pass for {task}", ""
    if event_type == "task_landing_changed":
        # A batch landed the work, sent it back, or waits for the operator; the queue's other moves
        # are everyday traffic.
        task = _str(d, "task_title") or _str(d, "task_id") or "A task"
        state = _str(d, "state")
        if state == "landed":
            return "done", f"{task} landed on main", ""
        if state == "sent_back":
            return "fail", f"{task} was sent back by its landing batch", ""
        if state == "held":
            return "ask", f"{task}'s landing is held", ""
        return None
    if event_type == "stall_recorded":
        reason = _str(d, "reason")
        return "fail", (f"Work stalled: {reason}" if reason else "Work stalled"), ""
    if event_type == "run_failed":
        agent = _str(d, "agent")
        return "fail", f"{agent or 'An agent'}'s run failed", agent
    if event_type == "queue_chain_suspended":
        agent = _str(d, "agent")
        return "fail", f"A message chain to {agent or 'an agent'} was suspended", agent
    if event_type == "main_moved":
        # `hub/hub/main_watch.py`: a move of main the Hub's own integration did not make.
        branch = _str(d, "branch") or "main"
        if d.get("moved_rewrite") is True:
            return "fail", f"The history of {branch} was rewritten outside the Hub", ""
        return "fail", f"{branch} moved outside the Hub", ""
    if event_type == "next_slice_offered":
        # `hub/hub/slice_drafting.py`: a slice is built and its next slice's drafting is offered.
        nxt = d.get("next_slice")
        nxt = nxt if isinstance(nxt, dict) else {}
        title = _str(nxt, "title") or _str(nxt, "key") or "the next slice"
        return "done", f"A slice is built: draft {title}?", ""
    if event_type == "loop_stopped":
        reason = _str(d, "reason")
        if reason == QUEUE_DRAINED_REASON:
            return "done", "A loop finished its queue", ""
        return "fail", (f"A loop stopped: {reason}" if reason else "A loop stopped"), ""
    return None


def notice_for(project_id: str, event_type: str, data: Any) -> Optional[Dict[str, Any]]:
    """The notice an event publishes, or None for an event that calls nobody.

    `{id, kind, project_id, agent, conversation_id, title, text, source_event}`. The id is minted
    here, once per event, and is what both the page and the Windows notifier de-duplicate by.
    """
    if not project_id or not isinstance(data, dict) or event_type == NOTICE_EVENT:
        return None
    found = _classify(event_type, data)
    if found is None:
        return None
    kind, text, agent = found
    if len(text) > TEXT_LIMIT:
        text = f"{text[: TEXT_LIMIT - 1]}…"
    conversation_id = data.get("conversation_id")
    return {
        "id": f"ntc-{uuid.uuid4().hex[:16]}",
        "kind": kind,
        "project_id": project_id,
        "agent": agent or None,
        "conversation_id": (
            conversation_id if isinstance(conversation_id, str) and conversation_id else None
        ),
        "title": TITLES[kind],
        "text": text,
        "source_event": event_type,
    }


# --- the operator's choice of what reaches Windows ----------------------------------------------

#: The operator's defaults (2026-11-08): questions and failures reach Windows, done and reply do not.
DEFAULT_WINDOWS_KINDS: Dict[str, bool] = {"ask": True, "fail": True, "done": False, "reply": False}

WINDOWS_KINDS_FILE = "notify_settings.json"

_lock = threading.Lock()
#: Held in the process when the database has no directory to sit beside (`:memory:`, tests).
_memory_kinds: Optional[Dict[str, bool]] = None


def windows_kinds_path() -> Optional[Path]:
    """The file beside the Hub's database, or None when there is nowhere durable to keep it."""
    url = settings.database_url
    if url.startswith("sqlite"):
        db_path = url.split("///", 1)[-1]
        if not db_path or db_path == ":memory:" or ":memory:" in url:
            return None
        return Path(os.path.dirname(db_path) or ".") / WINDOWS_KINDS_FILE
    return Path("data") / WINDOWS_KINDS_FILE


def _normalise(raw: Any) -> Dict[str, bool]:
    kinds = dict(DEFAULT_WINDOWS_KINDS)
    if isinstance(raw, dict):
        for k in KINDS:
            if isinstance(raw.get(k), bool):
                kinds[k] = raw[k]
    return kinds


def load_windows_kinds() -> Dict[str, bool]:
    """The operator's per-kind Windows choices; the defaults where nothing (readable) was saved."""
    with _lock:
        path = windows_kinds_path()
        if path is None:
            return _normalise(_memory_kinds)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return dict(DEFAULT_WINDOWS_KINDS)
        except (OSError, ValueError):
            logger.warning(
                "Windows notification choices at %s are unreadable; using defaults", path
            )
            return dict(DEFAULT_WINDOWS_KINDS)
        return _normalise(raw)


def save_windows_kinds(kinds: Dict[str, bool]) -> Dict[str, bool]:
    """Keep the choices, written whole through a temporary file so a crash leaves the old ones."""
    global _memory_kinds
    value = _normalise(kinds)
    with _lock:
        path = windows_kinds_path()
        if path is None:
            _memory_kinds = dict(value)
            return value
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(value), encoding="utf-8")
        os.replace(tmp, path)
    return value
