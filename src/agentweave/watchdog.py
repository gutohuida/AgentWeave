"""Watchdog script for monitoring new messages and tasks."""

import contextlib
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .constants import AGENTS_DIR, MESSAGES_PENDING_DIR, TASKS_ACTIVE_DIR
from .eventlog import log_event
from .utils import load_json


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
        from .eventlog import log_event, write_heartbeat

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

        log_event("watchdog_started", transport=transport_type)
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
                    log_event("watchdog_poll_error", severity="warn", error=str(exc))
                write_heartbeat()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            log_event("watchdog_stopped")
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

        from .eventlog import log_event

        current_messages = self._scan_messages()
        new_messages = current_messages - self.known_messages

        for msg_id in new_messages:
            msg_data = self._get_message_info(msg_id)
            log_event(
                "msg_detected",
                msg_id=msg_id,
                **{"to": msg_data.get("to", "?"), "from": msg_data.get("from", "?")},
                subject=msg_data.get("subject", ""),
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
                    log_event(
                        "msg_stale",
                        msg_id=msg_id,
                        **{"to": msg_data.get("to", "?"), "from": msg_data.get("from", "?")},
                        subject=msg_data.get("subject", ""),
                        minutes_unread=elapsed_min,
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
        ['  💭 I need to check my inbox.']
    """

    _EVENT_RE = re.compile(r"^([A-Z][A-Za-z]+)\(")
    # Events we parse and render
    _RENDER = frozenset(
        {"TurnBegin", "StepBegin", "ThinkPart", "TextPart", "ToolCall", "ToolResult"}
    )

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
                text = text[:120] + "…"
            sep = "─" * 56
            return [sep, f"📨  {text}", sep]

        if name == "StepBegin":
            m = re.search(r"n=(\d+)", block)
            n = m.group(1) if m else "?"
            return [f"  ── Step {n} " + "─" * 46]

        if name == "ThinkPart":
            m = re.search(r"think='(.*?)',\s*encrypted", block, re.DOTALL)
            if not m:
                m = re.search(r'think="(.*?)",\s*encrypted', block, re.DOTALL)
            if m:
                thinking = re.sub(r"\s+", " ", m.group(1).replace("\\n", " ")).strip()
                if len(thinking) > 200:
                    thinking = thinking[:200] + "…"
                return [f"  💭 {thinking}"]
            return []

        if name == "TextPart":
            m = re.search(r"text='(.*?)'(?:[,)\s]|$)", block, re.DOTALL)
            if not m:
                m = re.search(r'text="(.*?)"(?:[,)\s]|$)', block, re.DOTALL)
            if m:
                text = m.group(1).replace("\\n", "\n").strip()
                if text:
                    return [f"  💬 {text}"]
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
            tool_name = self._pending.pop(call_id, "")

            is_error = "is_error=True" in block
            if is_error:
                err_m = re.search(r"text='([^']+)'", block)
                err = err_m.group(1)[:100] if err_m else "unknown error"
                return [f"     ✗ {err}"]

            # Meaningful message (e.g. "File successfully overwritten")
            msg_m = re.search(r"message='([^']+)'", block)
            if msg_m and msg_m.group(1).strip():
                return [f"     ✓ {msg_m.group(1).strip()[:100]}"]

            # get_inbox — count messages in result
            if tool_name == "get_inbox":
                count = len(re.findall(r'"id":', block))
                if count:
                    return [f"     ✓ {count} message(s)"]

            return ["     ✓ ok"]

        return []

    @staticmethod
    def _fmt_tool(tool_name: str, args: dict) -> str:
        # Drop large/noisy fields
        skip_keys = {"content", "body", "text", "new_text", "old_text"}
        display = {k: v for k, v in args.items() if k not in skip_keys}
        parts = []
        for k, v in list(display.items())[:4]:
            v_str = str(v)
            if len(v_str) > 60:
                v_str = v_str[:60] + "…"
            parts.append(f'{k}="{v_str}"')
        return f"  🔧 {tool_name}({', '.join(parts)})"


def _agent_ping_cmd(agent: str, prompt: str, session_id: Optional[str] = None) -> list:
    """Return the CLI command to ping an agent with a prompt.

    Kimi uses --print; Claude and others use --output-format stream-json so we can
    parse JSONL lines in real-time and extract the session_id for resumption.
    """
    if agent == "kimi":
        cmd = ["kimi", "--print"]
        if session_id:
            cmd += ["--session", session_id]
        cmd += ["-p", prompt]
        return cmd
    # Claude and other CLIs — stream-json gives real-time JSONL lines with thinking,
    # assistant messages, tool calls, and session_id for resumption.
    # --verbose is required when using --output-format with --print (-p).
    cmd = [agent, "--output-format", "stream-json", "--verbose"]
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
        parts = []
        result_text = data.get("result", "").strip()
        if result_text:
            parts.append(result_text)
        cost = data.get("total_cost_usd")
        if cost is not None:
            parts.append(f"[done] cost: ${cost:.4f}")
        return parts if parts else []

    # system/init and everything else — ignore
    return []


def _extract_kimi_session_id(sessions_before: set, sessions_after: set) -> Optional[str]:
    """Return the new Kimi session name by diffing before/after ~/.kimi/sessions/ listings."""
    new_sessions = sessions_after - sessions_before
    if new_sessions:
        return next(iter(new_sessions))
    return None


def _get_kimi_session_from_json(work_dir: Optional[str] = None) -> Optional[str]:
    """Read Kimi session ID from ~/.kimi/kimi.json for the given working directory.

    Kimi stores the last_session_id per work_dir in this JSON file.
    This is more reliable than detecting new session directories.
    """
    kimi_json = Path.home() / ".kimi" / "kimi.json"
    if not kimi_json.exists():
        return None
    try:
        data = json.loads(kimi_json.read_text())
        work_dirs = data.get("work_dirs", [])
        # Use provided work_dir or current working directory
        target_dir = work_dir or str(Path.cwd())
        for entry in work_dirs:
            if entry.get("path") == target_dir:
                return entry.get("last_session_id")
    except Exception:
        pass
    return None


def _run_agent_subprocess(
    agent: str,
    cmd: list,
    subject: str,
    transport: Any,
    is_http: bool,
) -> None:
    """Background thread: run agent, stream output to Hub, save session ID."""
    # Snapshot kimi sessions before launch
    sessions_before: set = set()
    if agent == "kimi":
        kimi_dir = Path.home() / ".kimi" / "sessions"
        if kimi_dir.exists():
            sessions_before = {p.name for p in kimi_dir.iterdir() if p.is_dir()}

    # Send "running" heartbeat + diagnostic start marker
    if is_http:
        try:
            transport.push_heartbeat(agent, status="running", message=f"Responding to: {subject}")
        except Exception as exc:
            from .eventlog import WARN, log_event

            log_event("watchdog_heartbeat_failed", severity=WARN, agent=agent, error=str(exc))
        try:
            transport.post_agent_output(agent, f"[watchdog] 🚀 Starting {agent}…", session_id=None)
        except Exception as exc:
            print(f"[ERROR] Could not post start marker to Hub: {exc}", file=sys.stderr)

    session_id: Optional[str] = None
    # Mutable container so the stderr thread can read the latest session_id
    session_id_ref: List[Optional[str]] = [None]
    kimi_parser = _KimiParser() if agent == "kimi" else None

    def _drain_stderr(proc: subprocess.Popen) -> None:
        """Read stderr in a background thread and post each line as agent output
        and as a log event so it appears in the Hub Logs tab."""
        _error_keywords = ("Error", "Traceback", "Exception", "FAILED", "fatal")
        try:
            for raw in proc.stderr:  # type: ignore[union-attr]
                err_line = raw.rstrip("\n")
                if not err_line.strip():
                    continue
                msg = f"[stderr] {err_line}"
                if is_http:
                    try:
                        transport.post_agent_output(agent, msg, session_id=session_id_ref[0])
                    except Exception as exc:
                        log_event(
                            "watchdog_output_post_failed",
                            severity=WARN,
                            agent=agent,
                            error=str(exc),
                        )
                    # Only push error-level lines to the Logs tab
                    if any(kw in err_line for kw in _error_keywords):
                        transport.push_log("agent_stderr", agent, {"line": err_line}, "error")
                else:
                    print(f"[{agent}:err] {err_line}", file=sys.stderr)
        except Exception as exc:
            log_event("watchdog_stderr_drain_failed", severity=WARN, agent=agent, error=str(exc))

    def _detect_kimi_session() -> None:
        """Background thread: poll for new Kimi session shortly after start."""
        nonlocal session_id, session_id_ref
        if agent != "kimi":
            return
        kimi_dir = Path.home() / ".kimi" / "sessions"
        if not kimi_dir.exists():
            log_event("watchdog_kimi_no_sessions_dir", severity=WARN)
            return

        # Also read kimi.json for the current working directory
        work_dir = str(Path.cwd())

        # Poll for up to 5 seconds to find new session
        for i in range(50):
            if session_id is not None:
                log_event("watchdog_kimi_session_already_set", session_id=session_id)
                return
            time.sleep(0.1)

            # Method 1: Check for new session directories
            try:
                sessions_now = {p.name for p in kimi_dir.iterdir() if p.is_dir()}
                new_sessions = sessions_now - sessions_before
                if new_sessions:
                    found_session = next(iter(new_sessions))
                    session_id = found_session
                    session_id_ref[0] = found_session
                    log_event("watchdog_kimi_session_found", session_id=found_session, attempts=i, method="directory")
                    return
            except Exception as e:
                log_event("watchdog_kimi_session_error", severity=WARN, error=str(e))

            # Method 2: Read from kimi.json (more reliable)
            try:
                from_json = _get_kimi_session_from_json(work_dir)
                if from_json and from_json not in sessions_before:
                    session_id = from_json
                    session_id_ref[0] = from_json
                    log_event("watchdog_kimi_session_found", session_id=from_json, attempts=i, method="kimi_json")
                    return
            except Exception:
                pass

        log_event("watchdog_kimi_session_not_found", severity=WARN, after_attempts=50)

    def _run_cmd(run_cmd: list, run_session_id: Optional[str]) -> int:
        """Run agent command, stream output. Returns process returncode."""
        nonlocal session_id, session_id_ref

        proc = subprocess.Popen(
            run_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        stderr_thread = threading.Thread(target=_drain_stderr, args=(proc,), daemon=True)
        stderr_thread.start()

        # Start Kimi session detection in background (for real-time session_id)
        if agent == "kimi":
            threading.Thread(target=_detect_kimi_session, daemon=True).start()

        output_line_count = 0
        for raw_line in proc.stdout:  # type: ignore[union-attr]
            line = raw_line.rstrip("\n")
            # Try to extract session_id from JSONL (always attempt for Claude)
            if agent != "kimi" and session_id is None:
                extracted = _extract_claude_session_id(line)
                if extracted:
                    session_id = extracted
                    session_id_ref[0] = session_id
            # Parse output into human-readable lines
            if kimi_parser is not None:
                readable_lines = kimi_parser.feed(line)
            else:
                readable_lines = _parse_claude_stream_line(line)
            # Stream to Hub or local stdout
            if is_http:
                for readable in readable_lines:
                    output_line_count += 1
                    try:
                        # Use session_id_ref[0] to get latest session (updated by detection thread for Kimi)
                        ok = transport.post_agent_output(
                            agent, readable, session_id=session_id_ref[0]
                        )
                        if not ok:
                            print(
                                f"[WARN] post_agent_output returned False for {agent}",
                                file=sys.stderr,
                            )
                    except Exception as exc:
                        log_event(
                            "watchdog_output_post_failed",
                            severity=WARN,
                            agent=agent,
                            error=str(exc),
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
        # expired. Clear it and retry once without --resume.
        saved_session = _load_agent_session(agent) if agent != "kimi" else None
        if returncode != 0 and saved_session:
            from .eventlog import WARN, log_event

            log_event(
                "watchdog_session_retry",
                severity=WARN,
                agent=agent,
                exit_code=returncode,
                reason="stale session cleared",
            )
            print(
                f"[WARN] {agent} exited with code {returncode} — session may be stale, "
                f"clearing and retrying without --resume",
                file=sys.stderr,
            )
            # Clear the stale session file
            session_file = AGENTS_DIR / f"{agent}-session.json"
            with contextlib.suppress(Exception):
                session_file.unlink(missing_ok=True)
            session_id = None
            session_id_ref[0] = None
            retry_cmd = _agent_ping_cmd(agent, cmd[-1], session_id=None)  # cmd[-1] is the prompt
            returncode = _run_cmd(retry_cmd, None)

        if returncode != 0:
            from .eventlog import WARN, log_event

            log_event("watchdog_agent_exit", severity=WARN, agent=agent, exit_code=returncode)
            print(f"[WARN] {agent} exited with code {returncode}", file=sys.stderr)
    except FileNotFoundError as exc:
        from .eventlog import ERROR, log_event

        log_event("watchdog_spawn_failed", severity=ERROR, agent=agent, error=str(exc))
        print(f"[ERROR] Failed to launch {agent}: {exc}", file=sys.stderr)
    except Exception as exc:
        from .eventlog import ERROR, log_event

        log_event("watchdog_subprocess_error", severity=ERROR, agent=agent, error=str(exc))
        print(f"[ERROR] Unexpected error running {agent}: {exc}", file=sys.stderr)

    # Extract kimi session ID after process exits (fallback if _detect_kimi_session missed it)
    if agent == "kimi" and session_id is None:
        work_dir = str(Path.cwd())

        # Method 1: Try reading from kimi.json (most reliable)
        from_json = _get_kimi_session_from_json(work_dir)
        if from_json:
            session_id = from_json
            session_id_ref[0] = from_json
            log_event("watchdog_kimi_session_fallback", session_id=from_json, method="kimi_json")

        # Method 2: Diff session directories
        if session_id is None:
            kimi_dir = Path.home() / ".kimi" / "sessions"
            if kimi_dir.exists():
                sessions_after = {p.name for p in kimi_dir.iterdir() if p.is_dir()}
                session_id = _extract_kimi_session_id(sessions_before, sessions_after)
                if session_id:
                    session_id_ref[0] = session_id
                    log_event("watchdog_kimi_session_fallback", session_id=session_id, method="directory_diff")

    # Persist session ID for next run
    if session_id:
        with contextlib.suppress(Exception):
            _save_agent_session(agent, session_id)
        # For Kimi, post a synthetic output line so the Hub/UI learns the session ID.
        # All real output lines were posted without session_id (detected post-exit),
        # so without this the UI would never see the session ID chip.
        if agent == "kimi" and is_http:
            with contextlib.suppress(Exception):
                transport.post_agent_output(
                    agent, f"[session: {session_id}]", session_id=session_id
                )

    # Send "idle" heartbeat
    if is_http:
        try:
            transport.push_heartbeat(agent, status="idle")
        except Exception as exc:
            from .eventlog import WARN, log_event

            log_event("watchdog_heartbeat_failed", severity=WARN, agent=agent, error=str(exc))


def _check_cli_available(agent: str) -> bool:
    """Check if an agent's CLI is available in PATH."""
    import shutil

    cli_name = "kimi" if agent == "kimi" else agent
    return shutil.which(cli_name) is not None


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
            from .eventlog import log_event

            log_event(
                "ping_skipped", agent=recipient, msg_id=msg_id, reason="CLI not found in PATH"
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

        import time as _t

        from .eventlog import log_event

        if pinged_at is not None:
            pinged_at[msg_id] = _t.time()
        log_event("watchdog_ping", agent=recipient, msg_id=msg_id, subject=data.get("subject", ""))

        t = threading.Thread(
            target=_run_agent_subprocess,
            args=(recipient, cmd, subject, transport, is_http),
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
            log_event(
                "direct_trigger_skipped",
                agent=recipient,
                msg_id=msg_id,
                reason="CLI not found in PATH",
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
        if session_id is None:
            session_id = _load_agent_session(recipient)

        prompt = (
            f"You have a new AgentWeave message from user. "
            f"Call get_inbox('{recipient}') to retrieve it and respond."
        )
        cmd = _agent_ping_cmd(recipient, prompt, session_id=session_id)

        log_event("direct_trigger_executing", agent=recipient, msg_id=msg_id, session_id=session_id)
        print(f"[TRIGGER] Executing direct trigger for {recipient}")
        print(f"[TRIGGER] Command: {' '.join(cmd)}")
        if session_id:
            print(f"[TRIGGER] Resuming session: {session_id}")

        # Execute in background thread.
        # Message is intentionally left unread so the agent can read it via get_inbox.
        t = threading.Thread(
            target=_run_agent_subprocess,
            args=(recipient, cmd, "Direct trigger from Hub", transport, is_http),
            daemon=True,
        )
        t.start()

    return callback


def main() -> None:
    """CLI entry point for watchdog."""
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

    # Combine all callbacks into one
    if callbacks:

        def combined_callback(event_type: str, data: Dict[str, Any]) -> None:
            for cb in callbacks:
                cb(event_type, data)

        watchdog.callback = combined_callback

    watchdog.start()


if __name__ == "__main__":
    main()
