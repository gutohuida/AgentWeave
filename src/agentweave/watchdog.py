"""Watchdog script for monitoring new messages and tasks."""

import contextlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .constants import (
    AGENT_CONTEXT_DIR,
    AGENTS_DIR,
    COMPACT_DECISION_FILE,
    CONTEXT_USAGE_DIR,
    MESSAGES_PENDING_DIR,
    RUNNER_CONFIGS,
    TASKS_ACTIVE_DIR,
)
from .utils import load_json

logger = logging.getLogger(__name__)


class Watchdog:
    """Monitors .agentweave/ (local) or a remote transport for changes."""

    def __init__(
        self,
        callback: Optional[Callable] = None,
        poll_interval: float = 5.0,
        transport: Any = None,
        retry_after: Optional[float] = None,
        agent: Optional[str] = None,
    ) -> None:
        """Initialize watchdog.

        Args:
            callback: Function to call when changes detected
            poll_interval: How often to check (seconds); overridden by
                           transport.poll_interval for non-local transports
            transport: BaseTransport instance (defaults to get_transport())
        """
        from .transport import get_transport as _get_transport

        self.transport = transport or _get_transport()
        self.callback = callback or self._default_callback

        # For git/http transport, use the transport's configured poll interval
        if self.transport.get_transport_type() != "local":
            self.poll_interval = float(getattr(self.transport, "poll_interval", poll_interval))
        else:
            self.poll_interval = poll_interval

        self.agent = agent
        self.known_messages: Set[str] = set()
        self.known_tasks: Set[str] = set()
        self.known_remote_files: Set[str] = set()  # for git transport
        self.running = False
        self.retry_after = retry_after  # seconds; None = no retry
        self.pinged_at: Dict[str, float] = {}  # msg_id -> unix time of last ping
        self.context_warned: Dict[str, bool] = {}  # agent -> currently in warning state
        self.compact_decision_mtime: float = 0.0  # mtime of last-processed compact_decision.md

    def _default_callback(self, event_type: str, data: dict) -> None:
        """Default callback that prints to stdout."""
        if event_type == "new_message":
            print(f"\n[MSG] New message for {data['to']} from {data['from']}")
            print(f"   Subject: {data.get('subject', '(no subject)')}")
            print(f"   Run: agentweave inbox --agent {data['to']}")
            print()
        elif event_type == "new_task":
            print(f"\n[TASK] New task assigned to {data.get('assignee', 'unknown')}")
            print(f"   Title: {data.get('title', 'Untitled')}")
            print(f"   Run: agentweave task show {data['id']}")
            print()
        elif event_type == "task_completed":
            print(f"\n[OK] Task completed: {data.get('title', 'Untitled')}")
            print("   Ready for review!")
            print()
        elif event_type == "context_warning":
            agent = data.get("agent", "unknown")
            percent = data.get("percent", 0)
            model = data.get("model", "?")
            threshold = data.get("threshold_warning", "?")
            print(
                f"\n[CTX] Context warning: {agent} ({model}) at {percent}% (threshold: {threshold}%)"
            )
            print(f"   Run /aw-checkpoint in {agent}'s session, then choose an action.")
            self._write_compact_decision(data)
            print()
        elif event_type == "compact_decision":
            agent = data.get("agent", "unknown")
            choice = data.get("choice", "unknown")
            print(f"\n[CTX] Compact decision received for {agent}: {choice}")
            self._handle_compact_decision(data)
            print()

    def _scan_messages(self) -> Set[str]:
        """Scan for local message files."""
        messages = set()
        if MESSAGES_PENDING_DIR.exists():
            for msg_file in MESSAGES_PENDING_DIR.glob("*.json"):
                messages.add(msg_file.stem)
        return messages

    def _scan_tasks(self) -> Set[str]:
        """Scan for local task files."""
        tasks = set()
        if TASKS_ACTIVE_DIR.exists():
            for task_file in TASKS_ACTIVE_DIR.glob("*.json"):
                tasks.add(task_file.stem)
        return tasks

    def _get_message_info(self, msg_id: str) -> dict:
        """Get message info from local filesystem."""
        msg_file = MESSAGES_PENDING_DIR / f"{msg_id}.json"
        return load_json(msg_file) or {}

    def _get_task_info(self, task_id: str) -> dict:
        """Get task info from local filesystem."""
        task_file = TASKS_ACTIVE_DIR / f"{task_id}.json"
        return load_json(task_file) or {}

    def start(self) -> None:
        """Start watching."""
        from .eventlog import write_heartbeat

        transport_type = self.transport.get_transport_type()
        print(f"[WATCH] AgentWeave Watchdog started (transport: {transport_type})")
        if transport_type == "local":
            print(f"   Watching: {MESSAGES_PENDING_DIR}")
            print(f"   Watching: {TASKS_ACTIVE_DIR}")
        elif transport_type == "http":
            hub_url = getattr(self.transport, "url", "?")
            agent_label = self.agent or "all agents"
            print(f"   Watching: {hub_url} (polling every {self.poll_interval}s)")
            print(f"   Agent: {agent_label}")
        else:
            remote = getattr(self.transport, "remote", "?")
            branch = getattr(self.transport, "branch", "?")
            print(f"   Watching: {remote}/{branch} (fetching every {self.poll_interval}s)")
        print(f"   Poll interval: {self.poll_interval}s")
        print("   Press Ctrl+C to stop\n")

        logger.info(
            "watchdog_started",
            extra={"event": "watchdog_started", "data": {"transport": transport_type}},
        )
        write_heartbeat()

        # Initial scan
        if transport_type == "local":
            self.known_messages = self._scan_messages()
            self.known_tasks = self._scan_tasks()
        elif transport_type == "http":
            self._init_http_state()
        else:
            self.transport._fetch()  # type: ignore[union-attr]
            self.known_remote_files = set(self.transport.list_remote_filenames())  # type: ignore[union-attr]

        self.running = True

        try:
            while self.running:
                try:
                    self._check_once()
                except Exception as exc:
                    # Log transient errors (e.g. Hub restart / network blip) but keep running
                    print(
                        f"[WARN] Poll error (will retry in {self.poll_interval}s): {exc}",
                        file=sys.stderr,
                    )
                    logger.warning(
                        "watchdog_poll_error",
                        extra={"event": "watchdog_poll_error", "data": {"error": str(exc)}},
                    )
                write_heartbeat()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logger.info("watchdog_stopped", extra={"event": "watchdog_stopped", "data": {}})
            print("\n\n[STOP] Watchdog stopped")

    def _check_once(self) -> None:
        """Check for changes once."""
        transport_type = self.transport.get_transport_type()
        if transport_type == "local":
            self._check_once_local()
        elif transport_type == "http":
            self._check_once_http()
        else:
            self._check_once_remote()

    def _check_once_local(self) -> None:
        """Scan local .agentweave/ filesystem for new files."""
        import time as _t

        current_messages = self._scan_messages()
        new_messages = current_messages - self.known_messages

        for msg_id in new_messages:
            msg_data = self._get_message_info(msg_id)
            logger.info(
                "msg_detected",
                extra={
                    "event": "msg_detected",
                    "data": {
                        "msg_id": msg_id,
                        "to": msg_data.get("to", "?"),
                        "from": msg_data.get("from", "?"),
                        "subject": msg_data.get("subject", ""),
                    },
                },
            )
            self.callback("new_message", msg_data)

        self.known_messages = current_messages

        # Re-ping stale messages (pinged but still unread after retry_after seconds)
        if self.retry_after is not None:
            now = _t.time()
            for msg_id in list(current_messages):
                last_ping = self.pinged_at.get(msg_id)
                if last_ping and (now - last_ping) >= self.retry_after:
                    msg_data = self._get_message_info(msg_id)
                    elapsed_min = int((now - last_ping) / 60)
                    logger.warning(
                        "msg_stale",
                        extra={
                            "event": "msg_stale",
                            "data": {
                                "msg_id": msg_id,
                                "to": msg_data.get("to", "?"),
                                "from": msg_data.get("from", "?"),
                                "subject": msg_data.get("subject", ""),
                                "minutes_unread": elapsed_min,
                            },
                        },
                    )
                    print(
                        f"[STALE] {msg_id} unread for {elapsed_min}m — re-pinging "
                        f"{msg_data.get('to', '?')}"
                    )
                    del self.pinged_at[msg_id]  # reset so retry_after resets
                    self.callback("new_message", msg_data)

        current_tasks = self._scan_tasks()
        new_tasks = current_tasks - self.known_tasks

        for task_id in new_tasks:
            task_data = self._get_task_info(task_id)
            self.callback("new_task", task_data)

        self.known_tasks = current_tasks

        # Context management monitoring
        self._check_context_usage()
        self._check_compact_decision()

    def _check_context_usage(self) -> None:
        """Scan context_usage/ dir; fire context_warning when an agent hits its threshold."""
        if not CONTEXT_USAGE_DIR.exists():
            return
        for usage_file in CONTEXT_USAGE_DIR.glob("*.json"):
            data = load_json(usage_file) or {}
            agent = data.get("agent", usage_file.stem)
            warning = bool(data.get("warning", False))
            if warning and not self.context_warned.get(agent):
                self.context_warned[agent] = True
                logger.info(
                    "context_warning",
                    extra={
                        "event": "context_warning",
                        "data": {
                            "agent": agent,
                            "percent": data.get("percent"),
                            "model": data.get("model"),
                        },
                    },
                )
                self.callback("context_warning", data)
                if self.transport.get_transport_type() == "http":
                    self._post_context_usage_to_hub(agent, data)
            elif not warning and self.context_warned.get(agent):
                # Warning cleared (agent compacted or threshold dropped)
                self.context_warned[agent] = False

    def _check_compact_decision(self) -> None:
        """Detect when user marks [x] in compact_decision.md and notify the agent."""
        if not COMPACT_DECISION_FILE.exists():
            return
        try:
            mtime = COMPACT_DECISION_FILE.stat().st_mtime
        except OSError:
            return
        if mtime <= self.compact_decision_mtime:
            return  # unchanged since last check

        content = COMPACT_DECISION_FILE.read_text(encoding="utf-8")

        # Parse agent name from header: "# Context Decision Required — <agent> — ..."
        agent_match = re.search(r"^# Context Decision Required — (\S+) —", content, re.MULTILINE)
        agent = agent_match.group(1) if agent_match else ""

        if re.search(r"\[x\]\s+\*\*Compact\*\*", content, re.IGNORECASE):
            choice = "compact"
        elif re.search(r"\[x\]\s+\*\*New Session\*\*", content, re.IGNORECASE):
            choice = "new_session"
        elif re.search(r"\[x\]\s+\*\*Continue\*\*", content, re.IGNORECASE):
            choice = "continue"
        else:
            return  # no choice marked yet

        self.compact_decision_mtime = mtime
        logger.info(
            "compact_decision",
            extra={"event": "compact_decision", "data": {"agent": agent, "choice": choice}},
        )
        self.callback("compact_decision", {"agent": agent, "choice": choice})

    def _write_compact_decision(self, usage_data: dict) -> None:
        """Write compact_decision.md so the user can choose compact/new-session/continue."""
        from datetime import datetime

        agent = usage_data.get("agent", "unknown")
        model = usage_data.get("model", "?")
        percent = usage_data.get("percent", 0)
        threshold = usage_data.get("threshold_warning", "?")
        dt = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        next_threshold = min(int(percent) + 20, 90) if isinstance(percent, int) else 90

        content = (
            f"# Context Decision Required — {agent} — {dt}\n\n"
            f"Agent **{agent}** ({model}) has reached **{percent}%** context utilization.\n"
            f"Recommended action threshold for this model: {threshold}%.\n\n"
            f"Run `/aw-checkpoint` in {agent}'s session first, then choose one action below.\n\n"
            "## Choose one action\n\n"
            "- [ ] **Compact** — agent writes checkpoint, then runs /compact and resumes\n"
            "- [ ] **New Session** — agent writes checkpoint, then you start a fresh session\n"
            f"- [ ] **Continue** — skip this warning; next alert at {next_threshold}%\n\n"
            "Mark one option with [x] and save this file. The watchdog will notify the agent.\n"
        )
        try:
            COMPACT_DECISION_FILE.parent.mkdir(parents=True, exist_ok=True)
            COMPACT_DECISION_FILE.write_text(content, encoding="utf-8")
            print(f"   Decision file: {COMPACT_DECISION_FILE}")
            print("   Edit that file: mark [x] your choice, then save.")
        except OSError as exc:
            print(f"   [WARN] Could not write decision file: {exc}", file=sys.stderr)

    def _handle_compact_decision(self, data: dict) -> None:
        """Send the user's compact decision to the agent's inbox."""
        from .messaging import Message, MessageBus

        agent = data.get("agent", "")
        choice = data.get("choice", "")
        if not agent or not choice:
            return

        if choice == "compact":
            subject = "Context: please compact now"
            content = (
                "**Context decision: Compact**\n\n"
                "1. Run `/aw-checkpoint` if you haven't already.\n"
                "2. Run `/compact` in your session.\n"
                "3. After compacting, re-read your checkpoint file and resume from Next Steps."
            )
        elif choice == "new_session":
            subject = "Context: new session requested"
            content = (
                "**Context decision: New Session**\n\n"
                "1. Run `/aw-checkpoint` if you haven't already.\n"
                "2. Your principal will start a fresh session for you.\n"
                "3. The new session will read your checkpoint as its first action."
            )
        elif choice == "continue":
            subject = "Context: warning dismissed"
            content = (
                "**Context decision: Continue**\n\n"
                "Warning dismissed. You may continue without compacting.\n"
                "Context monitoring will resume at the next threshold."
            )
            # Reset warned state so the next threshold level can trigger
            if agent in self.context_warned:
                self.context_warned[agent] = False
        else:
            return

        msg = Message.create(
            sender="watchdog",
            recipient=agent,
            subject=subject,
            content=content,
            message_type="message",
        )
        ok = MessageBus.send(msg)
        if ok:
            print(f"   Message sent to {agent}: {subject}")
        else:
            print(f"   [WARN] Could not send message to {agent}", file=sys.stderr)

    def _post_context_usage_to_hub(self, agent: str, data: dict) -> None:
        """POST context usage data to the Hub so Mission Control can display it."""
        import json as _json
        import urllib.error as _uerr
        import urllib.request as _req

        from .constants import TRANSPORT_CONFIG_FILE
        from .utils import load_json as _load_json

        config = _load_json(TRANSPORT_CONFIG_FILE)
        if not config:
            return
        url = config["url"].rstrip("/")
        api_key = config.get("api_key", "")
        body = _json.dumps(data).encode()
        request = _req.Request(
            f"{url}/api/v1/agents/{agent}/context-usage", data=body, method="POST"
        )
        request.add_header("Authorization", f"Bearer {api_key}")
        request.add_header("Content-Type", "application/json")
        try:
            with _req.urlopen(request, timeout=5):
                pass
        except (_uerr.HTTPError, _uerr.URLError) as exc:
            print(f"   [WARN] Could not post context usage to Hub: {exc}", file=sys.stderr)

    def _init_http_state(self) -> None:
        """Seed known message/task IDs from Hub so we don't re-fire on startup."""
        messages = self.transport.get_pending_messages(self.agent or "")
        for msg in messages:
            msg_id = msg.get("id", "")
            if msg_id:
                self.known_messages.add(msg_id)
        tasks = self.transport.get_active_tasks(self.agent or None)
        for task in tasks:
            task_id = task.get("id", "")
            if task_id:
                self.known_tasks.add(task_id)

    def _check_once_http(self) -> None:
        """Poll Hub REST API for new messages and tasks."""
        # Context files are always local, even when using HTTP transport
        self._check_context_usage()

        messages = self.transport.get_pending_messages(self.agent or "")
        for msg in messages:
            msg_id = msg.get("id", "")
            if msg_id and msg_id not in self.known_messages:
                self.known_messages.add(msg_id)
                self.callback("new_message", msg)

        tasks = self.transport.get_active_tasks(self.agent or None)
        for task in tasks:
            task_id = task.get("id", "")
            if task_id and task_id not in self.known_tasks:
                self.known_tasks.add(task_id)
                self.callback("new_task", task)

    def _check_once_remote(self) -> None:
        """Scan remote transport for new files without consuming messages.

        The watchdog only notifies — it does NOT add message IDs to the seen
        set. Archiving happens via `agentweave msg read` or `agentweave inbox`.
        This means the same message appears in both watchdog notifications AND
        the inbox command until explicitly archived.
        """
        self.transport._fetch()  # type: ignore[union-attr]
        current_files = set(self.transport.list_remote_filenames())  # type: ignore[union-attr]
        new_files = current_files - self.known_remote_files

        for fname in new_files:
            data = self.transport.read_remote_file(fname)  # type: ignore[union-attr]
            if data is None:
                continue
            if "-task-for-" in fname:
                self.callback("new_task", data)
            else:
                self.callback("new_message", data)

        self.known_remote_files = current_files

    def stop(self) -> None:
        """Stop watching."""
        self.running = False


