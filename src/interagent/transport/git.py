"""Git orphan-branch transport for cross-machine collaboration.

Messages and tasks are stored as JSON files on an orphan branch
(default: interagent/collab). All git operations use plumbing commands
(hash-object, mktree, commit-tree, push) — the working tree and HEAD
are never touched.

File naming on the branch
--------------------------
Messages: {iso_ts}-{from}-{to}-{uuid6}.json
  e.g.    20260309T142301Z-claude-kimi-a3f2c1.json

Tasks:    {iso_ts}-task-for-{assignee}-{uuid6}.json
  e.g.    20260309T142301Z-task-for-kimi-b7d3e2.json

Task status updates: {task_id}-status-{new_status}-{iso_ts}.json

The recipient is encoded in the filename (segment index 2 for messages,
segment index 3 after 'task-for' for tasks), so filtering is a cheap
filename-only operation — no file reads needed for inbox filtering.

Seen-set tracking
-----------------
To avoid re-delivering already-seen messages, seen message IDs are stored
in .interagent/.git_seen/{agent}-seen.txt (one ID per line). This file
is local-only and gitignored. archive_message() adds to the seen set.
"""

import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import BaseTransport
from ..constants import GIT_SEEN_DIR


def _iso_compact() -> str:
    """Compact UTC timestamp for use in filenames (no colons/dashes)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run_git(args: list, stdin_bytes: bytes = None) -> tuple:
    """Run a git command. Returns (returncode, stdout_str, stderr_str)."""
    proc = subprocess.run(
        ["git"] + args,
        input=stdin_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
    return proc.returncode, stdout, stderr


class GitTransport(BaseTransport):
    """Transport backed by a git orphan branch."""

    def __init__(
        self,
        remote: str = "origin",
        branch: str = "interagent/collab",
        poll_interval: int = 10,
    ):
        self.remote = remote
        self.branch = branch
        self.poll_interval = poll_interval
        self._remote_ref = f"{remote}/{branch}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def branch_exists_on_remote(self) -> bool:
        """Check if the collab branch exists on the remote."""
        rc, out, _ = _run_git(["ls-remote", "--heads", self.remote, self.branch])
        return rc == 0 and bool(out.strip())

    def _fetch(self) -> bool:
        """Fetch the remote collab branch (quiet — no output)."""
        rc, _, _ = _run_git(["fetch", self.remote, self.branch, "--quiet"])
        return rc == 0

    def list_remote_filenames(self) -> List[str]:
        """List all filenames currently on the remote collab branch."""
        rc, out, _ = _run_git(["ls-tree", self._remote_ref, "--name-only"])
        if rc != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]

    def read_remote_file(self, filename: str) -> Optional[Dict[str, Any]]:
        """Read and parse a JSON file from the remote collab branch."""
        rc, content, _ = _run_git(["show", f"{self._remote_ref}:{filename}"])
        if rc != 0:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None

    def _push_file(self, filename: str, content_bytes: bytes, commit_msg: str) -> bool:
        """Push a single new JSON file to the remote collab branch.

        Uses only git plumbing — no working tree modification, no HEAD change.
        Retries up to 3 times on non-fast-forward conflicts (race condition
        when two machines push simultaneously).
        """
        for attempt in range(3):
            # Write blob to git object store
            rc, blob_sha, _ = _run_git(
                ["hash-object", "-w", "--stdin"], stdin_bytes=content_bytes
            )
            if rc != 0:
                return False
            blob_sha = blob_sha.strip()

            # Refresh remote state before building the tree
            self._fetch()
            branch_exists = self.branch_exists_on_remote()

            # Build the new tree (existing entries + new blob)
            if branch_exists:
                rc, tree_entries, _ = _run_git(["ls-tree", self._remote_ref])
                mktree_input = (
                    tree_entries + f"100644 blob {blob_sha}\t{filename}\n"
                ).encode("utf-8")
            else:
                mktree_input = f"100644 blob {blob_sha}\t{filename}\n".encode("utf-8")

            rc, new_tree, _ = _run_git(["mktree"], stdin_bytes=mktree_input)
            if rc != 0:
                return False
            new_tree = new_tree.strip()

            # Create commit
            if branch_exists:
                rc, commit_sha, _ = _run_git(
                    [
                        "commit-tree", new_tree,
                        "-p", self._remote_ref,
                        "-m", commit_msg,
                    ]
                )
            else:
                rc, commit_sha, _ = _run_git(
                    ["commit-tree", new_tree, "-m", "init: interagent collab branch"]
                )
            if rc != 0:
                return False
            commit_sha = commit_sha.strip()

            # Push
            rc, _, err = _run_git(
                ["push", self.remote, f"{commit_sha}:refs/heads/{self.branch}"]
            )
            if rc == 0:
                return True
            if "non-fast-forward" in err or "rejected" in err:
                # Another machine pushed first — wait and retry
                time.sleep(0.5 * (2 ** attempt))
                continue
            return False

        return False

    # ------------------------------------------------------------------
    # Seen-set tracking (persisted locally, gitignored)
    # ------------------------------------------------------------------

    def _get_seen_set(self, agent: str) -> set:
        seen_file = GIT_SEEN_DIR / f"{agent}-seen.txt"
        if not seen_file.exists():
            return set()
        lines = seen_file.read_text(encoding="utf-8").splitlines()
        return {line for line in lines if line}

    def _save_seen_set(self, agent: str, seen: set) -> None:
        GIT_SEEN_DIR.mkdir(parents=True, exist_ok=True)
        seen_file = GIT_SEEN_DIR / f"{agent}-seen.txt"
        seen_file.write_text("\n".join(sorted(seen)), encoding="utf-8")

    # ------------------------------------------------------------------
    # Filename helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_msg_filename(message_data: Dict[str, Any]) -> str:
        uid = str(uuid.uuid4())[:6]
        from_agent = message_data.get("from", "unknown")
        to_agent = message_data.get("to", "unknown")
        return f"{_iso_compact()}-{from_agent}-{to_agent}-{uid}.json"

    @staticmethod
    def _make_task_filename(task_data: Dict[str, Any]) -> str:
        uid = str(uuid.uuid4())[:6]
        assignee = task_data.get("assignee", "unknown")
        return f"{_iso_compact()}-task-for-{assignee}-{uid}.json"

    @staticmethod
    def _recipient_from_msg_filename(fname: str) -> str:
        """Extract the 'to' agent from a message filename.

        Filename format: {ts}-{from}-{to}-{uid6}.json
        Split by '-' gives: [ts, from, to, uid6]
        """
        stem = fname[:-5] if fname.endswith(".json") else fname  # strip .json
        parts = stem.split("-")
        return parts[2] if len(parts) >= 4 else ""

    # ------------------------------------------------------------------
    # BaseTransport implementation
    # ------------------------------------------------------------------

    def send_message(self, message_data: Dict[str, Any]) -> bool:
        filename = self._make_msg_filename(message_data)
        content_bytes = json.dumps(message_data, indent=2).encode("utf-8")
        from_agent = message_data.get("from", "?")
        to_agent = message_data.get("to", "?")
        return self._push_file(filename, content_bytes, f"msg: {from_agent}→{to_agent}")

    def get_pending_messages(self, agent: str) -> List[Dict[str, Any]]:
        """Return unread messages addressed to `agent`.

        Fetches from remote, filters by recipient, excludes already-seen IDs.
        Does NOT mutate the seen set — call archive_message() to mark as read.
        """
        self._fetch()
        all_files = self.list_remote_filenames()

        # Fast filter: recipient encoded in filename (no file reads needed)
        candidate_files = [
            f for f in all_files
            if self._recipient_from_msg_filename(f) == agent
        ]

        seen = self._get_seen_set(agent)
        result = []

        for fname in candidate_files:
            data = self.read_remote_file(fname)
            if data is None:
                continue
            msg_id = data.get("id", "")
            if msg_id and msg_id not in seen:
                result.append(data)

        return sorted(result, key=lambda d: d.get("timestamp", ""))

    def archive_message(self, message_id: str) -> bool:
        """Mark a message as read by adding its ID to the local seen set.

        Git transport messages are immutable on the branch (append-only).
        Archiving is tracked locally in .interagent/.git_seen/.
        """
        # Find which agent this message belongs to
        self._fetch()
        all_files = self.list_remote_filenames()

        for fname in all_files:
            if "-task-for-" in fname:
                continue
            data = self.read_remote_file(fname)
            if data is None:
                continue
            if data.get("id") == message_id:
                agent = data.get("to", "")
                if agent:
                    seen = self._get_seen_set(agent)
                    seen.add(message_id)
                    self._save_seen_set(agent, seen)
                return True

        return False

    def send_task(self, task_data: Dict[str, Any]) -> bool:
        filename = self._make_task_filename(task_data)
        content_bytes = json.dumps(task_data, indent=2).encode("utf-8")
        assignee = task_data.get("assignee", "?")
        return self._push_file(filename, content_bytes, f"task: for {assignee}")

    def get_active_tasks(self, agent: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return active tasks, optionally filtered by assignee.

        Task definition files: {ts}-task-for-{assignee}-{uid}.json
        Status update files:   {task_id}-status-{new_status}-{iso_ts}.json
        Latest status file wins.
        """
        self._fetch()
        all_files = self.list_remote_filenames()

        def _is_task_def(fname: str) -> bool:
            # {ts}-task-for-{assignee}-{uid}.json  →  parts: [ts, task, for, assignee, uid]
            stem = fname[:-5] if fname.endswith(".json") else fname
            parts = stem.split("-")
            return len(parts) >= 5 and parts[1] == "task" and parts[2] == "for"

        def _task_assignee(fname: str) -> str:
            stem = fname[:-5] if fname.endswith(".json") else fname
            parts = stem.split("-")
            return parts[3] if len(parts) >= 5 else ""

        task_files = [
            f for f in all_files
            if _is_task_def(f) and (agent is None or _task_assignee(f) == agent)
        ]

        # Build latest status map from status update files
        status_files = sorted(f for f in all_files if "-status-" in f)
        status_map: Dict[str, str] = {}
        for sf in status_files:
            # {task_id}-status-{new_status}-{iso_ts}.json
            stem = sf[:-5] if sf.endswith(".json") else sf
            if "-status-" in stem:
                task_id_part, rest = stem.split("-status-", 1)
                new_status = rest.split("-")[0]
                status_map[task_id_part] = new_status

        result = []
        for fname in task_files:
            data = self.read_remote_file(fname)
            if data is None:
                continue
            task_id = data.get("id", fname[:-5])
            if task_id in status_map:
                data["status"] = status_map[task_id]
            if data.get("status") not in ("completed", "approved", "rejected"):
                result.append(data)

        return sorted(result, key=lambda d: d.get("created_at", ""))

    def get_transport_type(self) -> str:
        return "git"
