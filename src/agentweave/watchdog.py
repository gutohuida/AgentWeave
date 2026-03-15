"""Watchdog script for monitoring new messages and tasks."""

import json
import subprocess
import threading
import time
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .constants import AGENTS_DIR, MESSAGES_PENDING_DIR, TASKS_ACTIVE_DIR
from .utils import load_json


class Watchdog:
    """Monitors .agentweave/ (local) or a remote transport for changes."""

    def __init__(
        self,
        callback: Optional[Callable] = None,
        poll_interval: float = 5.0,
        transport=None,
        retry_after: Optional[float] = None,
        agent: Optional[str] = None,
    ):
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
            self.poll_interval = float(
                getattr(self.transport, "poll_interval", poll_interval)
            )
        else:
            self.poll_interval = poll_interval

        self.agent = agent
        self.known_messages: Set[str] = set()
        self.known_tasks: Set[str] = set()
        self.known_remote_files: Set[str] = set()  # for git transport
        self.running = False
        self.retry_after = retry_after  # seconds; None = no retry
        self.pinged_at: Dict[str, float] = {}  # msg_id -> unix time of last ping

    def _default_callback(self, event_type: str, data: dict):
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
            print(f"   Ready for review!")
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

    def start(self):
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
            self.transport._fetch()
            self.known_remote_files = set(self.transport.list_remote_filenames())

        self.running = True

        try:
            while self.running:
                self._check_once()
                write_heartbeat()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            log_event("watchdog_stopped")
            print("\n\n[STOP] Watchdog stopped")

    def _check_once(self):
        """Check for changes once."""
        transport_type = self.transport.get_transport_type()
        if transport_type == "local":
            self._check_once_local()
        elif transport_type == "http":
            self._check_once_http()
        else:
            self._check_once_remote()

    def _check_once_local(self):
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

    def _init_http_state(self):
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

    def _check_once_http(self):
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

    def _check_once_remote(self):
        """Scan remote transport for new files without consuming messages.

        The watchdog only notifies — it does NOT add message IDs to the seen
        set. Archiving happens via `agentweave msg read` or `agentweave inbox`.
        This means the same message appears in both watchdog notifications AND
        the inbox command until explicitly archived.
        """
        self.transport._fetch()
        current_files = set(self.transport.list_remote_filenames())
        new_files = current_files - self.known_remote_files

        for fname in new_files:
            data = self.transport.read_remote_file(fname)
            if data is None:
                continue
            if "-task-for-" in fname:
                self.callback("new_task", data)
            else:
                self.callback("new_message", data)

        self.known_remote_files = current_files

    def stop(self):
        """Stop watching."""
        self.running = False


def _agent_ping_cmd(agent: str, prompt: str, session_id: Optional[str] = None) -> list:
    """Return the CLI command to ping an agent with a prompt.

    Kimi uses --print; Claude and others use --output-format json so we can
    parse JSONL lines and extract the session_id for resumption.
    """
    if agent == "kimi":
        cmd = ["kimi", "--print"]
        if session_id:
            cmd += ["--session", session_id]
        cmd += ["-p", prompt]
        return cmd
    # Claude and other CLIs — stream-json gives per-event JSONL including thinking blocks
    cmd = [agent, "--output-format", "stream-json"]
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
        content = message.get("content", [])
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
                    prefixed = "\n".join(f"💭 {l}" for l in thinking.splitlines())
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
        cost = data.get("total_cost_usd")
        subtype = data.get("subtype", "")
        if subtype == "error":
            return [f"[ERROR] {data.get('error', 'unknown error')}"]
        if cost is not None:
            return [f"[done] cost: ${cost:.4f}"]
        return []

    # system/init and everything else — ignore
    return []


def _extract_kimi_session_id(sessions_before: set, sessions_after: set) -> Optional[str]:
    """Return the new Kimi session name by diffing before/after ~/.kimi/sessions/ listings."""
    new_sessions = sessions_after - sessions_before
    if new_sessions:
        return next(iter(new_sessions))
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

    # Send "running" heartbeat
    if is_http:
        try:
            transport.push_heartbeat(agent, status="running", message=f"Responding to: {subject}")
        except Exception:
            pass

    session_id: Optional[str] = None

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        for raw_line in proc.stdout:  # type: ignore[union-attr]
            line = raw_line.rstrip("\n")
            # Try to extract session_id from JSONL (always attempt for Claude)
            if agent != "kimi" and session_id is None:
                extracted = _extract_claude_session_id(line)
                if extracted:
                    session_id = extracted
            # Parse Claude stream-json into human-readable chunks; kimi is plain text
            if agent != "kimi":
                readable_lines = _parse_claude_stream_line(line)
            else:
                readable_lines = [line] if line.strip() else []
            # Stream to Hub or local stdout
            if is_http:
                for readable in readable_lines:
                    try:
                        transport.post_agent_output(agent, readable, session_id=session_id)
                    except Exception:
                        pass
            else:
                for readable in readable_lines:
                    print(f"[{agent}] {readable}")
        proc.wait()
    except FileNotFoundError as exc:
        print(f"[ERROR] Failed to launch {agent}: {exc}", file=sys.stderr)
    except Exception as exc:
        print(f"[ERROR] Unexpected error running {agent}: {exc}", file=sys.stderr)

    # Extract kimi session ID after process exits
    if agent == "kimi":
        kimi_dir = Path.home() / ".kimi" / "sessions"
        if kimi_dir.exists():
            sessions_after = {p.name for p in kimi_dir.iterdir() if p.is_dir()}
            session_id = _extract_kimi_session_id(sessions_before, sessions_after)

    # Persist session ID for next run
    if session_id:
        try:
            _save_agent_session(agent, session_id)
        except Exception:
            pass

    # Send "idle" heartbeat
    if is_http:
        try:
            transport.push_heartbeat(agent, status="idle")
        except Exception:
            pass


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
                f"[WARN] {agent} CLI not found in PATH. "
                f"Auto-ping for {agent} will not work.",
                file=sys.stderr,
            )

    def callback(event_type: str, data: Dict[str, Any]) -> None:
        if event_type != "new_message":
            return
        recipient = data.get("to", "")
        if recipient not in agent_set:
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
            log_event("ping_skipped", agent=recipient, msg_id=msg_id, reason="CLI not found in PATH")
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

        from .eventlog import log_event
        import time as _t
        if pinged_at is not None:
            pinged_at[msg_id] = _t.time()
        log_event("watchdog_ping", agent=recipient, msg_id=msg_id,
                  subject=data.get("subject", ""))

        t = threading.Thread(
            target=_run_agent_subprocess,
            args=(recipient, cmd, subject, transport, is_http),
            daemon=True,
        )
        t.start()

    return callback


def main():
    """CLI entry point for watchdog."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Watch for AgentWeave changes",
    )
    parser.add_argument(
        "--interval", "-i",
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

        watchdog.callback = _make_ping_callback(
            agents_to_ping,
            pinged_at=watchdog.pinged_at,
            transport=watchdog.transport,
        )
        print(f"[PING] Auto-ping enabled for: {', '.join(agents_to_ping)}")
        if args.retry_after:
            print(f"[PING] Retry after: {int(args.retry_after)}s")

    watchdog.start()


if __name__ == "__main__":
    main()