class _KimiParser:
    """
    State-machine parser for kimi --print streaming output.

    Kimi emits Python-repr-style events, one per multi-line block ending with ')'.
    This accumulates lines, detects event boundaries, and emits human-readable strings.

    Example input (kimi raw lines):
        ThinkPart(
            type='think',
            think='I need to check my inbox.',
            encrypted=None
        )
    Example output:
        ['  \u1f4ad I need to check my inbox.']
    """

    _EVENT_RE = re.compile(r"^([A-Z][A-Za-z]+)\(")
    # Events we parse and render
    _RENDER = frozenset({"TurnBegin", "StepBegin", "ThinkPart", "TextPart", "ToolCall", "ToolResult"})

    def __init__(self) -> None:
        self._buf: List[str] = []
        self._cur: str = ""  # current event name
        self._skip: bool = False  # True when we don't want this event's output
        self._pending: Dict[str, str] = {}  # tool_call_id -> tool_name
        self._partial_id: str = ""  # call_id waiting for ToolCallPart
        self._partial_name: str = ""  # tool_name waiting for ToolCallPart
        self._partial_args: str = ""  # accumulated partial JSON args

    def feed(self, line: str) -> List[str]:
        """Feed one raw output line; returns list of display strings (may be empty)."""
        stripped = line.strip()
        if not stripped:
            return []

        if not self._buf:
            m = self._EVENT_RE.match(stripped)
            if not m:
                return []
            name = m.group(1)
            self._cur = name
            self._skip = name not in self._RENDER
            self._buf = [stripped]
            # Single-line event: parens balance on this one line
            if stripped.count("(") == stripped.count(")"):
                return self._flush()
            return []
        else:
            self._buf.append(stripped)
            # Closing paren on its own line ends the current outer event
            if stripped == ")":
                return self._flush()
            return []

    def _flush(self) -> List[str]:
        block = "\n".join(self._buf)
        name = self._cur
        self._buf = []
        self._cur = ""

        if self._skip:
            self._skip = False
            # ToolCallPart carries the rest of a split arguments string
            if name == "ToolCallPart":
                m = re.search(r"arguments_part='(.*?)'(?:\s*\))?$", block, re.DOTALL)
                if m and self._partial_id:
                    self._partial_args += m.group(1)
                    try:
                        args = json.loads(self._partial_args)
                        result = [self._fmt_tool(self._partial_name, args)]
                        self._partial_id = self._partial_name = self._partial_args = ""
                        return result
                    except Exception:
                        pass  # still incomplete; wait for more ToolCallPart
            return []

        self._skip = False
        return self._render(name, block)

    def _render(self, name: str, block: str) -> List[str]:
        if name == "TurnBegin":
            m = re.search(r'user_input=["\'](.+?)["\']', block, re.DOTALL)
            text = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
            if len(text) > 120:
                text = text[:120] + "\u2026"
            sep = "\u2500" * 56
            return [sep, f"\U0001f4e8  {text}", sep]

        if name == "StepBegin":
            m = re.search(r"n=(\d+)", block)
            n = m.group(1) if m else "?"
            return [f"  \u2500\u2500 Step {n} " + "\u2500" * 46]

        if name == "ThinkPart":
            m = re.search(r"think='(.*?)',\s*encrypted", block, re.DOTALL)
            if not m:
                m = re.search(r'think="(.*?)",\s*encrypted', block, re.DOTALL)
            if m:
                thinking = re.sub(r"\s+", " ", m.group(1).replace("\\n", " ")).strip()
                if len(thinking) > 200:
                    thinking = thinking[:200] + "\u2026"
                return [f"  \U0001f4ad {thinking}"]
            return []

        if name == "TextPart":
            m = re.search(r"text='(.*?)'(?:[,)\s]|$)", block, re.DOTALL)
            if not m:
                m = re.search(r'text="(.*?)"(?:[,)\s]|$)', block, re.DOTALL)
            if m:
                text = m.group(1).replace("\\n", "\n").strip()
                if text:
                    return [f"  \U0001f4ac {text}"]
            return []

        if name == "ToolCall":
            id_m = re.search(r"id='([^']+)'", block)
            name_m = re.search(r"name='([^']+)'", block)
            args_m = re.search(r"arguments='(.*?)'(?:\s*\)|\s*,)", block, re.DOTALL)
            call_id = id_m.group(1) if id_m else ""
            tool_name = name_m.group(1) if name_m else "unknown"
            raw_args = args_m.group(1) if args_m else ""
            self._pending[call_id] = tool_name
            try:
                args = json.loads(raw_args)
                return [self._fmt_tool(tool_name, args)]
            except Exception:
                # Incomplete JSON — wait for ToolCallPart to complete it
                self._partial_id = call_id
                self._partial_name = tool_name
                self._partial_args = raw_args
                return []

        if name == "ToolResult":
            id_m = re.search(r"tool_call_id='([^']+)'", block)
            call_id = id_m.group(1) if id_m else ""
            self._pending.pop(call_id, "")

            is_error = "is_error=True" in block
            if is_error:
                err_m = re.search(r"text='([^']+)'", block)
                err = err_m.group(1)[:100] if err_m else "unknown error"
                return [f"     \u2717 {err}"]

            msg_m = re.search(r"message='([^']+)'", block)
            if msg_m and msg_m.group(1).strip():
                return [f"     \u2713 {msg_m.group(1).strip()[:100]}"]

            return ["     \u2713 ok"]

        return []

    @staticmethod
    def _fmt_tool(tool_name: str, args: dict) -> str:
        skip_keys = {"content", "body", "text", "new_text", "old_text"}
        display = {k: v for k, v in args.items() if k not in skip_keys}
        parts = []
        for k, v in list(display.items())[:4]:
            v_str = str(v)
            if len(v_str) > 60:
                v_str = v_str[:60] + "\u2026"
            parts.append(f'{k}="{v_str}"')
        return f"  \U0001f527 {tool_name}({', '.join(parts)})"


