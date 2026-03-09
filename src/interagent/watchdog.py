"""Watchdog script for monitoring new messages and tasks."""

import time
import sys
from pathlib import Path
from typing import Set, Callable, Optional

from .constants import MESSAGES_PENDING_DIR, TASKS_ACTIVE_DIR
from .utils import load_json


class Watchdog:
    """Monitors .interagent/ (local) or a remote transport for changes."""

    def __init__(
        self,
        callback: Optional[Callable] = None,
        poll_interval: float = 5.0,
        transport=None,
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
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            print("\n\n[STOP] Watchdog stopped")

    def _check_once(self):
        """Check for changes once."""
        if self.transport.get_transport_type() == "local":
            self._check_once_local()
        else:
            self._check_once_remote()

    def _check_once_local(self):
        """Scan local .interagent/ filesystem for new files."""
        current_messages = self._scan_messages()
        new_messages = current_messages - self.known_messages

        for msg_id in new_messages:
            msg_data = self._get_message_info(msg_id)
            self.callback("new_message", msg_data)

        self.known_messages = current_messages

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

    args = parser.parse_args()

    watchdog = Watchdog(poll_interval=args.interval or 5.0)
    watchdog.start()


if __name__ == "__main__":
    main()
