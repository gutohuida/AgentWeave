"""Watchdog script for monitoring new messages and tasks."""

import subprocess
import time
import sys
from typing import Any, Callable, Dict, List, Optional, Set

from .constants import MESSAGES_PENDING_DIR, TASKS_ACTIVE_DIR
from .utils import load_json


class Watchdog:
    """Monitors .interagent/ (local) or a remote transport for changes."""

    def __init__(
        self,
        callback: Optional[Callable] = None,
        poll_interval: float = 5.0,
        transport=None,
        retry_after: Optional[float] = None,
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

        self.known_messages: Set[str] = set()
        self.known_tasks: Set[str] = set()
        self.known_remote_files: Set[str] = set()  # for git/http transport
        self.running = False
        self.retry_after = retry_after  # seconds; None = no retry
        self.pinged_at: Dict[str, float] = {}  # msg_id -> unix time of last ping

    def _default_callback(self, event_type: str, data: dict):
        """Default callback that prints to stdout."""
        if event_type == "new_message":
            print(f"\n[MSG] New message for {data['to']} from {data['from']}")
            print(f"   Subject: {data.get('subject', '(no subject)')}")
            print(f"   Run: interagent inbox --agent {data['to']}")
            print()
        elif event_type == "new_task":
            print(f"\n[TASK] New task assigned to {data.get('assignee', 'unknown')}")
            print(f"   Title: {data.get('title', 'Untitled')}")
            print(f"   Run: interagent task show {data['id']}")
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
        print(f"[WATCH] InterAgent Watchdog started (transport: {transport_type})")
        if transport_type == "local":
            print(f"   Watching: {MESSAGES_PENDING_DIR}")
            print(f"   Watching: {TASKS_ACTIVE_DIR}")
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
        if self.transport.get_transport_type() == "local":
            self._check_once_local()
        else:
            self._check_once_remote()

    def _check_once_local(self):
        """Scan local .interagent/ filesystem for new files."""
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

    def _check_once_remote(self):
        """Scan remote transport for new files without consuming messages.

        The watchdog only notifies — it does NOT add message IDs to the seen
        set. Archiving happens via `interagent msg read` or `interagent inbox`.
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


def _agent_ping_cmd(agent: str, prompt: str) -> list:
    """Return the CLI command to ping an agent with a prompt."""
    if agent == "kimi":
        return ["kimi", "--print", "-p", prompt]
    return ["claude", "-p", prompt]


def _check_cli_available(agent: str) -> bool:
    """Check if an agent's CLI is available in PATH."""
    import shutil
    cli_name = "kimi" if agent == "kimi" else "claude"
    return shutil.which(cli_name) is not None


def _make_ping_callback(agents: List[str], pinged_at: Optional[Dict[str, float]] = None) -> Callable:
    """Return a callback that pings each agent's CLI when a message addressed to them arrives.

    Handles any number of agents. Non-blocking (Popen fire-and-forget).
    A seen-set prevents double-pings for the same message ID.
    """
    agent_set = set(agents)
    seen: Set[str] = set()

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
            f"You have a new InterAgent message from {data.get('from', 'another agent')}. "
            f"Call get_inbox('{recipient}') to retrieve it and respond."
        )
        cmd = _agent_ping_cmd(recipient, prompt)
        print(f"[PING] Notifying {recipient}: {data.get('subject', '(no subject)')}")
        print(f"[PING] Command: {' '.join(cmd)}")

        from .eventlog import log_event
        import time as _t
        if pinged_at is not None:
            pinged_at[msg_id] = _t.time()
        log_event("watchdog_ping", agent=recipient, msg_id=msg_id,
                  subject=data.get("subject", ""))

        # Run subprocess and capture error output for debugging
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError as e:
            print(f"[ERROR] Failed to ping {recipient}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[ERROR] Unexpected error pinging {recipient}: {e}", file=sys.stderr)

    return callback


def main():
    """CLI entry point for watchdog."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Watch for InterAgent changes",
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
                    "Run: interagent init",
                    file=sys.stderr,
                )
                sys.exit(1)
            agents_to_ping = session.agent_names

        watchdog.callback = _make_ping_callback(agents_to_ping, pinged_at=watchdog.pinged_at)
        print(f"[PING] Auto-ping enabled for: {', '.join(agents_to_ping)}")
        if args.retry_after:
            print(f"[PING] Retry after: {int(args.retry_after)}s")

    watchdog.start()


if __name__ == "__main__":
    main()