def _get_runner_type(agent: str) -> str:
    """Return the runner type for an agent, loading from session config."""
    from .constants import AGENT_RUNNER_DEFAULTS
    from .session import Session

    session = Session.load()
    if session:
        return session.get_runner_config(agent).get("runner", "native")
    return AGENT_RUNNER_DEFAULTS.get(agent, "native")


def _agent_ping_cmd(agent: str, prompt: str, session_id: Optional[str] = None) -> list:
    """Return the CLI command to ping an agent with a prompt.

    Dispatches based on runner type from session config, not agent name.
    Kimi uses --print (plain Python-repr events) with --session for resumption.
    Claude/claude_proxy use --output-format stream-json --verbose with --resume.
    """
    from .session import Session

    runner_type = _get_runner_type(agent)
    rc = RUNNER_CONFIGS.get(runner_type, RUNNER_CONFIGS["native"])

    if runner_type == "kimi":
        cmd = ["kimi", "--print"]
        # Inject per-agent context file if it exists
        context_file = AGENT_CONTEXT_DIR / f"{agent}.md"
        if context_file.exists():
            cmd += ["--agent-file", str(context_file)]
        if session_id:
            cmd += ["--session", session_id]
        cmd += ["-p", prompt]
        return cmd

    # claude, claude_proxy, native — all use stream-json JSONL output
    cli = rc.get("cli") or agent  # native: use agent name as CLI
    model = None
    session = Session.load()
    if session:
        runner_config = session.get_runner_config(agent)
        model = runner_config.get("model")

    cmd = [cli, "--output-format", "stream-json", "--verbose"]
    if model:
        cmd += ["--model", model]
    # Inject per-agent context file for claude/claude_proxy if it exists
    if runner_type in ("claude", "claude_proxy", "native"):
        context_file = AGENT_CONTEXT_DIR / f"{agent}.md"
        if context_file.exists():
            cmd += ["--append-system-prompt-file", str(context_file)]
    if session_id:
        cmd += ["--resume", session_id]
    cmd += ["-p", prompt]
    return cmd


def _load_agent_session(agent: str) -> Optional[str]:
    """Load saved session ID for an agent from .agentweave/agents/<agent>-session.json."""
    session_file = AGENTS_DIR / f"{agent}-session.json"
    if not session_file.exists():
        return None
    try:
        data = json.loads(session_file.read_text())
        return data.get("session_id")
    except Exception:
        return None


def _save_agent_session(agent: str, session_id: str) -> None:
    """Persist session ID for an agent to .agentweave/agents/<agent>-session.json."""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    session_file = AGENTS_DIR / f"{agent}-session.json"
    session_file.write_text(json.dumps({"session_id": session_id}))


def _extract_claude_session_id(line: str) -> Optional[str]:
    """Parse a JSONL line from claude --output-format stream-json, return session_id if present."""
    try:
        data = json.loads(line)
        return data.get("session_id") or None
    except Exception:
        return None


def _parse_claude_stream_line(line: str) -> list:
    """Parse one JSONL line from `claude --output-format stream-json`.

    Returns a list of human-readable strings to post as agent output.
    Empty list means the line carries no user-visible content.
    """
    try:
        data = json.loads(line)
    except Exception:
        # Non-JSON line — pass through as-is if non-empty
        stripped = line.strip()
        return [stripped] if stripped else []

    msg_type = data.get("type", "")

    if msg_type == "assistant":
        message = data.get("message", {})
        # Some CLI versions nest content under "message", others put it at the top level
        content = message.get("content", data.get("content", []))
        if isinstance(content, str):
            return [content] if content.strip() else []
        results = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type == "thinking":
                thinking = block.get("thinking", "").strip()
                if thinking:
                    # Prefix each line so it's visually distinct in the log
                    prefixed = "\n".join(f"💭 {line}" for line in thinking.splitlines())
                    results.append(prefixed)
            elif block_type == "text":
                text = block.get("text", "").strip()
                if text:
                    results.append(text)
        return results

    if msg_type == "tool_use":
        name = data.get("name", "unknown")
        inp = data.get("input", {})
        try:
            inp_str = json.dumps(inp, ensure_ascii=False)
            if len(inp_str) > 300:
                inp_str = inp_str[:300] + "…"
        except Exception:
            inp_str = str(inp)
        return [f"🔧 {name}({inp_str})"]

    if msg_type == "tool_result":
        content = data.get("content", [])
        if isinstance(content, str):
            stripped = content.strip()
            return [f"  → {stripped[:500]}"] if stripped else []
        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    t = block.get("text", "").strip()
                    if t:
                        snippet = t[:500] + ("…" if len(t) > 500 else "")
                        texts.append(f"  → {snippet}")
            return texts
        return []

    if msg_type == "result":
        subtype = data.get("subtype", "")
        if subtype == "error":
            return [f"[ERROR] {data.get('error', 'unknown error')}"]
        # result_text duplicates the already-streamed assistant messages — skip it
        cost = data.get("total_cost_usd")
        return [f"[done] cost: ${cost:.4f}"] if cost is not None else []

    # system/init and everything else — ignore
    return []


_KIMI_RESUME_RE = re.compile(r"kimi -r ([a-f0-9\-]{36})")


def _extract_kimi_session_from_stdout(stdout_lines: List[str]) -> Optional[str]:
    """Extract Kimi session ID from stdout.

    Kimi prints: "To resume this session: kimi -r <UUID>" as the last line.
    """
    for line in reversed(stdout_lines):
        m = _KIMI_RESUME_RE.search(line)
        if m:
            return m.group(1)
    return None


def _run_agent_subprocess(
    agent: str,
    cmd: list,
    subject: str,
    transport: Any,
    is_http: bool,
    env_vars: Optional[Dict[str, str]] = None,
) -> None:
    """Background thread: run agent, stream output to Hub, save session ID."""
    runner_type = _get_runner_type(agent)
    is_kimi = runner_type == "kimi"

    # Send "running" heartbeat + diagnostic start marker
    if is_http:
        try:
            transport.push_heartbeat(agent, status="running", message=f"Responding to: {subject}")
        except Exception as exc:
            logger.warning(
                "watchdog_heartbeat_failed",
                extra={
                    "event": "watchdog_heartbeat_failed",
                    "data": {"agent": agent, "error": str(exc)},
                },
            )
        try:
            transport.post_agent_output(agent, f"[watchdog] 🚀 Starting {agent}…", session_id=None)
        except Exception as exc:
            print(f"[ERROR] Could not post start marker to Hub: {exc}", file=sys.stderr)

    session_id: Optional[str] = None
    # Mutable container so the stderr thread can read the latest session_id
    session_id_ref: List[Optional[str]] = [None]
    # Collect all stdout lines for Kimi session ID extraction
    kimi_stdout_lines: List[str] = []
    kimi_parser = _KimiParser() if is_kimi else None

    def _drain_stderr(proc: subprocess.Popen) -> None:
        """Read stderr in a background thread and post each line as agent output
        and as a log event so it appears in the Hub Logs tab."""
        _error_keywords = ("Error", "Traceback", "Exception", "FAILED", "fatal")
        try:
            for raw in proc.stderr:  # type: ignore[union-attr]
                err_line = raw.rstrip("\n")
                if not err_line.strip():
                    continue
                # For Kimi: capture session ID from stderr resume line in real-time
                if is_kimi and session_id_ref[0] is None:
                    m = _KIMI_RESUME_RE.search(err_line)
                    if m:
                        session_id_ref[0] = m.group(1)
                msg = f"[stderr] {err_line}"
                if is_http:
                    try:
                        transport.post_agent_output(agent, msg, session_id=session_id_ref[0])
                    except Exception as exc:
                        logger.warning(
                            "watchdog_output_post_failed",
                            extra={
                                "event": "watchdog_output_post_failed",
                                "data": {"agent": agent, "error": str(exc)},
                            },
                        )
                    # Only push error-level lines to the Logs tab
                    if any(kw in err_line for kw in _error_keywords):
                        transport.push_log("agent_stderr", agent, {"line": err_line}, "error")
                else:
                    print(f"[{agent}:err] {err_line}", file=sys.stderr)
        except Exception as exc:
            logger.warning(
                "watchdog_stderr_drain_failed",
                extra={
                    "event": "watchdog_stderr_drain_failed",
                    "data": {"agent": agent, "error": str(exc)},
                },
            )

    def _run_cmd(run_cmd: list, run_session_id: Optional[str]) -> int:
        """Run agent command, stream output. Returns process returncode."""
        nonlocal session_id, session_id_ref

        # Prepare environment: merge env_vars with current environment
        proc_env = None
        if env_vars:
            proc_env = os.environ.copy()
            proc_env.update(env_vars)
            # If ANTHROPIC_API_KEY_VAR is set, resolve it and set ANTHROPIC_API_KEY.
            # (Claude CLI needs ANTHROPIC_API_KEY, not ANTHROPIC_API_KEY_VAR)
            # Always overwrite ANTHROPIC_API_KEY so the parent shell's Claude key
            # is never accidentally forwarded to a proxy provider.
            api_key_var = env_vars.get("ANTHROPIC_API_KEY_VAR")
            if api_key_var:
                resolved = os.environ.get(api_key_var, "")
                if resolved:
                    proc_env["ANTHROPIC_API_KEY"] = resolved
                else:
                    # Key var declared but not exported — clear inherited Claude key
                    # so the failure is an explicit 401 rather than a silent wrong-key error.
                    proc_env.pop("ANTHROPIC_API_KEY", None)
                    print(
                        f"[WARN] {api_key_var} is not set in the environment. "
                        f"Export it before starting the watchdog.",
                        file=sys.stderr,
                    )

        proc = subprocess.Popen(
            run_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=proc_env,
        )
        stderr_thread = threading.Thread(target=_drain_stderr, args=(proc,), daemon=True)
        stderr_thread.start()

        output_line_count = 0
        for raw_line in proc.stdout:  # type: ignore[union-attr]
            line = raw_line.rstrip("\n")

            if is_kimi:
                # Collect all lines for post-exit session ID extraction
                kimi_stdout_lines.append(line)
                # Extract session ID in real-time if seen on stdout
                if session_id is None:
                    m = _KIMI_RESUME_RE.search(line)
                    if m:
                        session_id = m.group(1)
                        session_id_ref[0] = session_id
                # Parse Kimi's Python-repr events streamed in real-time
                readable_lines = kimi_parser.feed(line) if kimi_parser is not None else []
            else:
                # Try to extract session_id from JSONL stream (Claude/claude_proxy)
                if session_id is None:
                    extracted = _extract_claude_session_id(line)
                    if extracted:
                        session_id = extracted
                        session_id_ref[0] = session_id
                readable_lines = _parse_claude_stream_line(line)

            # Stream to Hub or local stdout
            if is_http:
                for readable in readable_lines:
                    output_line_count += 1
                    try:
                        ok = transport.post_agent_output(
                            agent, readable, session_id=session_id_ref[0]
                        )
                        if not ok:
                            print(
                                f"[WARN] post_agent_output returned False for {agent}",
                                file=sys.stderr,
                            )
                    except Exception as exc:
                        logger.warning(
                            "watchdog_output_post_failed",
                            extra={
                                "event": "watchdog_output_post_failed",
                                "data": {"agent": agent, "error": str(exc)},
                            },
                        )
                        print(
                            f"[ERROR] post_agent_output failed for {agent}: {exc}",
                            file=sys.stderr,
                        )
            else:
                for readable in readable_lines:
                    output_line_count += 1
                    print(f"[{agent}] {readable}")

        proc.wait()
        stderr_thread.join(timeout=5)

        # Post a completion summary so we can confirm the pipeline is alive
        summary = f"[watchdog] ✅ {agent} done — {output_line_count} output line(s)"
        print(summary, file=sys.stderr)
        if is_http:
            with contextlib.suppress(Exception):
                transport.post_agent_output(agent, summary, session_id=session_id_ref[0])

        return proc.returncode or 0

    try:
        returncode = _run_cmd(cmd, session_id)

        # If the process failed and we used a session ID, the session may be
        # expired. Clear it and retry once without --resume/--session.
        saved_session = _load_agent_session(agent)
        if returncode != 0 and saved_session:
            logger.warning(
                "watchdog_session_retry",
                extra={
                    "event": "watchdog_session_retry",
                    "data": {
                        "agent": agent,
                        "exit_code": returncode,
                        "reason": "stale session cleared",
                    },
                },
            )
            print(
                f"[WARN] {agent} exited with code {returncode} — session may be stale, "
                f"clearing and retrying without session ID",
                file=sys.stderr,
            )
            # Clear the stale session file
            session_file = AGENTS_DIR / f"{agent}-session.json"
            with contextlib.suppress(Exception):
                session_file.unlink(missing_ok=True)
            session_id = None
            session_id_ref[0] = None
            kimi_stdout_lines.clear()
            retry_cmd = _agent_ping_cmd(agent, cmd[-1], session_id=None)  # cmd[-1] is the prompt
            returncode = _run_cmd(retry_cmd, None)

        if returncode != 0:
            logger.warning(
                "watchdog_agent_exit",
                extra={
                    "event": "watchdog_agent_exit",
                    "data": {"agent": agent, "exit_code": returncode},
                },
            )
            print(f"[WARN] {agent} exited with code {returncode}", file=sys.stderr)
    except FileNotFoundError as exc:
        logger.error(
            "watchdog_spawn_failed",
            extra={"event": "watchdog_spawn_failed", "data": {"agent": agent, "error": str(exc)}},
        )
        print(f"[ERROR] Failed to launch {agent}: {exc}", file=sys.stderr)
    except Exception as exc:
        logger.error(
            "watchdog_subprocess_error",
            extra={
                "event": "watchdog_subprocess_error",
                "data": {"agent": agent, "error": str(exc)},
            },
        )
        print(f"[ERROR] Unexpected error running {agent}: {exc}", file=sys.stderr)

    # Extract Kimi session ID from collected stdout lines (post-exit)
    if is_kimi and session_id is None and kimi_stdout_lines:
        found = _extract_kimi_session_from_stdout(kimi_stdout_lines)
        if found:
            session_id = found
            session_id_ref[0] = found
            logger.info(
                "watchdog_kimi_session_found",
                extra={
                    "event": "watchdog_kimi_session_found",
                    "data": {"session_id": found, "method": "stdout_resume_line"},
                },
            )

    # Persist session ID for next run
    if session_id:
        with contextlib.suppress(Exception):
            _save_agent_session(agent, session_id)
        # For Kimi, post a synthetic output line so the Hub/UI learns the session ID.
        if is_kimi and is_http:
            with contextlib.suppress(Exception):
                transport.post_agent_output(
                    agent, f"[session: {session_id}]", session_id=session_id
                )

    # Send "idle" heartbeat
    if is_http:
        try:
            transport.push_heartbeat(agent, status="idle")
        except Exception as exc:
            logger.warning(
                "watchdog_heartbeat_failed",
                extra={
                    "event": "watchdog_heartbeat_failed",
                    "data": {"agent": agent, "error": str(exc)},
                },
            )


def _check_cli_available(agent: str) -> bool:
    """Check if an agent's CLI is available in PATH."""
    import shutil

    runner_type = _get_runner_type(agent)
    rc = RUNNER_CONFIGS.get(runner_type, RUNNER_CONFIGS["native"])
    cli = rc.get("cli") or agent  # native: use agent name as CLI
    return shutil.which(cli) is not None


def _make_ping_callback(
    agents: List[str],
    pinged_at: Optional[Dict[str, float]] = None,
    transport: Any = None,
) -> Callable:
    """Return a callback that pings each agent's CLI when a message addressed to them arrives.

    Handles any number of agents. Non-blocking (spawns a daemon thread per ping).
    Uses session persistence to resume the same agent session across pings.
    A seen-set prevents double-pings for the same message ID.
    """
    agent_set = set(agents)
    seen: Set[str] = set()
    is_http = transport is not None and transport.get_transport_type() == "http"

    # Validate CLIs at startup and warn about missing ones
    for agent in agents:
        if not _check_cli_available(agent):
            print(
                f"[WARN] {agent} CLI not found in PATH. " f"Auto-ping for {agent} will not work.",
                file=sys.stderr,
            )

    def callback(event_type: str, data: Dict[str, Any]) -> None:
        if event_type != "new_message":
            return
        recipient = data.get("to", "")
        if recipient not in agent_set:
            return
        # Direct trigger messages (from Hub UI) are handled by _make_direct_trigger_callback
        # which also uses get_inbox flow.  Skip here to avoid launching a second process.
        if data.get("from", "") == "user":
            return
        msg_id = data.get("id", "")
        if msg_id in seen:
            return
        seen.add(msg_id)

        # Skip if CLI is not available
        if not _check_cli_available(recipient):
            print(
                f"[SKIP] Cannot notify {recipient}: CLI not found in PATH",
                file=sys.stderr,
            )
            logger.warning(
                "ping_skipped",
                extra={
                    "event": "ping_skipped",
                    "data": {
                        "agent": recipient,
                        "msg_id": msg_id,
                        "reason": "CLI not found in PATH",
                    },
                },
            )
            return

        prompt = (
            f"You have a new AgentWeave message from {data.get('from', 'another agent')}. "
            f"Call get_inbox('{recipient}') to retrieve it and respond."
        )
        session_id = _load_agent_session(recipient)
        cmd = _agent_ping_cmd(recipient, prompt, session_id=session_id)
        subject = data.get("subject", "(no subject)")
        print(f"[PING] Notifying {recipient}: {subject}")
        print(f"[PING] Command: {' '.join(cmd)}")
        if session_id:
            print(f"[PING] Resuming session: {session_id}")

        # Load env_vars from session config for claude_proxy agents
        env_vars = None
        from .session import Session

        session = Session.load()
        if session:
            runner_config = session.get_runner_config(recipient)
            if runner_config.get("runner") == "claude_proxy" and runner_config.get("env_vars"):
                env_vars = runner_config.get("env_vars")

        import time as _t

        if pinged_at is not None:
            pinged_at[msg_id] = _t.time()
        logger.info(
            "watchdog_ping",
            extra={
                "event": "watchdog_ping",
                "data": {"agent": recipient, "msg_id": msg_id, "subject": data.get("subject", "")},
            },
        )

        t = threading.Thread(
            target=_run_agent_subprocess,
            args=(recipient, cmd, subject, transport, is_http, env_vars),
            daemon=True,
        )
        t.start()

    return callback


def _make_direct_trigger_callback(
    transport: Any = None,
) -> Callable:
    """Return a callback that polls for and executes direct trigger messages from Hub UI.

    These are messages created by the Hub UI's "Send Message" feature that need
    to be executed on the host machine (where the CLIs are installed).
    """
    is_http = transport is not None and transport.get_transport_type() == "http"
    seen: Set[str] = set()

    if not is_http:
        # Direct triggers only work with HTTP transport (Hub)
        return lambda event_type, data: None

    def callback(event_type: str, data: Dict[str, Any]) -> None:
        if event_type != "new_message":
            return

        # Check for direct trigger messages (from user via Hub UI)
        sender = data.get("from", "")
        subject = data.get("subject", "")
        if sender != "user" or "Direct message from Hub" not in subject:
            return

        recipient = data.get("to", "")
        msg_id = data.get("id", "")

        if msg_id in seen:
            return
        seen.add(msg_id)

        # Skip if CLI is not available
        if not _check_cli_available(recipient):
            logger.warning(
                "direct_trigger_skipped",
                extra={
                    "event": "direct_trigger_skipped",
                    "data": {
                        "agent": recipient,
                        "msg_id": msg_id,
                        "reason": "CLI not found in PATH",
                    },
                },
            )
            return

        # Extract optional session ID from content tag, then discard raw content.
        # We do NOT pass raw content directly as the prompt — agents need to go through
        # their normal get_inbox flow so that output capture (MCP tool events, stream-json
        # events) works correctly.  The message stays unread in the DB so the agent can
        # retrieve it via get_inbox.  The seen-set above prevents re-triggering within
        # this watchdog session.
        content = data.get("content", "")
        session_id = None
        if "[Session:" in content:
            import re as _re

            match = _re.search(r"\[Session:\s*([^\]]+)\]", content)
            if match:
                session_id = match.group(1).strip()
        # For direct triggers, no [Session:] tag means the user explicitly chose
        # "New conversation" in the UI. Do NOT fall back to the saved session,
        # or the message will be routed to the previous session.

        prompt = (
            f"You have a new AgentWeave message from user. "
            f"Call get_inbox('{recipient}') to retrieve it and respond."
        )
        cmd = _agent_ping_cmd(recipient, prompt, session_id=session_id)

        # Load env_vars from session config for claude_proxy agents
        env_vars = None
        from .session import Session

        session = Session.load()
        if session:
            runner_config = session.get_runner_config(recipient)
            if runner_config.get("runner") == "claude_proxy" and runner_config.get("env_vars"):
                env_vars = runner_config.get("env_vars")

        logger.info(
            "direct_trigger_executing",
            extra={
                "event": "direct_trigger_executing",
                "data": {"agent": recipient, "msg_id": msg_id, "session_id": session_id},
            },
        )
        print(f"[TRIGGER] Executing direct trigger for {recipient}")
        print(f"[TRIGGER] Command: {' '.join(cmd)}")
        if session_id:
            print(f"[TRIGGER] Resuming session: {session_id}")

        # Execute in background thread.
        # Message is intentionally left unread so the agent can read it via get_inbox.
        t = threading.Thread(
            target=_run_agent_subprocess,
            args=(recipient, cmd, "Direct trigger from Hub", transport, is_http, env_vars),
            daemon=True,
        )
        t.start()

    return callback


def main() -> None:
    """CLI entry point for watchdog."""
    from .logging_handlers import _configure_logging

    _configure_logging()

    import argparse

    parser = argparse.ArgumentParser(
        description="Watch for AgentWeave changes",
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=float,
        default=None,
        help="Poll interval in seconds (default: 5 for local, 10 for git transport)",
    )
    parser.add_argument(
        "--auto-ping",
        action="store_true",
        help="Automatically ping the target agent's CLI when a message arrives",
    )
    parser.add_argument(
        "--agent",
        type=str,
        default=None,
        help="Agent to monitor and ping when --auto-ping is set (e.g. claude, kimi)",
    )
    parser.add_argument(
        "--retry-after",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Re-ping if a message is still unread after this many seconds (e.g. 600 for 10min)",
    )

    args = parser.parse_args()

    watchdog = Watchdog(
        poll_interval=args.interval or 5.0,
        retry_after=args.retry_after,
        agent=args.agent,
    )

    callbacks = []

    if args.auto_ping:
        if args.agent:
            agents_to_ping = [args.agent]
        else:
            # No --agent given: read all agents from the active session
            from .session import Session

            session = Session.load()
            if not session:
                print(
                    "Error: --auto-ping without --agent requires an active session. "
                    "Run: agentweave init",
                    file=sys.stderr,
                )
                sys.exit(1)
            agents_to_ping = session.agent_names

        callbacks.append(
            _make_ping_callback(
                agents_to_ping,
                pinged_at=watchdog.pinged_at,
                transport=watchdog.transport,
            )
        )
        print(f"[PING] Auto-ping enabled for: {', '.join(agents_to_ping)}")
        if args.retry_after:
            print(f"[PING] Retry after: {int(args.retry_after)}s")

    # Always enable direct trigger callback for HTTP transport
    # This allows Hub UI "Send Message" to work
    callbacks.append(_make_direct_trigger_callback(transport=watchdog.transport))
    print("[TRIGGER] Direct trigger handler enabled (for Hub UI messages)")

    # On HTTP transport: push session config to the Hub so it knows the full
    # agent configuration (names, roles, yolo flags) without filesystem access.
    if watchdog.transport is not None and watchdog.transport.get_transport_type() == "http":
        from .session import Session as _Session

        _sess = _Session.load()
        if _sess:
            try:
                watchdog.transport.push_session(_sess.to_dict())
                print(f"[HUB] Session synced: {', '.join(_sess.agent_names)}")
            except Exception as _exc:
                print(f"[WARN] Could not sync session with hub: {_exc}", file=sys.stderr)

        # Push roles config so Hub knows dev roles even after a restart
        try:
            import json as _json

            from .constants import ROLES_CONFIG_FILE

            if ROLES_CONFIG_FILE.exists():
                _roles = _json.loads(ROLES_CONFIG_FILE.read_text(encoding="utf-8"))
                watchdog.transport.push_roles_config(_roles)
                print("[HUB] Roles config synced")
        except Exception as _exc:
            print(f"[WARN] Could not sync roles config with hub: {_exc}", file=sys.stderr)

    # Combine all callbacks into one
    if callbacks:

        def combined_callback(event_type: str, data: Dict[str, Any]) -> None:
            for cb in callbacks:
                cb(event_type, data)

        watchdog.callback = combined_callback

    watchdog.start()


if __name__ == "__main__":
    main()
