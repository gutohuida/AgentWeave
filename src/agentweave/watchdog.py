"""Watchdog script for monitoring new messages and tasks."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .constants import (
    AGENT_CONTEXT_DIR,
    AGENTS_DIR,
    COMPACT_DECISION_FILE,
    CONTEXT_USAGE_DIR,
    MESSAGES_PENDING_DIR,
    RUNNER_CONFIGS,
    TASKS_ACTIVE_DIR,
    TRIGGERED_DIRECT_FILE,
    _get_context_limit,
)
from .utils import load_dotenv, load_json

logger = logging.getLogger(__name__)


def _discover_spec_files() -> Dict[str, Path]:
    """Discover spec HTML files relative to the project root (CWD).

    Returns a mapping of repo-relative path (e.g. "spec/spec.html",
    "spec/changes/add-thing/spec.html") to the local file Path.
    """
    specs: Dict[str, Path] = {}
    spec_root = Path("spec")
    root_spec = spec_root / "spec.html"
    if root_spec.is_file():
        specs["spec/spec.html"] = root_spec
    changes_dir = spec_root / "changes"
    if changes_dir.is_dir():
        for change_spec in sorted(changes_dir.glob("*/spec.html")):
            specs[change_spec.as_posix()] = change_spec
    return specs


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
        self.known_spec_mtimes: Dict[str, float] = {}  # spec path -> last pushed mtime
        self.running = False
        self.retry_after = retry_after  # seconds; None = no retry
        self.pinged_at: Dict[str, float] = {}  # msg_id -> unix time of last ping
        self.context_warned: Dict[str, bool] = {}  # agent -> currently in warning state
        self._last_context_posted: Dict[str, dict] = {}  # agent -> last context data posted to Hub
        self.compact_decision_mtime: float = 0.0  # mtime of last-processed compact_decision.md

    def _default_callback(self, event_type: str, data: dict) -> None:
        """Default callback that prints to stdout."""
        if event_type == "new_message":
            logger.info(
                f"\n[MSG] New message for {data['to']} from {data['from']}",
                extra={"event": "new_message", "data": {}},
            )
            logger.info(
                f"   Subject: {data.get('subject', '(no subject)')}",
                extra={"event": "new_message", "data": {}},
            )
            logger.info(
                f"   Run: agentweave inbox --agent {data['to']}",
                extra={"event": "new_message", "data": {}},
            )
        elif event_type == "new_task":
            logger.info(
                f"\n[TASK] New task assigned to {data.get('assignee', 'unknown')}",
                extra={"event": "new_task", "data": {}},
            )
            logger.info(
                f"   Title: {data.get('title', 'Untitled')}",
                extra={"event": "new_task", "data": {}},
            )
            logger.info(
                f"   Run: agentweave task show {data['id']}",
                extra={"event": "new_task", "data": {}},
            )
        elif event_type == "task_completed":
            logger.info(
                f"\n[OK] Task completed: {data.get('title', 'Untitled')}",
                extra={"event": "task_completed", "data": {}},
            )
            logger.info("   Ready for review!", extra={"event": "task_completed", "data": {}})
        elif event_type == "context_warning":
            agent = data.get("agent", "unknown")
            percent = data.get("percent", 0)
            model = data.get("model", "?")
            threshold = data.get("threshold_warning", "?")
            logger.info(
                f"\n[CTX] Context warning: {agent} ({model}) at {percent}% (threshold: {threshold}%)",
                extra={"event": "context_event", "data": {}},
            )
            logger.info(
                f"   Run /aw-checkpoint in {agent}'s session, then choose an action.",
                extra={"event": "context_event", "data": {}},
            )
            self._write_compact_decision(data)
        elif event_type == "compact_decision":
            agent = data.get("agent", "unknown")
            choice = data.get("choice", "unknown")
            logger.info(
                f"\n[CTX] Compact decision received for {agent}: {choice}",
                extra={"event": "context_event", "data": {}},
            )
            self._handle_compact_decision(data)

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
        logger.info(
            f"[WATCH] AgentWeave Watchdog started (transport: {transport_type})",
            extra={"event": "watchdog_started", "data": {}},
        )
        if transport_type == "local":
            logger.info(
                f"   Watching: {MESSAGES_PENDING_DIR}",
                extra={"event": "watchdog_started", "data": {}},
            )
            logger.info(
                f"   Watching: {TASKS_ACTIVE_DIR}",
                extra={"event": "watchdog_started", "data": {}},
            )
        elif transport_type == "http":
            hub_url = getattr(self.transport, "url", "?")
            agent_label = self.agent or "all agents"
            logger.info(
                f"   Watching: {hub_url} (polling every {self.poll_interval}s)",
                extra={"event": "watchdog_started", "data": {}},
            )
            logger.info(
                f"   Agent: {agent_label}",
                extra={"event": "watchdog_started", "data": {}},
            )
        else:
            remote = getattr(self.transport, "remote", "?")
            branch = getattr(self.transport, "branch", "?")
            logger.info(
                f"   Watching: {remote}/{branch} (fetching every {self.poll_interval}s)",
                extra={"event": "watchdog_started", "data": {}},
            )
        logger.info(
            f"   Poll interval: {self.poll_interval}s",
            extra={"event": "watchdog_started", "data": {}},
        )
        logger.info(
            "   Press Ctrl+C to stop",
            extra={"event": "watchdog_started", "data": {}},
        )

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
                    logger.warning(
                        f"[WARN] Poll error (will retry in {self.poll_interval}s): {exc}",
                        extra={"event": "watchdog_warn", "data": {}},
                    )
                    logger.warning(
                        "watchdog_poll_error",
                        extra={"event": "watchdog_poll_error", "data": {"error": str(exc)}},
                    )
                write_heartbeat()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logger.info("watchdog_stopped", extra={"event": "watchdog_stopped", "data": {}})
            logger.info(
                "\n\n[STOP] Watchdog stopped", extra={"event": "watchdog_stopped", "data": {}}
            )

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
                    logger.info(
                        f"[STALE] {msg_id} unread for {elapsed_min}m — re-pinging "
                        f"{msg_data.get('to', '?')}",
                        extra={"event": "watchdog_stale", "data": {}},
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

        # Check scheduled jobs (local/git mode only)
        if self.transport.get_transport_type() in ("local", "git"):
            self._check_jobs()

    def _check_context_usage(self) -> None:
        """Scan context_usage/ dir; post updates to Hub and fire warning callbacks."""
        if not CONTEXT_USAGE_DIR.exists():
            return
        for usage_file in CONTEXT_USAGE_DIR.glob("*.json"):
            data = load_json(usage_file) or {}
            agent = data.get("agent", usage_file.stem)
            warning = bool(data.get("warning", False))

            # Always post to Hub when data changes (not just at warning threshold)
            if self.transport.get_transport_type() == "http":
                last = self._last_context_posted.get(agent)
                if data != last:
                    self._last_context_posted[agent] = dict(data)
                    self._post_context_usage_to_hub(agent, data)

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
            elif not warning and self.context_warned.get(agent):
                # Warning cleared (agent compacted or threshold dropped)
                self.context_warned[agent] = False

    def _check_jobs(self) -> None:
        """Check and fire scheduled jobs for local/git transport.

        Iterates enabled jobs, evaluates cron vs current time using croniter.
        Fires jobs that should run, with locking to prevent double-fires.
        """
        from .jobs import Job

        try:
            jobs = Job.list_all()
        except Exception:
            return

        for job in jobs:
            if not job.enabled:
                continue

            # Check if job should fire
            if not job.should_fire():
                continue

            # Acquire lock to prevent concurrent fires
            lock_name = f"job-{job.id}"
            from .locking import acquire_lock, release_lock

            if not acquire_lock(lock_name, timeout=0.1):
                continue  # Another process is firing this job

            try:
                self._fire_job(job, trigger="scheduled")
            finally:
                release_lock(lock_name)

    def _is_self_registered_poll(self, agent: str) -> bool:
        """Check if an agent is self-registered with contact_mode='poll'.

        Returns True only when using HTTP transport and the Hub reports
        self_registered=True and contact_mode='poll'.
        """
        if self.transport.get_transport_type() != "http":
            return False
        reg = self.transport.get_agent_registration(agent)
        if reg:
            return bool(reg.get("self_registered")) and reg.get("contact_mode") == "poll"
        return False

    def _fire_job(self, job: Any, trigger: str = "scheduled") -> bool:
        """Fire a job by running the agent subprocess.

        Args:
            job: The Job to fire
            trigger: "scheduled" or "manual"

        Returns:
            True if fired successfully, False otherwise
        """
        from .jobs import Job

        if isinstance(job, dict):
            job = Job.from_dict(job)

        agent = job.agent
        message = job.message

        # Skip self-registered poll agents — they manage their own polling
        if self._is_self_registered_poll(agent):
            logger.debug(
                "job_fire_skipped_self_registered",
                extra={
                    "event": "job_fire_skipped_self_registered",
                    "data": {
                        "job_id": job.id,
                        "agent": agent,
                        "reason": "self-registered poll agent",
                    },
                },
            )
            return False

        # Skip if CLI not available
        if not _check_cli_available(agent):
            logger.warning(
                "job_fire_skipped",
                extra={
                    "event": "job_fire_skipped",
                    "data": {"job_id": job.id, "agent": agent, "reason": "CLI not found"},
                },
            )
            job.record_run(status="failed", trigger=trigger)
            return False

        # Determine session mode
        session_id = None
        if job.session_mode == "resume":
            session_id = job.last_session_id or _load_agent_session(agent)

        # Build command
        cmd = _agent_ping_cmd(agent, message, session_id=session_id)

        # Record the run before firing (so we have the session_id for resume)
        job.record_run(status="fired", trigger=trigger, session_id=session_id)

        logger.info(
            "job_firing",
            extra={
                "event": "job_firing",
                "data": {
                    "job_id": job.id,
                    "job_name": job.name,
                    "agent": agent,
                    "trigger": trigger,
                    "session_id": session_id,
                },
            },
        )
        logger.info(
            f"[JOB] Firing {job.name} → {agent} (trigger: {trigger})",
            extra={"event": "job_fired", "data": {}},
        )

        # Load env_vars from session config for claude_proxy agents
        env_vars = None
        from .session import Session

        session = Session.load()
        if session:
            runner_config = session.get_runner_config(agent)
            # opencode runners also forward env_vars (e.g. MINIMAX_API_KEY for
            # the minimax provider). Other runners (kimi, codex, claude, native)
            # are NOT yet enabled — see TODO at the env-resolution block.
            if runner_config.get("runner") in (
                "claude_proxy",
                "opencode",
                "copilot",
            ) and runner_config.get("env_vars"):
                env_vars = runner_config.get("env_vars")

        # Fire in background thread
        is_http = self.transport.get_transport_type() == "http"
        t = threading.Thread(
            target=_run_agent_subprocess,
            args=(
                agent,
                cmd,
                f"Job: {job.name}",
                self.transport,
                is_http,
                env_vars,
                message,
                session_id,
            ),
            daemon=True,
        )
        t.start()

        return True

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
        from datetime import datetime, timezone

        agent = usage_data.get("agent", "unknown")
        model = usage_data.get("model", "?")
        percent = usage_data.get("percent", 0)
        threshold = usage_data.get("threshold_warning", "?")
        dt = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
            logger.info(
                f"   Decision file: {COMPACT_DECISION_FILE}",
                extra={"event": "compact_decision_written", "data": {}},
            )
            logger.info(
                "   Edit that file: mark [x] your choice, then save.",
                extra={"event": "compact_decision_written", "data": {}},
            )
        except OSError as exc:
            logger.warning(
                f"   [WARN] Could not write decision file: {exc}",
                extra={"event": "watchdog_warn", "data": {}},
            )

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
            logger.info(
                f"   Message sent to {agent}: {subject}",
                extra={"event": "message_sent", "data": {}},
            )
        else:
            logger.warning(
                f"   [WARN] Could not send message to {agent}",
                extra={"event": "watchdog_warn", "data": {}},
            )

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
            logger.warning(
                f"   [WARN] Could not post context usage to Hub: {exc}",
                extra={"event": "watchdog_warn", "data": {}},
            )

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
        # Initial push of all local spec HTML files so the Hub has them
        # even if they haven't changed since the watchdog started.
        self._sync_spec_files(push_all=True)

    def _check_once_http(self) -> None:
        """Poll Hub REST API for new messages and tasks."""
        # Context files are always local, even when using HTTP transport
        self._check_context_usage()

        messages = self.transport.get_pending_messages(self.agent or "")
        for msg in messages:
            msg_id = msg.get("id", "")
            if msg_id and msg_id not in self.known_messages:
                # Intercept new_session_request for Codex agents — delete session file directly
                # instead of sending an inbox message (Codex doesn't poll inbox between turns)
                subject = msg.get("subject", "")
                recipient = msg.get("to", "")
                if subject == "new_session_request" and recipient:
                    from .session import Session

                    _sess = Session.load()
                    if _sess and _sess.get_runner_config(recipient).get("runner") in (
                        "codex",
                        "codex_mcp",
                    ):
                        self._handle_codex_new_session(recipient)
                        self.known_messages.add(msg_id)
                        with contextlib.suppress(Exception):
                            self.transport.archive_message(msg_id)
                        continue

                self.known_messages.add(msg_id)
                self.callback("new_message", msg)

                # Auto-trigger agent for messages from "user" (job triggers, direct triggers)
                sender = msg.get("from", "")
                if sender == "user" and recipient and "Direct message from Hub" not in subject:
                    self._trigger_agent_from_message(recipient, msg)

        tasks = self.transport.get_active_tasks(self.agent or None)
        for task in tasks:
            task_id = task.get("id", "")
            if task_id and task_id not in self.known_tasks:
                self.known_tasks.add(task_id)
                self.callback("new_task", task)

        # Push any new/changed spec HTML files to the Hub
        self._sync_spec_files()

    def _sync_spec_files(self, push_all: bool = False) -> None:
        """Push new or changed spec HTML files to the Hub (http transport only).

        Fully defensive: spec sync must never break the poll loop, so every
        per-file failure is logged and skipped. A file's mtime is recorded
        in known_spec_mtimes only after a successful push, so a transient
        Hub error is retried on the next poll.
        """
        if not hasattr(self.transport, "push_spec"):
            return
        try:
            specs = _discover_spec_files()
        except Exception as exc:
            logger.warning(
                "spec_discovery_failed",
                extra={"event": "spec_discovery_failed", "data": {"error": str(exc)}},
            )
            return
        for rel_path, file_path in specs.items():
            try:
                mtime = file_path.stat().st_mtime
            except OSError as exc:
                logger.warning(
                    "spec_stat_failed",
                    extra={
                        "event": "spec_stat_failed",
                        "data": {"path": rel_path, "error": str(exc)},
                    },
                )
                continue
            if not push_all and self.known_spec_mtimes.get(rel_path) == mtime:
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning(
                    f"   [WARN] Could not read spec file {rel_path}: {exc}",
                    extra={
                        "event": "spec_read_failed",
                        "data": {"path": rel_path, "error": str(exc)},
                    },
                )
                continue
            try:
                if self.transport.push_spec(rel_path, content):
                    self.known_spec_mtimes[rel_path] = mtime
                    logger.info(
                        "spec_pushed",
                        extra={"event": "spec_pushed", "data": {"path": rel_path}},
                    )
            except Exception as exc:
                logger.warning(
                    "spec_push_failed",
                    extra={
                        "event": "spec_push_failed",
                        "data": {"path": rel_path, "error": str(exc)},
                    },
                )

    def _handle_codex_new_session(self, agent: str) -> None:
        """Delete session file and reset context usage for a Codex agent."""
        session_file = AGENTS_DIR / f"{agent}-session.json"
        if session_file.exists():
            try:
                session_file.unlink()
                logger.info(
                    "codex_new_session_file_deleted",
                    extra={
                        "event": "codex_new_session_file_deleted",
                        "data": {"agent": agent, "path": str(session_file)},
                    },
                )
                logger.info(
                    f"[CTX] Deleted session file for {agent} (new session requested)",
                    extra={"event": "context_event", "data": {}},
                )
            except OSError as exc:
                logger.warning(
                    "codex_new_session_file_delete_failed",
                    extra={
                        "event": "codex_new_session_file_delete_failed",
                        "data": {"agent": agent, "error": str(exc)},
                    },
                )
        _reset_context_usage(agent)

    def _ensure_agent_context(self, agent: str) -> bool:
        """Ensure the per-agent context file exists, generating it if needed.

        This tells the agent who it is and what its roles are.
        Returns True if context file exists or was generated successfully.
        """
        from .constants import AGENT_CONTEXT_DIR
        from .session import Session

        AGENT_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        context_file = AGENT_CONTEXT_DIR / f"{agent}.md"

        # If context already exists, just return True
        if context_file.exists():
            return True

        # Try to generate context
        session = Session.load()
        if not session:
            return False

        # Only generate for agents in session
        if agent not in session.agent_names:
            return False

        try:
            content = _build_agent_context(agent, session)
            context_file.write_text(content, encoding="utf-8")
            logger.info(
                "agent_context_generated",
                extra={
                    "event": "agent_context_generated",
                    "data": {"agent": agent, "path": str(context_file)},
                },
            )
            return True
        except Exception as exc:
            logger.warning(
                "agent_context_generation_failed",
                extra={
                    "event": "agent_context_generation_failed",
                    "data": {"agent": agent, "error": str(exc)},
                },
            )
            return False

    def _trigger_agent_from_message(self, agent: str, msg: dict) -> None:
        """Trigger an agent to run based on a Hub message.

        This is called when the watchdog detects a new message from "user"
        (indicating a job trigger or direct trigger from the Hub).
        """
        msg_id = msg.get("id", "")
        content = msg.get("content", "")
        subject = msg.get("subject", "Message from Hub")

        # Skip self-registered poll agents — they manage their own inbox polling
        if self._is_self_registered_poll(agent):
            logger.debug(
                "agent_trigger_skipped_self_registered",
                extra={
                    "event": "agent_trigger_skipped_self_registered",
                    "data": {
                        "agent": agent,
                        "msg_id": msg_id,
                        "reason": "self-registered poll agent",
                    },
                },
            )
            logger.warning(
                f"[SKIP] Self-registered poll agent {agent} handles its own polling",
                extra={"event": "watchdog_skip", "data": {}},
            )
            return

        # Check if agent is in pilot mode - skip auto-execution
        from .session import Session

        session = Session.load()
        if session and session.get_agent_pilot(agent):
            logger.debug(
                "agent_trigger_skipped_pilot",
                extra={
                    "event": "agent_trigger_skipped_pilot",
                    "data": {"agent": agent, "msg_id": msg_id, "reason": "pilot mode"},
                },
            )
            logger.info(
                f"[PILOT] Skipping execution for pilot agent {agent} (manual control)",
                extra={"event": "watchdog_pilot", "data": {}},
            )
            return

        # Ensure agent context file exists (so agent knows its identity/roles)
        self._ensure_agent_context(agent)

        # Skip if CLI not available
        if not _check_cli_available(agent):
            logger.warning(
                "agent_trigger_skipped",
                extra={
                    "event": "agent_trigger_skipped",
                    "data": {"agent": agent, "msg_id": msg_id, "reason": "CLI not found"},
                },
            )
            logger.warning(
                f"[SKIP] Cannot trigger {agent}: CLI not found",
                extra={"event": "watchdog_skip", "data": {}},
            )
            return

        # Parse session info from content tags
        # [Session: <id>] → resume the specified session
        # [NewSession] → explicitly start a new session
        session_id = None
        import re

        session_match = re.search(r"\[Session:\s*([^\]]+)\]", content)
        new_session_match = re.search(r"\[NewSession\]", content)

        if session_match:
            session_id = session_match.group(1).strip()
        elif new_session_match:
            session_id = None  # Explicit new session
        else:
            # No tag - fall back to agent's last saved session
            session_id = _load_agent_session(agent)

        # Clean up content by removing session tags for the actual prompt
        prompt = content
        prompt = re.sub(r"\[Session:\s*[^\]]+\]\n?\n?", "", prompt)
        prompt = re.sub(r"\[NewSession\]\n?\n?", "", prompt)
        prompt = prompt.strip()

        # Prepend shared/context.md so agents know the current session focus
        # without needing a separate file read
        from .constants import SHARED_DIR

        shared_context_file = SHARED_DIR / "context.md"
        if shared_context_file.exists():
            try:
                shared_context = shared_context_file.read_text(encoding="utf-8").strip()
                if shared_context:
                    prompt = f"## Current Session Focus\n\n{shared_context}\n\n---\n\n{prompt}"
            except Exception:
                pass

        # Build command
        cmd = _agent_ping_cmd(agent, prompt, session_id=session_id)

        logger.info(
            "agent_triggering_from_hub",
            extra={
                "event": "agent_triggering_from_hub",
                "data": {
                    "agent": agent,
                    "msg_id": msg_id,
                    "session_id": session_id,
                    "subject": subject,
                },
            },
        )
        logger.info(
            f"[TRIGGER] Firing {agent} from Hub message (session: {session_id or 'new'})",
            extra={"event": "trigger_event", "data": {}},
        )

        # Load env_vars from session config for claude_proxy agents
        env_vars = None
        from .session import Session

        session = Session.load()
        if session:
            runner_config = session.get_runner_config(agent)
            # opencode runners also forward env_vars (e.g. MINIMAX_API_KEY for
            # the minimax provider). Other runners (kimi, codex, claude, native)
            # are NOT yet enabled — see TODO at the env-resolution block.
            if runner_config.get("runner") in (
                "claude_proxy",
                "opencode",
                "copilot",
            ) and runner_config.get("env_vars"):
                env_vars = runner_config.get("env_vars")

        # Fire in background thread
        is_http = True
        t = threading.Thread(
            target=_run_agent_subprocess,
            args=(agent, cmd, subject, self.transport, is_http, env_vars, prompt, session_id),
            daemon=True,
        )
        t.start()

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


class _KimiWireParser:
    """Parser for kimi --wire JSON-RPC 2.0 streaming output.

    Kimi emits events as JSON-RPC 2.0 notifications:
      {"jsonrpc":"2.0","method":"event","params":{"type":"<EventType>","payload":{...}}}

    The event type is in params["type"] and the data is in params["payload"].

    Events handled:
    - ContentPart: payload {"type":"text"/"think","text":"..."} — streamed word by word;
      buffered and flushed as a single line on non-text events or TurnEnd.
    - ToolCallPart: payload {"arguments_part":"..."} — accumulated until ToolCall arrives
    - ToolCall: payload {"id":"...","function":{"name":"...","arguments":"..."}}
    - ToolResult: payload {"tool_call_id":"...","return_value":{"is_error":bool,"output":[...]}}
    - StatusUpdate: payload {"context_usage":0-1,"context_tokens":N,"max_context_tokens":N}
    - CompactionBegin/CompactionEnd: context compaction lifecycle
    - TurnEnd: end of turn; flushes any buffered text
    """

    def __init__(self) -> None:
        self._pending_tool_calls: Dict[str, str] = {}  # call_id -> tool_name
        self._pending_tool_args: str = ""  # accumulated from ToolCallPart events
        self._context_usage: Optional[Dict[str, Any]] = None
        self._session_id: Optional[str] = None
        self._in_compaction = False
        self._turn_ended = False
        self._text_buf: str = ""  # buffered ContentPart text (flushed on non-text event)
        self._think_buf: str = ""  # buffered think text

    def feed(self, line: str) -> List[str]:
        """Feed one JSON-RPC line; returns list of display strings."""
        stripped = line.strip()
        if not stripped:
            return []

        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return []

        # Primary format: JSON-RPC 2.0 notification
        # {"jsonrpc":"2.0","method":"event","params":{"type":"...","payload":{...}}}
        if "method" in data and "params" in data:
            params = data.get("params", {})
            if isinstance(params, dict):
                event_type = params.get("type", "")
                payload = params.get("payload", {})
                if not isinstance(payload, dict):
                    payload = {}
                return self._handle_event(event_type, payload)

        # Legacy response format: {"result": {"type": "...", ...}}
        if "result" in data:
            result = data.get("result", {})
            if isinstance(result, dict):
                return self._handle_event(result.get("type", ""), result)

        # Direct format: {"type": "...", ...}
        if "type" in data:
            return self._handle_event(data.get("type", ""), data)

        return []

    def _flush_text(self) -> List[str]:
        """Flush any buffered ContentPart text as a single display line."""
        out: List[str] = []
        if self._text_buf:
            out.append(f"  💬 {self._text_buf}")
            self._text_buf = ""
        if self._think_buf:
            thinking = self._think_buf.replace("\n", "\n  💭 ")
            out.append(f"  💭 {thinking}")
            self._think_buf = ""
        return out

    def _handle_event(self, event_type: str, payload: Dict[str, Any]) -> List[str]:
        """Handle a single event and return display strings."""
        if event_type == "ContentPart":
            # payload: {"type": "text"/"think", "text": "..."}
            content_type = payload.get("type", "")
            text = payload.get("text", "")
            if content_type == "text":
                self._text_buf += text
            elif content_type == "think":
                self._think_buf += text
            return []

        # Non-text event: flush any buffered text first
        out = self._flush_text()

        if event_type == "ToolCallPart":
            # payload: {"arguments_part": "..."}
            self._pending_tool_args += payload.get("arguments_part", "")

        elif event_type == "ToolCall":
            # payload: {"id":"...","function":{"name":"...","arguments":"..."}}
            func = payload.get("function", {})
            name = func.get("name") or payload.get("name", "unknown")
            arguments_str = self._pending_tool_args or func.get("arguments", "")
            self._pending_tool_args = ""
            call_id = payload.get("id", "")
            if call_id:
                self._pending_tool_calls[call_id] = name
            try:
                arguments = json.loads(arguments_str) if arguments_str else {}
            except (json.JSONDecodeError, ValueError):
                arguments = {}
            args_str = json.dumps(arguments, ensure_ascii=False)
            if len(args_str) > 300:
                args_str = args_str[:300] + "…"
            out.append(f"  🔧 {name}({args_str})")

        elif event_type == "ToolResult":
            # payload: {"tool_call_id":"...","return_value":{"is_error":bool,"output":[{"type":"text","text":"..."}]}}
            call_id = payload.get("tool_call_id", "")
            self._pending_tool_calls.pop(call_id, None)
            return_value = payload.get("return_value", {})
            is_error = (
                return_value.get("is_error", False) if isinstance(return_value, dict) else False
            )
            output = return_value.get("output", []) if isinstance(return_value, dict) else []
            content = ""
            for item in output:
                if isinstance(item, dict) and item.get("type") == "text":
                    content = item.get("text", "")
                    break
            if is_error:
                out.append(f"     ✗ {content[:100] if content else 'error'}")
            elif content:
                out.append(f"     ✓ {content[:100]}")
            else:
                out.append("     ✓ ok")

        elif event_type == "StatusUpdate":
            # payload: {"context_usage":0-1,"context_tokens":N,"max_context_tokens":N,...}
            context_usage = payload.get("context_usage")
            if context_usage is not None:
                self._context_usage = {
                    "percent": int(context_usage * 100),
                    "context_usage_ratio": context_usage,
                    "context_tokens": payload.get("context_tokens"),
                    "max_context_tokens": payload.get("max_context_tokens"),
                }

        elif event_type == "CompactionBegin":
            self._in_compaction = True
            out.append("  🔄 Context compaction started...")

        elif event_type == "CompactionEnd":
            self._in_compaction = False
            out.append("  ✅ Context compaction complete")

        elif event_type == "TurnEnd":
            self._turn_ended = True
            session_id = payload.get("session_id")
            if session_id:
                self._session_id = session_id

        return out

    def get_context_usage(self) -> Optional[Dict[str, Any]]:
        """Return the latest context usage data, if any."""
        return self._context_usage

    def get_session_id(self) -> Optional[str]:
        """Return the session ID if captured from TurnEnd."""
        return self._session_id

    def is_turn_ended(self) -> bool:
        """Return True if a TurnEnd event has been received."""
        return self._turn_ended

    def is_in_compaction(self) -> bool:
        """Return True if we're currently in a compaction."""
        return self._in_compaction


class _KimiCodeParser:
    """Parser for kimi `--print --output-format stream-json` events.

    Two kimi versions emit stream-json with slightly different shapes; both
    are handled here so the watchdog works against either install:

    1. kimi-code v0.x (legacy standalone, e.g. 0.16.0) — chat-history
       persistence events with a top-level "type" field:

         {"type":"metadata","protocol_version":"1.0","created_at":<unix_ms>}
         {"type":"context.append_message","message":{
           "role": "user" | "assistant" | "tool",
           "content": [{"type":"text","text":"…"} | {"type":"think","think":"…"}],
           "toolCalls": [{"type":"function","id":"…","function":{"name":"…","arguments":"…"}}],
           "toolCallId": "…"   // only for role="tool"
         }}

    2. kimi-cli v1.x (e.g. 1.47.0) — bare chat events with no top-level
       "type" field; role/content/tool_calls live at the event root.
       v1.x uses snake_case keys (tool_calls, tool_call_id) and emits tool
       `content` as a plain string instead of a list of typed parts:

         {"role":"assistant","content":[{"type":"think","think":"…"},
                                         {"type":"text","text":"…"}],
          "tool_calls":[{"type":"function","id":"…",
                        "function":{"name":"get_inbox","arguments":"…"}}]}
         {"role":"user","content":[{"type":"text","text":"…"}]}
         {"role":"tool","content":"<raw text>",
          "tool_call_id":"…"}

    Both shapes are normalized into (role, content, tool_calls) so the same
    rendering helpers work. Skipped on purpose:
      - "metadata" event (v0.x only — no useful display content)
      - role="user" (don't re-display the prompt)
      - events missing a recognized role or with neither top-level nor
        wrapped "message" (forward-compat safety)
    """

    def __init__(self) -> None:
        self._assistant_count = 0

    def feed(self, line: str) -> List[str]:
        stripped = line.strip()
        if not stripped:
            return []
        try:
            evt = json.loads(stripped)
        except json.JSONDecodeError:
            return []

        evt_type = evt.get("type")
        if evt_type == "metadata":
            return []

        # v0.x format: message fields live under evt["message"].
        if evt_type == "context.append_message":
            msg = evt.get("message") or {}
            role = msg.get("role", "")
            content = msg.get("content") or []
            tool_calls = msg.get("toolCalls") or msg.get("tool_calls") or []
        # v1.x format (kimi-cli ≥ 1.0): message fields live at the event root.
        elif "role" in evt and evt_type is None:
            role = evt.get("role", "")
            content = evt.get("content") or []
            tool_calls = evt.get("toolCalls") or evt.get("tool_calls") or []
        else:
            return []

        if role == "assistant":
            self._assistant_count += 1
            return self._render_assistant(content, tool_calls)
        if role == "tool":
            return self._render_tool_result(content)
        return []

    @staticmethod
    def _render_assistant(content: Any, tool_calls: List[Any]) -> List[str]:
        """Render an assistant message.

        ``content`` may be:
        - a list of typed parts (kimi thinking-mode + kimi-code v0.x), e.g.
          ``[{"type":"think","think":"…"}, {"type":"text","text":"…"}]``
        - a plain string (kimi-cli v1.x with --no-thinking final message), e.g.
          ``"Done! I wrote the file."``
        - ``[]`` (kimi-cli v1.x mid-task while thinking is enabled but the
          think part was rendered separately, or --no-thinking step events)

        Tool calls are appended after the text/think lines.
        """
        out: List[str] = []
        if isinstance(content, str):
            text = content.strip()
            if text:
                out.append(f"  💬 {text[:500]}")
        else:
            for part in content or []:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type")
                if ptype == "think":
                    thinking = (part.get("think") or "").strip()
                    if not thinking:
                        continue
                    thinking = re.sub(r"\s+", " ", thinking.replace("\n", " "))[:200]
                    out.append(f"  💭 {thinking}")
                elif ptype == "text":
                    text = (part.get("text") or "").strip()
                    if text:
                        out.append(f"  💬 {text[:500]}")
        for tc in tool_calls or []:
            if not isinstance(tc, dict):
                continue
            func = tc.get("function") or {}
            name = func.get("name") or "unknown"
            args_str = func.get("arguments") or "{}"
            try:
                args = json.loads(args_str) if args_str else {}
            except (json.JSONDecodeError, ValueError):
                args = {}
            display = {k: v for k, v in args.items() if k not in {"content", "body", "text"}}
            parts = []
            for k, v in list(display.items())[:4]:
                v_str = str(v)
                if len(v_str) > 60:
                    v_str = v_str[:60] + "…"
                parts.append(f'{k}="{v_str}"')
            out.append(f"  🔧 {name}({', '.join(parts)})")
        return out

    @staticmethod
    def _render_tool_result(content: Any) -> List[str]:
        """Render a tool result.

        ``content`` may be either:
        - a list of typed parts (v0.x / kimi-code / kimi-cli v1.x), e.g.
          ``[{"type":"text","text":"…"}, {"type":"text","text":"…"}]`` —
          multi-part lists (e.g. ``<system>…</system>`` + actual stdout)
          render as multiple ``✓`` lines so neither part is hidden.
        - a plain string (kimi-cli v1.x), e.g. ``"<system>…</system>"``

        Falls back to ``"✓ ok"`` when the input is empty or unparseable.
        """
        if isinstance(content, str):
            text = content.strip()
            return [f"     ✓ {text[:200]}"] if text else ["     ✓ ok"]
        out: List[str] = []
        for part in content or []:
            if isinstance(part, dict) and part.get("type") == "text":
                text = (part.get("text") or "").strip()
                if text:
                    out.append(f"     ✓ {text[:200]}")
        if not out:
            out.append("     ✓ ok")
        return out


_KIMI_VERSION_CACHE: Optional[str] = None


def _detect_kimi_major_version() -> str:
    """Return "1" for kimi v1.x (kimi-cli), "0" for kimi-code v0.x standalone,
    or "1" as a safe fallback when detection fails.

    Result is cached at module scope so we only run `kimi --version` once per
    process. Detected by parsing the first numeric segment of `kimi --version`:
        v1.x prints "kimi, version 1.x.y"
        v0.x (standalone Moonshot binary) prints "0.x.y"
    """
    global _KIMI_VERSION_CACHE
    if _KIMI_VERSION_CACHE is not None:
        return _KIMI_VERSION_CACHE
    try:
        result = subprocess.run(["kimi", "--version"], capture_output=True, text=True, timeout=5)
        out = (result.stdout or result.stderr or "").strip()
        # Strip "kimi, version " prefix if present
        lowered = out.lower()
        if "version" in lowered:
            out = out.split("version", 1)[1].strip()
        major = out.split(".")[0].strip() or "1"
        # Sanity-check it's actually a digit
        _KIMI_VERSION_CACHE = major if major.isdigit() else "1"
    except Exception:
        _KIMI_VERSION_CACHE = "1"
    return _KIMI_VERSION_CACHE


def _extract_kimi_code_session(workdir: Path) -> Optional[str]:
    """Find the most recently updated kimi-code session for the given workdir.

    kimi-code keeps a global index at ``~/.kimi-code/session_index.jsonl`` —
    one JSONL record per session with ``sessionId``, ``sessionDir`` and
    ``workDir`` fields. We filter by ``workDir`` (the cwd kimi-code was
    invoked from) and return the session with the newest mtime. The
    per-session ``state.json`` does NOT carry ``workDir`` for native
    kimi-code sessions, so the index is the only reliable source.
    """
    index_file = Path.home() / ".kimi-code" / "session_index.jsonl"
    if not index_file.is_file():
        return None
    try:
        target = str(workdir.resolve())
    except OSError:
        return None
    best_mtime = -1.0
    best_sid: Optional[str] = None
    try:
        with index_file.open(encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if rec.get("workDir") != target:
                    continue
                sd = rec.get("sessionDir") or ""
                sid = rec.get("sessionId") or ""
                if not sid or not sd:
                    continue
                try:
                    mtime = Path(sd).stat().st_mtime
                except OSError:
                    continue
                if mtime > best_mtime:
                    best_mtime = mtime
                    best_sid = sid
    except OSError:
        return best_sid
    return best_sid


def _get_runner_type(agent: str) -> str:
    """Return the runner type for an agent, loading from session config."""
    from .constants import AGENT_RUNNER_DEFAULTS
    from .session import Session

    session = Session.load()
    if session:
        return session.get_runner_config(agent).get("runner", "native")
    return AGENT_RUNNER_DEFAULTS.get(agent, "native")


def _agent_ping_cmd(
    agent: str, prompt: str, session_id: Optional[str] = None, use_wire_mode: bool = False
) -> list:
    """Return the CLI command to ping an agent with a prompt.

    Dispatches based on runner type from session config, not agent name.
    Kimi uses --print for plain Python-repr events, or --print --wire for JSON-RPC 2.0
    streaming with context usage reporting. --wire alone is rejected by the kimi CLI;
    it is a modifier of --print. --session resumes an existing session.
    Claude/claude_proxy use --output-format stream-json --verbose with --resume.
    OpenCode uses `opencode run` with --session, --model, --file, and --format json.
    """
    from .session import Session

    runner_type = _get_runner_type(agent)
    rc = RUNNER_CONFIGS.get(runner_type, RUNNER_CONFIGS["native"])

    if runner_type == "kimi":
        # Two kimi families exist on PATH; the framework supports both:
        #   - kimi v1.x (kimi-cli): --print [--wire] for streaming events
        #   - kimi-code v0.x (standalone Moonshot binary): -p + --output-format
        #     stream-json; chat-history persistence events, no real-time streaming.
        # Detect once per process via `kimi --version`; major version 0 → v0 mode.
        kimi_major = _detect_kimi_major_version()
        if kimi_major == "0":
            # kimi-code v0.x: -p "<prompt>" with --output-format stream-json.
            # Note: -p takes a string arg (subject to ARG_MAX). Long prompts
            # are an existing limitation of kimi-code v0.x itself; not fixed here.
            # -y (--yolo) is incompatible with -p (--prompt) in kimi v0.x — the
            # CLI rejects the combination with "Cannot combine --prompt with
            # --yolo." — so only pass -y when the agent actually has yolo on.
            cmd = ["kimi", "--output-format", "stream-json"]
            session = Session.load()
            if session:
                model = session.get_runner_config(agent).get("model")
                if model:
                    cmd += ["-m", model]
                if session.agents.get(agent, {}).get("yolo"):
                    cmd += ["-y"]
            if session_id:
                cmd += ["-S", session_id]
            cmd += ["-p", prompt]
            return cmd
        # kimi v1.x (kimi-cli, e.g. 1.47.0): non-interactive print mode with
        # stream-json output and -p <prompt>. kimi 1.47.0 rejects --wire as a
        # modifier of --print ("Cannot combine --print, --wire."), so we use
        # the documented --print -p --output-format stream-json combination
        # instead. Each stdout line is a JSON event with role/content fields
        # (no top-level "type"), parsed by _KimiCodeParser.
        cmd = ["kimi", "--print", "--output-format", "stream-json"]
        session = Session.load()
        if session:
            model = session.get_runner_config(agent).get("model")
            if model:
                cmd += [rc.get("model_flag", "--model"), model]
        if session_id:
            cmd += ["-S", session_id]
        cmd += ["-p", prompt]
        return cmd

    if runner_type == "opencode":
        # OpenCode: --session <id> continues an EXISTING session; opencode
        # errors out with "Session not found" if the ID does not exist in
        # its DB. So we use --title for new sessions and let opencode
        # create them on first run. For continuity, _run_cmd parses the
        # JSON output to capture the real opencode sessionID (e.g.
        # "ses_13e16807bffe1TAS5GVCeHxZ0z") and saves it for the next run;
        # the next invocation will see it in known_session_id and pass it
        # via --session to actually continue the previous conversation.
        #
        # Per-agent `cli:` override (in agentweave.yml / session.json) lets the
        # user pin the opencode binary to an absolute path. This matters on
        # hosts with multiple opencode installs on PATH (e.g. a stale Linux
        # 1.14.28 shadowing a working Windows 1.17.x from npm under WSL) —
        # without it, `shutil.which` would resolve the wrong one and the
        # model lookup would fail with `ProviderModelNotFoundError` even
        # though the yml and auth.json are correct.
        session = Session.load()
        cli_override: Optional[str] = None
        if session:
            cli_override = session.get_runner_config(agent).get("cli")
        cli = cli_override or rc.get("cli", "opencode")
        subcommand = rc.get("subcommand", "run")
        cmd = [cli, subcommand]

        # Stable friendly name: agentweave-{agent}
        stable_title = f"agentweave-{agent}"

        # Opencode session IDs are auto-generated as "ses_<alnum>" (~30
        # chars). If the saved value does not match that shape (e.g. a
        # legacy stable name like "agentweave-opencode" from before we
        # captured real sessionIDs), treat it as missing so we fall back
        # to --title instead of feeding opencode an invalid --session.
        import re as _re

        _opencode_sid_re = _re.compile(r"^ses_[A-Za-z0-9]{20,}$")
        if session_id is not None and not _opencode_sid_re.match(session_id):
            session_id = None

        if session_id is None:
            # First run for this agent — no real opencode sessionID yet.
            # Use --title to create a new session named after the agent.
            # The real sessionID will be captured from the JSON output and
            # saved by _run_cmd at exit, so subsequent runs can continue.
            cmd += ["--title", stable_title]
        else:
            # Resuming a known opencode session (e.g. ses_...)
            cmd += ["--session", session_id]

        # Model flag if configured
        if session:
            model = session.get_runner_config(agent).get("model")
            if model:
                cmd += ["--model", model]

        # Context file injection via --file.
        # Use absolute path (matches the codex branch) so opencode can find
        # the file even when the watchdog is launched from a UNC path
        # (e.g. \\wsl.localhost\...) where Windows CMD cannot resolve
        # relative paths. Mirrors codex's rationale at line ~1305.
        context_file = AGENT_CONTEXT_DIR.resolve() / f"{agent}.md"
        if context_file.exists():
            cmd += ["--file", str(context_file)]

        # Pin the opencode working directory to the project root so it
        # resolves "opencode.json" (which holds the mcp.agentweave block)
        # from the right place. Without this, when the watchdog runs from
        # a UNC cwd that opencode cannot chdir into (Windows CMD falls
        # back to C:\Windows), opencode creates a session in the global
        # "Windows" project and never finds the project-root opencode.json
        # — leaving AgentWeave MCP tools unavailable to the agent.
        project_root = AGENT_CONTEXT_DIR.resolve().parent.parent
        cmd += ["--dir", str(project_root)]

        cmd += ["--format", "json", prompt]
        return cmd

    if runner_type == "codex":
        # Codex: headless exec with JSONL output, thread-based sessions
        cli = rc.get("cli", "codex")
        cmd = [cli, "exec"]

        # Resume via positional subcommand: codex exec resume <thread_id>
        if session_id:
            cmd += ["resume", session_id]
        cmd += ["--json", "--skip-git-repo-check"]

        # Context file injection via -c model_instructions_file=<path>
        # Use absolute path because Codex runs from a neutral cwd to avoid
        # auto-discovering .agentweave/ and entering bootstrap mode.
        context_file = AGENT_CONTEXT_DIR.resolve() / f"{agent}.md"
        if context_file.exists():
            cmd += ["-c", f"model_instructions_file={context_file}"]

        # Model flag if configured
        session = Session.load()
        if session:
            model = session.get_runner_config(agent).get("model")
            if model:
                cmd += ["--model", model]

            # Runner options: memory disabled
            runner_options = session.get_runner_options(agent)
            if runner_options.get("memory") is False:
                cmd += ["-c", "memory_mode=disabled"]

            # yolo mode: bypass approval prompts so MCP tools and commands
            # execute without user interaction (required for headless watchdog)
            agent_cfg = session.agents.get(agent, {})
            if agent_cfg.get("yolo"):
                cmd += ["--dangerously-bypass-approvals-and-sandbox"]
            else:
                # `--full-auto` is deprecated by newer codex and was
                # removed in recent versions. `--sandbox workspace-write`
                # is the documented replacement. It auto-approves file
                # edits in the workspace but still prompts for MCP tool
                # calls — which the watchdog cannot answer. So a headless
                # codex agent that needs MCP tools MUST enable yolo, and
                # the diagnostics surface a warning when it doesn't.
                cmd += ["--sandbox", "workspace-write"]

        cmd += [prompt]
        return cmd

    if runner_type == "codex_mcp":
        return [rc.get("cli", "codex"), rc.get("subcommand", "mcp-server")]

    if runner_type == "copilot":
        # Copilot CLI: non-interactive mode with JSONL output, UUID-based sessions.
        # --output-format json → one JSON object per line (session ID in `result` event).
        # --resume=<uuid>     → resume a specific session (= form avoids interactive picker).
        # --allow-all-tools   → headless auto-approval (required for watchdog; --yolo adds
        #                       --allow-all-paths and --allow-all-urls too).
        # --no-ask-user       → prevent interactive questions that would block the watchdog.
        cmd = ["copilot", "--output-format", "json", "--no-ask-user"]
        session = Session.load()
        if session:
            model = session.get_runner_config(agent).get("model")
            if model:
                cmd += ["--model", model]
            agent_cfg = session.agents.get(agent, {})
            if agent_cfg.get("yolo"):
                cmd += ["--yolo"]
            else:
                cmd += ["--allow-all-tools"]
        else:
            cmd += ["--allow-all-tools"]
        if session_id:
            cmd += [f"--resume={session_id}"]
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


def _codex_working_dir() -> Path:
    """Return the project root workdir used for headless Codex runs."""
    agentweave_dir = AGENT_CONTEXT_DIR.resolve().parent
    return agentweave_dir.parent


def _build_codex_mcp_tool_call(
    agent: str,
    prompt: str,
    thread_id: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Build the Codex MCP tool call name and arguments for one turn."""
    if thread_id:
        return "codex-reply", {"threadId": thread_id, "prompt": prompt}

    from .session import Session

    session = Session.load()
    runner_config = session.get_runner_config(agent) if session else {}
    agent_cfg = session.agents.get(agent, {}) if session else {}

    args: Dict[str, Any] = {
        "prompt": prompt,
        "cwd": str(_codex_working_dir()),
        "approval-policy": "never",
        "sandbox": "danger-full-access" if agent_cfg.get("yolo") else "workspace-write",
    }

    model = runner_config.get("model")
    if model:
        args["model"] = model

    context_file = AGENT_CONTEXT_DIR.resolve() / f"{agent}.md"
    if context_file.exists():
        args["developer-instructions"] = context_file.read_text(encoding="utf-8")

    runner_options = session.get_runner_options(agent) if session else {}
    if runner_options.get("memory") is False:
        args["config"] = {"memory_mode": "disabled"}

    return "codex", args


def _load_agent_session(agent: str) -> Optional[str]:
    """Load saved session ID for an agent from .agentweave/agents/<agent>-session.json."""
    session_file = AGENTS_DIR / f"{agent}-session.json"
    if not session_file.exists():
        return None
    try:
        data = json.loads(session_file.read_text(encoding="utf-8"))
        return data.get("session_id")
    except Exception:
        return None


def _save_agent_session(agent: str, session_id: str) -> None:
    """Persist session ID for an agent to .agentweave/agents/<agent>-session.json."""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    session_file = AGENTS_DIR / f"{agent}-session.json"
    session_file.write_text(json.dumps({"session_id": session_id}))


def _clear_agent_session(agent: str) -> None:
    """Remove a saved session ID for an agent if it exists."""
    session_file = AGENTS_DIR / f"{agent}-session.json"
    with contextlib.suppress(FileNotFoundError):
        session_file.unlink()


def _write_context_usage(
    agent: str,
    input_tokens: int,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Write context usage data to .agentweave/shared/context_usage/<agent>.json.

    Computes percent based on model's context limit, with warning at 70% and
    critical at 90%. Returns the usage_data dict on success, None on error.
    """
    context_limit = _get_context_limit(model or "")
    percent = min(100, int((input_tokens / context_limit) * 100)) if context_limit > 0 else 0
    warning = percent >= 70
    critical = percent >= 90

    usage_data: Dict[str, Any] = {
        "agent": agent,
        "percent": percent,
        "model": model or "unknown",
        "input_tokens": input_tokens,
        "context_limit": context_limit,
        "warning": warning,
        "critical": critical,
        "threshold_warning": 70,
        "threshold_critical": 90,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        CONTEXT_USAGE_DIR.mkdir(parents=True, exist_ok=True)
        usage_file = CONTEXT_USAGE_DIR / f"{agent}.json"
        usage_file.write_text(json.dumps(usage_data, indent=2))
        return usage_data
    except OSError as exc:
        logger.warning(
            "context_usage_write_failed",
            extra={
                "event": "context_usage_write_failed",
                "data": {"agent": agent, "error": str(exc)},
            },
        )
        return None


def _write_codex_context_usage(
    agent: str,
    usage_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Write context usage data from Codex turn.completed event.

    Computes percent based on CODEX_MODEL_CONTEXT_LIMITS, with warning at 70%
    and critical at 90%. Returns the usage_data dict on success, None on error.
    """
    from .constants import CODEX_MODEL_CONTEXT_LIMITS

    input_tokens = usage_data.get("input_tokens", 0) or 0
    output_tokens = usage_data.get("output_tokens", 0) or 0
    total_tokens = input_tokens + output_tokens

    # Get model from session config
    model = None
    from .session import Session

    _sess = Session.load()
    if _sess:
        runner_config = _sess.get_runner_config(agent)
        model = runner_config.get("model")

    context_limit = CODEX_MODEL_CONTEXT_LIMITS.get(model, 128000) if model else 128000
    percent = min(100, int((total_tokens / context_limit) * 100)) if context_limit > 0 else 0
    warning = percent >= 70
    critical = percent >= 90

    result: Dict[str, Any] = {
        "agent": agent,
        "percent": percent,
        "model": model or "unknown",
        "tokens_used": total_tokens,
        "tokens_limit": context_limit,
        "input_tokens": input_tokens,
        "cached_input_tokens": usage_data.get("cached_input_tokens", 0),
        "output_tokens": output_tokens,
        "warning": warning,
        "critical": critical,
        "threshold_warning": 70,
        "threshold_critical": 90,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        CONTEXT_USAGE_DIR.mkdir(parents=True, exist_ok=True)
        usage_file = CONTEXT_USAGE_DIR / f"{agent}.json"
        usage_file.write_text(json.dumps(result, indent=2))
        return result
    except OSError as exc:
        logger.warning(
            "codex_context_usage_write_failed",
            extra={
                "event": "codex_context_usage_write_failed",
                "data": {"agent": agent, "error": str(exc)},
            },
        )
        return None


class _CodexMcpClient:
    """Minimal JSON-RPC client for `codex mcp-server` over stdio."""

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd
        self.proc: Optional[subprocess.Popen] = None
        self._next_id = 1
        self._stdout_queue: queue.Queue[str] = queue.Queue()

    def start(self) -> None:
        """Start and initialize the MCP server if it is not already running."""
        if self.proc and self.proc.poll() is None:
            return
        self._stdout_queue = queue.Queue()
        self.proc = subprocess.Popen(
            ["codex", "mcp-server"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=self.cwd,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agentweave-watchdog", "version": "0.1.0"},
            },
            timeout=30,
        )
        self.notify("notifications/initialized", {})

    def _read_stdout(self) -> None:
        """Read JSON-RPC stdout in the background so requests can time out."""
        if not self.proc or not self.proc.stdout:
            return
        try:
            for raw in self.proc.stdout:
                self._stdout_queue.put(raw)
        finally:
            self._stdout_queue.put("")

    def close(self) -> None:
        """Stop the MCP server process."""
        if not self.proc:
            return
        with contextlib.suppress(Exception):
            if self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.close()
        if self.proc.poll() is None:
            self.proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.proc.wait(timeout=5)
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc = None

    def __enter__(self) -> "_CodexMcpClient":
        self.start()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.close()

    def notify(self, method: str, params: Dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("Codex MCP server is not running")
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()

    def request(
        self,
        method: str,
        params: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        self.start()
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            raise RuntimeError("Codex MCP server is not running")
        if timeout is None:
            timeout = float(os.environ.get("AW_CODEX_MCP_TIMEOUT", "1800"))
        request_id = self._next_id
        self._next_id += 1
        self.proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
            + "\n"
        )
        self.proc.stdin.flush()
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"Codex MCP request timed out after {timeout:.0f}s: {method}")
            try:
                raw = self._stdout_queue.get(timeout=min(1.0, remaining))
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise RuntimeError(
                        f"Codex MCP server exited with code {self.proc.returncode}"
                    ) from None
                continue
            if raw == "":
                raise RuntimeError("Codex MCP server exited before returning a response")
            if not raw.strip():
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"Codex MCP error: {message['error']}")
            result = message.get("result", {})
            return result if isinstance(result, dict) else {"result": result}

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})


_CODEX_MCP_CLIENTS: Dict[str, _CodexMcpClient] = {}
_CODEX_MCP_CLIENTS_LOCK = threading.Lock()


def _get_codex_mcp_client(agent: str) -> _CodexMcpClient:
    """Return the long-lived Codex MCP client for this watchdog process."""
    with _CODEX_MCP_CLIENTS_LOCK:
        client = _CODEX_MCP_CLIENTS.get(agent)
        if client is None:
            client = _CodexMcpClient(cwd=str(_codex_working_dir()))
            _CODEX_MCP_CLIENTS[agent] = client
        return client


def _reset_codex_mcp_client(agent: str) -> None:
    """Close and remove a cached Codex MCP client."""
    with _CODEX_MCP_CLIENTS_LOCK:
        client = _CODEX_MCP_CLIENTS.pop(agent, None)
    if client:
        client.close()


def _extract_codex_mcp_result(result: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """Extract thread id and display text from a Codex MCP tools/call result."""
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        thread_id = structured.get("threadId")
        content = structured.get("content")
        return (
            thread_id if isinstance(thread_id, str) else None,
            content if isinstance(content, str) else "",
        )

    thread_id = None
    parts: List[str] = []
    for item in result.get("content", []) if isinstance(result.get("content"), list) else []:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
            with contextlib.suppress(json.JSONDecodeError):
                parsed = json.loads(text)
                if isinstance(parsed, dict) and isinstance(parsed.get("threadId"), str):
                    thread_id = parsed["threadId"]
    return thread_id, "\n".join(parts)


def _run_codex_mcp_turn(
    agent: str,
    prompt: str,
    thread_id: Optional[str],
    transport: Any,
    is_http: bool,
) -> Tuple[Optional[str], int]:
    """Run one Codex MCP turn and stream the final content to AgentWeave."""
    tool_name, arguments = _build_codex_mcp_tool_call(agent, prompt, thread_id)
    client = _get_codex_mcp_client(agent)
    try:
        result = client.call_tool(tool_name, arguments)
    except RuntimeError as exc:
        message = str(exc)
        if thread_id and "Session not found for thread_id" in message:
            tool_name, arguments = _build_codex_mcp_tool_call(agent, prompt, thread_id=None)
            result = client.call_tool(tool_name, arguments)
        else:
            _reset_codex_mcp_client(agent)
            raise
    next_thread_id, content = _extract_codex_mcp_result(result)
    if thread_id and "Session not found for thread_id" in content:
        tool_name, arguments = _build_codex_mcp_tool_call(agent, prompt, thread_id=None)
        result = client.call_tool(tool_name, arguments)
        next_thread_id, content = _extract_codex_mcp_result(result)
    if next_thread_id is None:
        next_thread_id = thread_id
    output_count = 0
    if content:
        output_count = 1
        if is_http:
            transport.post_agent_output(agent, content, session_id=next_thread_id)
        else:
            print(f"[{agent}] {content}")
    return next_thread_id, output_count


def _reset_context_usage(agent: str) -> None:
    """Reset context usage to 0% (e.g., on new session detection)."""
    usage_data = {
        "agent": agent,
        "percent": 0,
        "warning": False,
        "critical": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        CONTEXT_USAGE_DIR.mkdir(parents=True, exist_ok=True)
        usage_file = CONTEXT_USAGE_DIR / f"{agent}.json"
        usage_file.write_text(json.dumps(usage_data, indent=2))
    except OSError as exc:
        logger.warning(
            "context_usage_reset_failed",
            extra={
                "event": "context_usage_reset_failed",
                "data": {"agent": agent, "error": str(exc)},
            },
        )


def _write_context_usage_from_wire(
    agent: str,
    wire_usage: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Write context usage data from Kimi wire mode StatusUpdate event.

    Args:
        agent: The agent name
        wire_usage: Dict with 'percent', 'context_usage_ratio', 'context_tokens', 'max_context_tokens'

    Returns the usage_data dict on success, None on error.
    """
    percent = wire_usage.get("percent", 0)
    warning = percent >= 70
    critical = percent >= 90

    usage_data: Dict[str, Any] = {
        "agent": agent,
        "percent": percent,
        "model": "kimi-wire",
        "input_tokens": wire_usage.get("context_tokens", 0),
        "context_limit": wire_usage.get("max_context_tokens", 0),
        "warning": warning,
        "critical": critical,
        "threshold_warning": 70,
        "threshold_critical": 90,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        CONTEXT_USAGE_DIR.mkdir(parents=True, exist_ok=True)
        usage_file = CONTEXT_USAGE_DIR / f"{agent}.json"
        usage_file.write_text(json.dumps(usage_data, indent=2))
        return usage_data
    except OSError as exc:
        logger.warning(
            "context_usage_wire_write_failed",
            extra={
                "event": "context_usage_wire_write_failed",
                "data": {"agent": agent, "error": str(exc)},
            },
        )
        return None


def _build_agent_context(agent: str, session: Any) -> str:
    """Build the per-agent context file content for .agentweave/context/<agent>.md.

    Tells the agent who it is, its roles, and the team structure.
    Format uses HTML comments at the start (Kimi-compatible, no YAML frontmatter).
    """
    from . import __version__
    from .context_builder import build_agent_context

    try:
        from .cli import _get_project_instructions

        project_instructions = _get_project_instructions()
    except Exception:
        project_instructions = ""

    return build_agent_context(
        agent,
        session,
        version_comment=f"AgentWeave v{__version__}",
        project_instructions=project_instructions,
    ).context


def _load_triggered_ids(max_age_hours: int = 24) -> Set[str]:
    """Load recently-triggered direct-trigger message IDs from disk.

    Returns IDs whose timestamp is within max_age_hours. Also rewrites the file
    without expired entries so it doesn't grow unboundedly.
    """
    if not TRIGGERED_DIRECT_FILE.exists():
        return set()
    try:
        data: Dict[str, str] = json.loads(TRIGGERED_DIRECT_FILE.read_text(encoding="utf-8"))
        cutoff = time.time() - max_age_hours * 3600
        recent: Dict[str, str] = {}
        result: Set[str] = set()
        for msg_id, ts_str in data.items():
            try:
                # Parse ISO timestamp
                import datetime as _dt

                ts = _dt.datetime.fromisoformat(ts_str).timestamp()
            except Exception:
                continue
            if ts >= cutoff:
                recent[msg_id] = ts_str
                result.add(msg_id)
        # Rewrite without expired entries
        if len(recent) != len(data):
            with contextlib.suppress(Exception):
                TRIGGERED_DIRECT_FILE.write_text(json.dumps(recent))
        return result
    except Exception:
        return set()


def _save_triggered_id(msg_id: str) -> None:
    """Persist a triggered direct-trigger message ID to disk.

    Appends to TRIGGERED_DIRECT_FILE. Suppresses all exceptions and logs a
    warning on failure so the caller is never blocked.
    """
    from datetime import datetime, timezone

    ts_str = datetime.now(timezone.utc).isoformat()
    try:
        existing: Dict[str, str] = {}
        if TRIGGERED_DIRECT_FILE.exists():
            with contextlib.suppress(Exception):
                existing = json.loads(TRIGGERED_DIRECT_FILE.read_text(encoding="utf-8"))
        existing[msg_id] = ts_str
        TRIGGERED_DIRECT_FILE.write_text(json.dumps(existing))
    except Exception as exc:
        logger.warning(
            "triggered_direct_write_failed",
            extra={
                "event": "triggered_direct_write_failed",
                "data": {"msg_id": msg_id, "error": str(exc)},
            },
        )


def _extract_jsonl_session_id(line: str, runner_type: str) -> Optional[str]:
    """Parse a JSONL line and extract session ID using runner config fields.

    Uses session_event_type and session_id_field from RUNNER_CONFIGS so the
    parser stays data-driven and works for any JSONL-output runner.
    """
    rc = RUNNER_CONFIGS.get(runner_type, {})
    if rc.get("session_source") != "jsonl":
        return None
    session_event_type = rc.get("session_event_type")
    session_id_field = rc.get("session_id_field", "session_id")
    try:
        data = json.loads(line)
        if session_event_type and data.get("type") != session_event_type:
            return None
        return data.get(session_id_field) or None
    except Exception:
        return None


def _parse_codex_stream_line(line: str) -> tuple:
    """Parse one JSONL line from `codex exec --json`.

    Returns a tuple of (display_strings, usage_data) where:
    - display_strings: list of human-readable strings to post as agent output
    - usage_data: dict with usage info if this is a turn.completed message, else None

    Codex emits `item.started` / `item.completed` events (not `assistant`).
    Each item has a type like `agent_message`, `mcp_tool_call`, `command_execution`.
    """
    try:
        data = json.loads(line)
    except Exception:
        stripped = line.strip()
        return ([stripped] if stripped else [], None)

    msg_type = data.get("type", "")

    # --- item.started: show what Codex is about to do ---
    if msg_type == "item.started":
        item = data.get("item", {})
        item_type = item.get("type", "")
        if item_type == "mcp_tool_call":
            server = item.get("server", "?")
            tool = item.get("tool", "?")
            args = item.get("arguments", {})
            try:
                args_str = json.dumps(args, ensure_ascii=False)
                if len(args_str) > 200:
                    args_str = args_str[:200] + "…"
            except Exception:
                args_str = str(args)
            return ([f"🔧 MCP tool: {server}.{tool}({args_str})"], None)
        if item_type == "command_execution":
            command = item.get("command", "")
            if command:
                return ([f"⚙️  $ {command}"], None)
        return ([], None)

    # --- item.completed: show results and agent messages ---
    if msg_type == "item.completed":
        item = data.get("item", {})
        item_type = item.get("type", "")

        if item_type == "agent_message":
            text = item.get("text", "").strip()
            return ([text] if text else [], None)

        if item_type == "mcp_tool_call":
            tool = item.get("tool", "?")
            error = item.get("error")
            if error:
                err_msg = (
                    error.get("message", str(error)) if isinstance(error, dict) else str(error)
                )
                return ([f"❌ {tool}: {err_msg}"], None)
            return ([], None)

        if item_type == "command_execution":
            command = item.get("command", "")
            exit_code = item.get("exit_code")
            output = item.get("aggregated_output", "").strip()
            lines = []
            if command:
                status = "✅" if exit_code == 0 else "❌"
                lines.append(f"{status} $ {command}")
            if output:
                out_lines = output.splitlines()
                for ol in out_lines[:20]:  # cap at 20 lines
                    lines.append(f"   {ol}")
                if len(out_lines) > 20:
                    lines.append(f"   … ({len(out_lines) - 20} more lines)")
            return (lines, None)

        return ([], None)

    # --- turn.completed: extract usage for context monitoring ---
    if msg_type == "turn.completed":
        usage = data.get("usage", {})
        usage_data = None
        if usage:
            usage_data = {
                "input_tokens": usage.get("input_tokens"),
                "cached_input_tokens": usage.get("cached_input_tokens"),
                "output_tokens": usage.get("output_tokens"),
            }
        return ([], usage_data)

    # Ignore thread.started, turn.started, and other internal events
    return ([], None)


def _extract_claude_session_id(line: str) -> Optional[str]:
    """Parse a JSONL line from claude --output-format stream-json, return session_id if present."""
    try:
        data = json.loads(line)
        return data.get("session_id") or None
    except Exception:
        return None


def _parse_claude_stream_line(line: str) -> tuple:
    """Parse one JSONL line from `claude --output-format stream-json`.

    Returns a tuple of (display_strings, usage_data) where:
    - display_strings: list of human-readable strings to post as agent output
    - usage_data: dict with usage info if this is a result message, else None

    Empty display_strings means the line carries no user-visible content.
    """
    try:
        data = json.loads(line)
    except Exception:
        # Non-JSON line — pass through as-is if non-empty
        stripped = line.strip()
        return ([stripped] if stripped else [], None)

    msg_type = data.get("type", "")

    if msg_type == "assistant":
        message = data.get("message", {})
        # Some CLI versions nest content under "message", others put it at the top level
        content = message.get("content", data.get("content", []))
        if isinstance(content, str):
            return ([content] if content.strip() else [], None)
        results = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type == "thinking":
                thinking = block.get("thinking", "").strip()
                if thinking:
                    # Prefix each line so it's visually distinct in the log
                    prefixed = "\n".join(f"💭 {ln}" for ln in thinking.splitlines())
                    results.append(prefixed)
            elif block_type == "text":
                text = block.get("text", "").strip()
                if text:
                    results.append(text)
        return (results, None)

    if msg_type == "tool_use":
        name = data.get("name", "unknown")
        inp = data.get("input", {})
        try:
            inp_str = json.dumps(inp, ensure_ascii=False)
            if len(inp_str) > 300:
                inp_str = inp_str[:300] + "…"
        except Exception:
            inp_str = str(inp)
        return ([f"🔧 {name}({inp_str})"], None)

    if msg_type == "tool_result":
        content = data.get("content", [])
        if isinstance(content, str):
            stripped = content.strip()
            return ([f"  → {stripped[:500]}"] if stripped else [], None)
        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    t = block.get("text", "").strip()
                    if t:
                        snippet = t[:500] + ("…" if len(t) > 500 else "")
                        texts.append(f"  → {snippet}")
            return (texts, None)
        return ([], None)

    if msg_type == "result":
        subtype = data.get("subtype", "")
        if subtype == "error":
            return ([f"[ERROR] {data.get('error', 'unknown error')}"], None)
        # result_text duplicates the already-streamed assistant messages — skip it
        cost = data.get("total_cost_usd")
        display = [f"[done] cost: ${cost:.4f}"] if cost is not None else []
        # Extract usage data for context monitoring
        usage = data.get("usage", {})
        usage_data = None
        if usage and "input_tokens" in usage:
            usage_data = {
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
            }
        return (display, usage_data)

    # system/init and everything else — ignore
    return ([], None)


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


def _copilot_uses_pat(env_vars: Optional[Dict[str, str]]) -> bool:
    """Return True if the copilot agent will authenticate via a PAT, not OAuth.

    PATs (COPILOT_GITHUB_TOKEN, GH_TOKEN, GITHUB_TOKEN) are read atomically from
    an env var and are safe for concurrent copilot processes. Native OAuth reads
    from Windows Credential Manager, which races when multiple copilot processes
    start simultaneously — only the first wins.

    Whether a PAT is in the agent's ``env_vars`` config only matters if the token
    is actually present in the process environment (which is what the copilot CLI
    reads), so the authoritative check is the live environment.
    """
    pat_vars = ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
    return any(os.environ.get(var) for var in pat_vars)


def _run_agent_subprocess(
    agent: str,
    cmd: list,
    subject: str,
    transport: Any,
    is_http: bool,
    env_vars: Optional[Dict[str, str]] = None,
    prompt: str = "",
    known_session_id: Optional[str] = None,
) -> None:
    """Background thread: run agent, stream output to Hub, save session ID."""
    from .locking import acquire_lock, release_lock

    # Acquire lock to prevent concurrent spawns of the same agent
    lock_name = f"spawn_{agent}"
    if not acquire_lock(lock_name, timeout=0.1):  # Short timeout - try once, don't block
        logger.info(
            "spawn_skipped_already_running",
            extra={
                "event": "spawn_skipped_already_running",
                "data": {"agent": agent, "reason": "another_instance_is_running"},
            },
        )
        logger.warning(
            f"[SKIP] {agent} is already running, skipping spawn",
            extra={"event": "watchdog_skip", "data": {}},
        )
        return

    # Copilot agents using native OAuth share Windows Credential Manager — concurrent
    # reads race and only the first process wins. Serialise OAuth-authenticated agents
    # through a shared lock (60 s patience, then skip).
    # PAT users (COPILOT_GITHUB_TOKEN / GH_TOKEN / GITHUB_TOKEN) read atomically from
    # an env var; no race exists, so we skip the lock and allow full concurrency.
    runner_type = _get_runner_type(agent)
    runner_lock_name = (
        f"spawn_runner_{runner_type}"
        if runner_type == "copilot" and not _copilot_uses_pat(env_vars)
        else None
    )
    runner_lock_held = False
    if runner_lock_name:
        if not acquire_lock(runner_lock_name, timeout=60):
            msg = (
                f"[watchdog] ⏳ {agent} queued too long waiting for another copilot agent "
                "to finish — skipping this turn."
            )
            logger.warning(msg, extra={"event": "watchdog_skip", "data": {}})
            if is_http:
                with contextlib.suppress(Exception):
                    transport.post_agent_output(agent, msg, session_id=known_session_id)
            release_lock(lock_name)
            return
        runner_lock_held = True

    try:
        from .diagnostics import launch_blockers
        from .session import Session

        blockers = launch_blockers(agent, Session.load())
        if blockers:
            for blocker in blockers:
                event = (
                    "proxy_api_key_missing"
                    if blocker.id.startswith("proxy_api_key")
                    else "agent_launch_skipped"
                )
                payload = blocker.to_dict()
                logger.error(event, extra={"event": event, "data": payload})
                msg = f"[watchdog] Launch skipped for {agent}: {blocker.message}"
                if blocker.hint:
                    msg = f"{msg} Hint: {blocker.hint}"
                logger.warning(f"[SKIP] {msg}", extra={"event": "watchdog_skip", "data": {}})
                if is_http:
                    with contextlib.suppress(Exception):
                        transport.post_agent_output(agent, msg, session_id=known_session_id)
                    with contextlib.suppress(Exception):
                        transport.push_log(event, agent, payload, "error")
            if is_http:
                with contextlib.suppress(Exception):
                    transport.push_heartbeat(agent, status="idle", message="Launch skipped")
            return
        _do_run_agent_subprocess(
            agent, cmd, subject, transport, is_http, env_vars, prompt, known_session_id
        )
    finally:
        if runner_lock_held and runner_lock_name:
            release_lock(runner_lock_name)
        release_lock(lock_name)


def _do_run_agent_subprocess(
    agent: str,
    cmd: list,
    subject: str,
    transport: Any,
    is_http: bool,
    env_vars: Optional[Dict[str, str]] = None,
    prompt: str = "",
    known_session_id: Optional[str] = None,
) -> None:
    """Internal: run agent, stream output to Hub, save session ID (must hold spawn lock)."""
    runner_type = _get_runner_type(agent)
    is_kimi = runner_type == "kimi"
    is_opencode = runner_type == "opencode"
    is_codex = runner_type == "codex"
    is_copilot = runner_type == "copilot"
    is_codex_mcp = runner_type == "codex_mcp"
    # Detect wire mode: --wire flag in cmd indicates JSON-RPC bidirectional mode
    is_wire_mode = is_kimi and "--wire" in cmd
    # Detect kimi-code v0.x standalone: uses -p + --output-format stream-json
    # (no --print/--wire). Distinguished by the "--output-format" flag in cmd.
    is_kimi_code = is_kimi and "--output-format" in cmd

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
            logger.error(
                f"[ERROR] Could not post start marker to Hub: {exc}",
                extra={"event": "watchdog_error", "data": {}},
            )

    session_id: Optional[str] = known_session_id
    # Mutable container so the stderr thread can read the latest session_id
    session_id_ref: List[Optional[str]] = [known_session_id]
    stale_codex_session: List[bool] = [False]
    # Copilot auth failure flag — set by _drain_stderr when the Copilot CLI reports
    # "No authentication information found" so the completion summary can show ❌.
    copilot_auth_failed: List[bool] = [False]
    # Collect all stdout lines for Kimi session ID extraction (print mode only)
    kimi_stdout_lines: List[str] = []
    recent_stderr: List[str] = []
    # Select appropriate parser based on mode
    kimi_parser: Optional[Any] = None
    if is_wire_mode:
        kimi_parser = _KimiWireParser()
    elif is_kimi_code:
        kimi_parser = _KimiCodeParser()
    elif is_kimi:
        kimi_parser = _KimiParser()

    if is_codex_mcp:
        output_line_count = 0
        try:
            session_id, output_line_count = _run_codex_mcp_turn(
                agent,
                prompt,
                session_id,
                transport,
                is_http,
            )
        except Exception as exc:
            logger.error(
                "watchdog_codex_mcp_error",
                extra={
                    "event": "watchdog_codex_mcp_error",
                    "data": {"agent": agent, "error": str(exc)},
                },
            )
            logger.error(
                f"[ERROR] Codex MCP turn failed for {agent}: {exc}",
                extra={"event": "watchdog_error", "data": {}},
            )

        summary = f"[watchdog] ✅ {agent} done — {output_line_count} output line(s)"
        logger.info(summary, extra={"event": "watchdog_agent_done", "data": {}})
        if is_http:
            with contextlib.suppress(Exception):
                transport.post_agent_output(agent, summary, session_id=session_id)
        if session_id:
            with contextlib.suppress(Exception):
                _save_agent_session(agent, session_id)
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
        return

    def _drain_stderr(proc: subprocess.Popen) -> None:
        """Read stderr in a background thread and post each line as agent output
        and as a log event so it appears in the Hub Logs tab."""
        _error_keywords = ("Error", "Traceback", "Exception", "FAILED", "fatal")
        _copilot_auth_phrase = "No authentication information found"
        try:
            for raw in proc.stderr:  # type: ignore[union-attr]
                err_line = raw.rstrip("\n")
                if not err_line.strip():
                    continue
                # Suppress known Codex stderr noise
                if is_codex and "failed to record rollout items" in err_line:
                    continue
                if is_codex and "Session not found for thread_id" in err_line:
                    stale_codex_session[0] = True

                # Detect copilot auth failure — flag it so the summary shows ❌
                if is_copilot and _copilot_auth_phrase in err_line:
                    copilot_auth_failed[0] = True

                # For Kimi: capture session ID from stderr resume line in real-time
                if is_kimi and session_id_ref[0] is None:
                    m = _KIMI_RESUME_RE.search(err_line)
                    if m:
                        session_id_ref[0] = m.group(1)
                recent_stderr.append(err_line)
                del recent_stderr[:-10]
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

        proc_env = _prepare_agent_env(env_vars)

        # Wire mode requires bidirectional stdin/stdout communication
        stdin_config = subprocess.PIPE if is_wire_mode else subprocess.DEVNULL

        # Codex exec is workspace-scoped to its current directory. Run from
        # the project root so headless turns can inspect, edit, and verify the
        # actual repository instead of the AgentWeave runtime directory.
        cwd = None
        if is_codex:
            cwd = str(_codex_working_dir())

        # Resolve the CLI binary to an absolute path so subprocess.Popen
        # does not depend on the inherited cwd's ability to look up PATH
        # entries. Without this, when the watchdog is launched from a UNC
        # cwd (e.g. \\wsl.localhost\... under WSL), Windows can fail to
        # find `.cmd` shims like `opencode.cmd` and raise WinError 2.
        # shutil.which respects PATHEXT, so a bare "opencode" resolves
        # to "opencode.cmd" — the file subprocess.Popen can actually exec.
        if run_cmd and not os.path.isabs(run_cmd[0]):
            resolved = shutil.which(run_cmd[0])
            if resolved:
                run_cmd = [resolved, *run_cmd[1:]]

        proc = subprocess.Popen(
            run_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=stdin_config,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=proc_env,
            cwd=cwd,
        )
        stderr_thread = threading.Thread(target=_drain_stderr, args=(proc,), daemon=True)
        stderr_thread.start()

        # For wire mode, send the JSON-RPC prompt immediately after starting
        if is_wire_mode and kimi_parser is not None:
            # Use the provided prompt parameter, or fallback to a default
            wire_prompt = (
                prompt
                if prompt
                else (
                    "You have a new AgentWeave message. "
                    "Call get_inbox to retrieve it and respond."
                )
            )
            jsonrpc_request = {
                "jsonrpc": "2.0",
                "method": "prompt",
                "id": f"{agent}-{int(time.time() * 1000)}",
                "params": {"user_input": wire_prompt},
            }
            try:
                proc.stdin.write(json.dumps(jsonrpc_request) + "\n")  # type: ignore[union-attr]
                proc.stdin.flush()  # type: ignore[union-attr]
                # Do NOT close stdin here — kimi's async loop reads EOF as "terminate now"
                # and exits before making the API call. We close stdin later on TurnEnd.
            except Exception as exc:
                logger.warning(
                    "wire_mode_prompt_write_failed",
                    extra={
                        "event": "wire_mode_prompt_write_failed",
                        "data": {"agent": agent, "error": str(exc)},
                    },
                )

        output_line_count = 0
        usage_data_for_context: Optional[Dict[str, Any]] = None
        # Track compaction state to only reset on transition into compaction
        was_in_compaction = False
        for raw_line in proc.stdout:  # type: ignore[union-attr]
            line = raw_line.rstrip("\n")

            if is_kimi:
                (
                    readable_lines,
                    usage_data,
                    was_in_compaction,
                    _,
                ) = _parse_kimi_stdout_line(
                    line,
                    kimi_parser,
                    proc,
                    agent=agent,
                    is_wire_mode=is_wire_mode,
                    is_kimi_code=is_kimi_code,
                    session_id_ref=session_id_ref,
                    was_in_compaction=was_in_compaction,
                    kimi_stdout_lines=kimi_stdout_lines,
                )
            elif is_opencode:
                readable_lines, usage_data = _parse_opencode_stdout_line(line, session_id_ref)
            elif is_copilot:
                readable_lines, usage_data = _parse_copilot_stdout_line(
                    line, runner_type, session_id_ref
                )
            elif is_codex:
                readable_lines, usage_data, stale = _parse_codex_stdout_line(
                    line, runner_type, session_id_ref
                )
                if stale:
                    stale_codex_session[0] = True
            else:
                readable_lines, usage_data = _parse_claude_stdout_line(
                    line, runner_type, session_id_ref
                )

            session_id = session_id_ref[0]
            if usage_data is not None:
                usage_data_for_context = usage_data

            # Stream to Hub or local stdout
            if is_http:
                for readable in readable_lines:
                    output_line_count += 1
                    try:
                        ok = transport.post_agent_output(
                            agent, readable, session_id=session_id_ref[0]
                        )
                        if not ok:
                            logger.warning(
                                f"[WARN] post_agent_output returned False for {agent}",
                                extra={"event": "watchdog_warn", "data": {}},
                            )
                    except Exception as exc:
                        logger.warning(
                            "watchdog_output_post_failed",
                            extra={
                                "event": "watchdog_output_post_failed",
                                "data": {"agent": agent, "error": str(exc)},
                            },
                        )
                        logger.error(
                            f"[ERROR] post_agent_output failed for {agent}: {exc}",
                            extra={"event": "watchdog_error", "data": {}},
                        )
            else:
                for readable in readable_lines:
                    output_line_count += 1
                    print(f"[{agent}] {readable}")

        proc.wait()
        stderr_thread.join(timeout=5)

        # Post a completion summary so we can confirm the pipeline is alive.
        # Show ❌ with actionable guidance when copilot failed to authenticate.
        if is_copilot and copilot_auth_failed[0]:
            summary = (
                f"[watchdog] ❌ {agent} failed — authentication error.\n"
                "[watchdog]    Fix: set COPILOT_GITHUB_TOKEN in your .env (fine-grained PAT\n"
                "[watchdog]    with 'Copilot Requests' permission). Native OAuth is not safe\n"
                "[watchdog]    for concurrent headless use. Or run `copilot login` to refresh."
            )
        else:
            summary = f"[watchdog] ✅ {agent} done — {output_line_count} output line(s)"
        logger.info(summary, extra={"event": "watchdog_agent_done", "data": {}})
        if is_http:
            with contextlib.suppress(Exception):
                transport.post_agent_output(agent, summary, session_id=session_id_ref[0])

        # Write context usage if we captured usage data (Claude/claude_proxy or Kimi wire mode)
        if not is_kimi and not is_codex and usage_data_for_context and proc.returncode == 0:
            input_tokens = usage_data_for_context.get("input_tokens")
            if input_tokens is not None:
                # Get model from session config
                model = None
                from .session import Session

                _sess = Session.load()
                if _sess:
                    runner_config = _sess.get_runner_config(agent)
                    model = runner_config.get("model")
                ctx_data = _write_context_usage(agent, input_tokens, model)
                if is_http and ctx_data:
                    with contextlib.suppress(Exception):
                        transport.post_context_usage(agent, ctx_data)

        # Write context usage for Codex (from turn.completed JSONL events)
        if is_codex and usage_data_for_context and proc.returncode == 0:
            ctx_data = _write_codex_context_usage(agent, usage_data_for_context)
            if is_http and ctx_data:
                with contextlib.suppress(Exception):
                    transport.post_context_usage(agent, ctx_data)

        # Write context usage for Kimi wire mode (uses context_usage ratio instead of input_tokens)
        if is_wire_mode and usage_data_for_context and proc.returncode == 0:
            ctx_data = _write_context_usage_from_wire(agent, usage_data_for_context)
            if is_http and ctx_data:
                with contextlib.suppress(Exception):
                    transport.post_context_usage(agent, ctx_data)

        return proc.returncode or 0

    try:
        returncode = _run_cmd(cmd, session_id)

        if is_codex and session_id and stale_codex_session[0]:
            logger.info(
                "watchdog_codex_stale_session_retry",
                extra={
                    "event": "watchdog_codex_stale_session_retry",
                    "data": {"agent": agent, "session_id": session_id},
                },
            )
            _clear_agent_session(agent)
            session_id = None
            session_id_ref[0] = None
            stale_codex_session[0] = False
            fresh_cmd = _agent_ping_cmd(agent, prompt, session_id=None)
            returncode = _run_cmd(fresh_cmd, None)

        if returncode != 0:
            from .diagnostics import redact_secrets

            logger.warning(
                "watchdog_agent_exit",
                extra={
                    "event": "watchdog_agent_exit",
                    "data": {
                        "agent": agent,
                        "runner": runner_type,
                        "exit_code": returncode,
                        "stderr_tail": redact_secrets(recent_stderr),
                    },
                },
            )
            logger.warning(
                f"[WARN] {agent} exited with code {returncode}",
                extra={"event": "watchdog_warn", "data": {}},
            )
    except FileNotFoundError as exc:
        logger.error(
            "watchdog_spawn_failed",
            extra={"event": "watchdog_spawn_failed", "data": {"agent": agent, "error": str(exc)}},
        )
        logger.error(
            f"[ERROR] Failed to launch {agent}: {exc}",
            extra={"event": "watchdog_error", "data": {}},
        )
    except Exception as exc:
        logger.error(
            "watchdog_subprocess_error",
            extra={
                "event": "watchdog_subprocess_error",
                "data": {"agent": agent, "error": str(exc)},
            },
        )
        logger.error(
            f"[ERROR] Unexpected error running {agent}: {exc}",
            extra={"event": "watchdog_error", "data": {}},
        )

    session_id = _extract_session_id_post_run(
        agent,
        session_id,
        session_id_ref,
        is_kimi=is_kimi,
        is_kimi_code=is_kimi_code,
        is_wire_mode=is_wire_mode,
        kimi_stdout_lines=kimi_stdout_lines,
        returncode=returncode,
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


def _extract_kimi_code_session_id(
    session_id: Optional[str],
    session_id_ref: List[Optional[str]],
    returncode: int,
) -> Optional[str]:
    """Discover a kimi-code v0.x session ID from the global session index."""
    if session_id is not None or returncode != 0:
        return session_id
    workdir = Path.cwd()
    found = _extract_kimi_code_session(workdir)
    if found:
        session_id_ref[0] = found
        logger.info(
            "watchdog_kimi_code_session_found",
            extra={
                "event": "watchdog_kimi_code_session_found",
                "data": {
                    "session_id": found,
                    "method": "session_index_scan",
                    "workdir": str(workdir),
                },
            },
        )
    else:
        logger.warning(
            "watchdog_kimi_code_session_not_found",
            extra={
                "event": "watchdog_kimi_code_session_not_found",
                "data": {"workdir": str(workdir)},
            },
        )
    return found or session_id


def _extract_session_id_post_run(
    agent: str,
    session_id: Optional[str],
    session_id_ref: List[Optional[str]],
    *,
    is_kimi: bool,
    is_kimi_code: bool,
    is_wire_mode: bool,
    kimi_stdout_lines: List[str],
    returncode: int,
) -> Optional[str]:
    """Discover and return the agent session ID after the subprocess exits."""
    if session_id is None and session_id_ref[0] is not None:
        session_id = session_id_ref[0]
    if (
        is_kimi
        and not is_wire_mode
        and not is_kimi_code
        and session_id is None
        and kimi_stdout_lines
    ):
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
    session_id = _extract_kimi_code_session_id(session_id, session_id_ref, returncode)
    if is_wire_mode and session_id:
        logger.info(
            "watchdog_kimi_wire_session_found",
            extra={
                "event": "watchdog_kimi_wire_session_found",
                "data": {"session_id": session_id, "method": "TurnEnd_event"},
            },
        )
    return session_id


def _prepare_agent_env(env_vars: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """Merge env_vars with the current environment and resolve placeholder vars."""
    if not env_vars:
        return None
    proc_env = os.environ.copy()
    proc_env.update(env_vars)
    api_key_var = env_vars.get("ANTHROPIC_API_KEY_VAR")
    if api_key_var:
        resolved = os.environ.get(api_key_var, "")
        if resolved:
            proc_env["ANTHROPIC_API_KEY"] = resolved
        else:
            # Key var declared but not exported — clear inherited Claude key
            # so the failure is an explicit 401 rather than a silent wrong-key error.
            proc_env.pop("ANTHROPIC_API_KEY", None)
            logger.warning(
                f"[WARN] {api_key_var} is not set in the environment. "
                f"Export it before starting the watchdog.",
                extra={"event": "watchdog_warn", "data": {}},
            )
    for var_name in list(env_vars.keys()):
        if var_name in ("ANTHROPIC_API_KEY_VAR", "ANTHROPIC_BASE_URL"):
            continue
        if env_vars[var_name] == var_name:
            value = os.environ.get(var_name)
            if value:
                proc_env[var_name] = value
            else:
                proc_env.pop(var_name, None)
                logger.warning(
                    f"[WARN] {var_name} is not set in the environment. "
                    f"Export it before starting the watchdog.",
                    extra={"event": "watchdog_warn", "data": {}},
                )
    return proc_env


def _parse_kimi_stdout_line(
    line: str,
    parser: Any,
    proc: subprocess.Popen,
    *,
    agent: str,
    is_wire_mode: bool,
    is_kimi_code: bool,
    session_id_ref: List[Optional[str]],
    was_in_compaction: bool,
    kimi_stdout_lines: List[str],
) -> tuple[list[str], Optional[Dict[str, Any]], bool, List[str]]:
    """Parse one line of Kimi stdout (wire, v1.x print, or v0.x stream-json)."""
    readable_lines: list[str] = []
    usage_data: Optional[Dict[str, Any]] = None

    if is_wire_mode:
        readable_lines = parser.feed(line)
        if parser.is_turn_ended() and proc.stdin and not proc.stdin.closed:
            with contextlib.suppress(OSError):
                proc.stdin.close()  # type: ignore[union-attr]
        wire_context_usage = parser.get_context_usage()
        if wire_context_usage is not None:
            usage_data = wire_context_usage
        is_in_compaction = parser.is_in_compaction()
        if is_in_compaction and not was_in_compaction:
            _reset_context_usage(agent)
        was_in_compaction = is_in_compaction
        wire_session_id = parser.get_session_id()
        if wire_session_id:
            session_id_ref[0] = wire_session_id
    else:
        # v1.x print mode or v0.x stream-json
        kimi_stdout_lines.append(line)
        if not is_kimi_code and session_id_ref[0] is None:
            m = _KIMI_RESUME_RE.search(line)
            if m:
                session_id_ref[0] = m.group(1)
        readable_lines = parser.feed(line) if parser is not None else []

    return readable_lines, usage_data, was_in_compaction, kimi_stdout_lines


def _parse_opencode_stdout_line(
    line: str, session_id_ref: List[Optional[str]]
) -> tuple[list[str], Optional[Dict[str, Any]]]:
    """Parse one line of OpenCode JSON output."""
    readable_lines: list[str] = []
    try:
        evt = json.loads(line)
    except (ValueError, TypeError):
        return readable_lines, None

    evt_sid = evt.get("sessionID")
    if evt_sid:
        session_id_ref[0] = evt_sid

    evt_type = evt.get("type")
    if evt_type == "text":
        text = (evt.get("part") or {}).get("text", "")
        if text:
            readable_lines.append(text)
    elif evt_type == "error":
        err = evt.get("error") or {}
        err_name = err.get("name", "Error")
        err_data = err.get("data") or {}
        err_msg = err_data.get("message", "opencode error")
        err_ref = err_data.get("ref", "")
        prefix = f"[opencode error] {err_name}: {err_msg}"
        if err_ref:
            prefix += f" (ref: {err_ref})"
        readable_lines.append(prefix)
    return readable_lines, None


def _parse_codex_stdout_line(
    line: str, runner_type: str, session_id_ref: List[Optional[str]]
) -> tuple[list[str], Optional[Dict[str, Any]], bool]:
    """Parse one line of Codex JSONL output."""
    stale = False
    if session_id_ref[0] is None:
        extracted = _extract_jsonl_session_id(line, runner_type)
        if extracted:
            session_id_ref[0] = extracted
    readable_lines, usage_data = _parse_codex_stream_line(line)
    if any("Session not found for thread_id" in item for item in readable_lines):
        stale = True
        readable_lines = []
    return readable_lines, usage_data, stale


def _parse_copilot_stdout_line(
    line: str, runner_type: str, session_id_ref: List[Optional[str]]
) -> tuple[list[str], Optional[Dict[str, Any]]]:
    """Parse one line of GitHub Copilot CLI JSONL output (--output-format json).

    Copilot emits one JSON object per line. Relevant event types:
    - assistant.message: full agent response with content and tool requests
    - result:            final event with sessionId, exitCode, and usage stats
    - others:            session lifecycle, deltas, user echo — skipped
    """
    # Extract session ID from result event
    if session_id_ref[0] is None:
        extracted = _extract_jsonl_session_id(line, runner_type)
        if extracted:
            session_id_ref[0] = extracted

    try:
        data = json.loads(line)
    except Exception:
        stripped = line.strip()
        return ([stripped] if stripped else [], None)

    msg_type = data.get("type", "")
    event_data = data.get("data", {})

    # Full assistant message (streamed deltas are dropped; this is the complete version)
    if msg_type == "assistant.message":
        results = []
        content = event_data.get("content", "").strip()
        if content:
            results.append(content)
        # Tool request summaries
        for req in event_data.get("toolRequests", []):
            name = req.get("name", "?")
            summary = req.get("intentionSummary", "")
            if summary:
                results.append(f"🔧 {name}: {summary}")
            else:
                args = req.get("arguments", {})
                try:
                    args_str = json.dumps(args, ensure_ascii=False)
                    if len(args_str) > 200:
                        args_str = args_str[:200] + "…"
                except Exception:
                    args_str = str(args)
                results.append(f"🔧 {name}({args_str})")
        return (results, None)

    # Final result event — emit a brief summary
    if msg_type == "result":
        exit_code = data.get("exitCode", 0)
        if exit_code != 0:
            return ([f"[error] copilot exited with code {exit_code}"], None)
        usage = data.get("usage", {})
        premium = usage.get("premiumRequests", 0)
        display = [f"[done] {premium} premium request(s)"] if premium else []
        return (display, None)

    # Ignore streaming deltas, session lifecycle, user echo, MCP status, etc.
    return ([], None)


def _parse_claude_stdout_line(
    line: str, runner_type: str, session_id_ref: List[Optional[str]]
) -> tuple[list[str], Optional[Dict[str, Any]]]:
    """Parse one line of Claude / claude_proxy JSONL output."""
    if session_id_ref[0] is None:
        extracted = _extract_jsonl_session_id(line, runner_type)
        if extracted:
            session_id_ref[0] = extracted
    readable_lines, usage_data = _parse_claude_stream_line(line)
    return readable_lines, usage_data


def _check_cli_available(agent: str) -> bool:
    """Check if an agent's CLI is available in PATH.

    An absolute path in `session.agents[agent].cli` short-circuits the
    PATH lookup — we only need `os.path.isfile` on the explicit value.
    """
    from .session import Session

    runner_type = _get_runner_type(agent)
    rc = RUNNER_CONFIGS.get(runner_type, RUNNER_CONFIGS["native"])
    cli_override: Optional[str] = None
    try:
        session = Session.load()
        if session and agent in session.agent_names:
            cli_override = session.get_runner_config(agent).get("cli")
    except Exception:
        cli_override = None
    if cli_override:
        return os.path.isfile(cli_override) and os.access(cli_override, os.X_OK)
    cli = rc.get("cli") or agent  # native: use agent name as CLI
    return shutil.which(cli) is not None  # shutil: module-level import


def _make_ping_callback(
    agents: List[str],
    pinged_at: Optional[Dict[str, float]] = None,
    transport: Any = None,
) -> Callable:
    """Return a callback that pings each agent's CLI when a message addressed to them arrives.

    Handles any number of agents. Non-blocking (spawns a daemon thread per ping).
    Uses session persistence to resume the same agent session across pings.
    A seen-set prevents double-pings for the same message ID.
    Agent list is reloaded from session.json on each message so agents added
    after the watchdog starts are picked up automatically.
    """
    initial_agent_set = set(agents)
    seen: Set[str] = set()
    is_http = transport is not None and transport.get_transport_type() == "http"

    # Validate CLIs at startup and warn about missing ones
    for agent in agents:
        if not _check_cli_available(agent):
            logger.warning(
                f"[WARN] {agent} CLI not found in PATH. " f"Auto-ping for {agent} will not work.",
                extra={"event": "watchdog_warn", "data": {}},
            )

    def callback(event_type: str, data: Dict[str, Any]) -> None:
        if event_type != "new_message":
            return
        recipient = data.get("to", "")

        # Direct trigger messages (from Hub UI) are handled by _make_direct_trigger_callback
        # which also uses get_inbox flow.  Skip here to avoid launching a second process.
        if data.get("from", "") == "user":
            return
        msg_id = data.get("id", "")
        if msg_id in seen:
            return

        # Reload the live agent list from session.json so agents added after
        # watchdog startup are included without requiring a restart.
        from .session import Session as _Session

        _sess = _Session.load()
        current_agent_set = set(_sess.agent_names) if _sess else initial_agent_set
        if recipient not in current_agent_set:
            return

        if recipient not in initial_agent_set:
            logger.info(
                f"[PING] Detected new agent since startup: {recipient}",
                extra={"event": "ping_event", "data": {}},
            )

        seen.add(msg_id)

        # Skip if CLI is not available
        if not _check_cli_available(recipient):
            logger.warning(
                f"[SKIP] Cannot notify {recipient}: CLI not found in PATH",
                extra={"event": "watchdog_skip", "data": {}},
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

        # Check if agent is in pilot mode - skip auto-execution
        if _sess and _sess.get_agent_pilot(recipient):
            logger.debug(
                "agent_ping_skipped_pilot",
                extra={
                    "event": "agent_ping_skipped_pilot",
                    "data": {"agent": recipient, "msg_id": msg_id, "reason": "pilot mode"},
                },
            )
            logger.info(
                f"[PILOT] Skipping ping for pilot agent {recipient} (manual control)",
                extra={"event": "watchdog_pilot", "data": {}},
            )
            return

        sender = data.get("from", "another agent")
        runner_config = _sess.get_runner_config(recipient) if _sess else {}
        runner_type = runner_config.get("runner")
        # Determine hub_client mode for the recipient agent
        hub_client_mode = _sess.get_agent_hub_client(recipient) if _sess else "auto"

        if runner_type in ("codex", "codex_mcp"):
            content = data.get("content", "")
            prompt = "\n".join(
                [
                    "AgentWeave message",
                    "",
                    f"From: {sender}",
                    f"To: {recipient}",
                    f"Subject: {data.get('subject', '(no subject)')}",
                    "",
                    "Message:",
                    content.strip() or "Continue.",
                ]
            )
            if transport is not None:
                with contextlib.suppress(Exception):
                    transport.archive_message(msg_id)
        elif hub_client_mode == "cli":
            # CLI mode: agent cannot use MCP tools — instruct it to use CLI commands
            prompt = (
                f"You have a new AgentWeave message from {sender}. "
                f"Run: agentweave inbox --agent {recipient} --mark-read"
            )
        else:
            # auto/mcp: default — agent uses MCP get_inbox() tool
            prompt = (
                f"You have a new AgentWeave message from {sender}. "
                f"Call get_inbox('{recipient}') to retrieve it and respond."
            )
        session_id = _load_agent_session(recipient)
        cmd = _agent_ping_cmd(recipient, prompt, session_id=session_id)
        subject = data.get("subject", "(no subject)")
        logger.info(
            f"[PING] Notifying {recipient}: {subject}", extra={"event": "ping_event", "data": {}}
        )
        logger.info(f"[PING] Command: {' '.join(cmd)}", extra={"event": "ping_event", "data": {}})
        if session_id:
            logger.info(
                f"[PING] Resuming session: {session_id}", extra={"event": "ping_event", "data": {}}
            )

        # Load env_vars from session config for claude_proxy agents
        env_vars = None
        if _sess:
            runner_config = _sess.get_runner_config(recipient)
            # opencode runners also forward env_vars (e.g. MINIMAX_API_KEY for
            # the minimax provider). Other runners (kimi, codex, claude, native)
            # are NOT yet enabled — see TODO at the env-resolution block.
            if runner_config.get("runner") in (
                "claude_proxy",
                "opencode",
                "copilot",
            ) and runner_config.get("env_vars"):
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
            args=(recipient, cmd, subject, transport, is_http, env_vars, prompt, session_id),
            daemon=True,
        )
        t.start()

    return callback


def _make_direct_trigger_callback(
    transport: Any = None,
    watchdog_instance: Optional["Watchdog"] = None,
) -> Callable:
    """Return a callback that polls for and executes direct trigger messages from Hub UI.

    These are messages created by the Hub UI's "Send Message" feature that need
    to be executed on the host machine (where the CLIs are installed).

    Args:
        transport: The transport instance to use for communication
        watchdog_instance: Optional Watchdog instance for accessing state (e.g., message counts)
    """
    is_http = transport is not None and transport.get_transport_type() == "http"
    # Pre-populate from disk so restarts don't re-trigger already-processed messages.
    seen: Set[str] = _load_triggered_ids()

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
        _save_triggered_id(msg_id)

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

        # Check if agent is in pilot mode - skip auto-execution
        from .session import Session as _Session

        _sess = _Session.load()
        if _sess and _sess.get_agent_pilot(recipient):
            logger.debug(
                "agent_trigger_skipped_pilot",
                extra={
                    "event": "agent_trigger_skipped_pilot",
                    "data": {"agent": recipient, "reason": "pilot mode (manual control)"},
                },
            )
            logger.info(
                f"[PILOT] Skipping direct trigger for pilot agent {recipient} (manual control)",
                extra={"event": "watchdog_pilot", "data": {}},
            )
            return

        # Extract optional session ID from content tags. Most runners keep the
        # inbox-driven flow so they can retrieve the unread message themselves.
        # Codex runners work better when the direct Hub message is the top-level
        # prompt. Otherwise they can complete the turn after only retrieving and
        # acknowledging the inbox message.
        content = data.get("content", "")
        session_id = None
        is_new_session = False
        if "[Session:" in content:
            import re as _re

            match = _re.search(r"\[Session:\s*([^\]]+)\]", content)
            if match:
                session_id = match.group(1).strip()
        elif "[NewSession]" in content:
            # Hub UI explicitly requested a new session — leave session_id as None.
            is_new_session = True
        else:
            # No session tag present: fall back to the agent's last saved session.
            # This prevents unnecessary new sessions when the Hub UI sends a message
            # before its session-selector has finished loading.
            session_id = _load_agent_session(recipient)

        # Reset context usage and message count when starting a new session
        if is_new_session:
            _reset_context_usage(recipient)
            # Immediately notify Hub to clear the context bar in Mission Control
            if is_http and transport is not None:
                try:
                    reset_data = {
                        "agent": recipient,
                        "percent": 0,
                        "warning": False,
                        "critical": False,
                        "threshold_warning": 70,
                        "threshold_critical": 90,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    transport.post_context_usage(recipient, reset_data)
                except Exception:
                    pass
            # Clear context usage cache on watchdog instance if available
            if watchdog_instance is not None:
                watchdog_instance._last_context_posted.pop(recipient, None)

        runner_config = _sess.get_runner_config(recipient) if _sess else {}
        runner_type = runner_config.get("runner")
        hub_client_mode = _sess.get_agent_hub_client(recipient) if _sess else "auto"
        if runner_type in ("codex", "codex_mcp"):
            cleaned_content = re.sub(r"\[Session:\s*[^\]]+\]\n?\n?", "", content)
            cleaned_content = re.sub(r"\[NewSession\]\n?\n?", "", cleaned_content).strip()
            if not cleaned_content:
                cleaned_content = "Continue."
            prompt = "\n".join(
                [
                    "AgentWeave direct message",
                    "",
                    f"From: {sender}",
                    f"To: {recipient}",
                    f"Subject: {subject}",
                    "",
                    "Message:",
                    cleaned_content,
                ]
            )
            if transport is not None:
                with contextlib.suppress(Exception):
                    transport.archive_message(msg_id)
        elif hub_client_mode == "cli":
            prompt = (
                f"You have a new AgentWeave message from user. "
                f"Run: agentweave inbox --agent {recipient} --mark-read"
            )
        else:
            prompt = (
                f"You have a new AgentWeave message from user. "
                f"Call get_inbox('{recipient}') to retrieve it and respond."
            )

        cmd = _agent_ping_cmd(recipient, prompt, session_id=session_id)

        # Load env_vars from session config for claude_proxy agents
        env_vars = None
        # opencode runners also forward env_vars (e.g. MINIMAX_API_KEY for
        # the minimax provider). Other runners (kimi, codex, claude, native)
        # are NOT yet enabled — see TODO at the env-resolution block.
        if runner_config.get("runner") in (
            "claude_proxy",
            "opencode",
            "copilot",
        ) and runner_config.get("env_vars"):
            env_vars = runner_config.get("env_vars")

        logger.info(
            "direct_trigger_executing",
            extra={
                "event": "direct_trigger_executing",
                "data": {"agent": recipient, "msg_id": msg_id, "session_id": session_id},
            },
        )
        logger.info(
            f"[TRIGGER] Executing direct trigger for {recipient}",
            extra={"event": "trigger_event", "data": {}},
        )
        logger.info(
            f"[TRIGGER] Command: {' '.join(cmd)}", extra={"event": "trigger_event", "data": {}}
        )
        if session_id:
            logger.info(
                f"[TRIGGER] Resuming session: {session_id}",
                extra={"event": "trigger_event", "data": {}},
            )

        # Execute in background thread. Non-Codex-MCP direct messages are
        # intentionally left unread so the agent can read them via get_inbox.
        t = threading.Thread(
            target=_run_agent_subprocess,
            args=(
                recipient,
                cmd,
                "Direct trigger from Hub",
                transport,
                is_http,
                env_vars,
                prompt,
                session_id,
            ),
            daemon=True,
        )
        t.start()

    return callback


def main() -> None:
    """CLI entry point for watchdog."""
    from .logging_handlers import _configure_logging

    load_dotenv()
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
                logger.error(
                    "Error: --auto-ping without --agent requires an active session. "
                    "Run: agentweave init",
                    extra={"event": "watchdog_error", "data": {}},
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
        logger.info(
            f"[PING] Auto-ping enabled for: {', '.join(agents_to_ping)}",
            extra={"event": "ping_event", "data": {}},
        )
        if args.retry_after:
            logger.info(
                f"[PING] Retry after: {int(args.retry_after)}s",
                extra={"event": "ping_event", "data": {}},
            )

    # Always enable direct trigger callback for HTTP transport
    # This allows Hub UI "Send Message" to work
    callbacks.append(
        _make_direct_trigger_callback(transport=watchdog.transport, watchdog_instance=watchdog)
    )
    logger.info(
        "[TRIGGER] Direct trigger handler enabled (for Hub UI messages)",
        extra={"event": "trigger_event", "data": {}},
    )

    # On HTTP transport: push session config to the Hub so it knows the full
    # agent configuration (names, roles, yolo flags) without filesystem access.
    if watchdog.transport is not None and watchdog.transport.get_transport_type() == "http":
        from .session import Session as _Session

        _sess = _Session.load()
        if _sess:
            try:
                watchdog.transport.push_session(_sess.to_dict())
                logger.info(
                    f"[HUB] Session synced: {', '.join(_sess.agent_names)}",
                    extra={"event": "hub_event", "data": {}},
                )
            except Exception as _exc:
                logger.warning(
                    f"[WARN] Could not sync session with hub: {_exc}",
                    extra={"event": "watchdog_warn", "data": {}},
                )

        # Push roles config so Hub knows dev roles even after a restart
        try:
            import json as _json

            from .constants import ROLES_CONFIG_FILE

            if ROLES_CONFIG_FILE.exists():
                _roles = _json.loads(ROLES_CONFIG_FILE.read_text(encoding="utf-8"))
                watchdog.transport.push_roles_config(_roles)
                logger.info("[HUB] Roles config synced", extra={"event": "hub_event", "data": {}})
        except Exception as _exc:
            logger.warning(
                f"[WARN] Could not sync roles config with hub: {_exc}",
                extra={"event": "watchdog_warn", "data": {}},
            )

    # Combine all callbacks into one
    if callbacks:

        def combined_callback(event_type: str, data: Dict[str, Any]) -> None:
            for cb in callbacks:
                cb(event_type, data)

        watchdog.callback = combined_callback

    watchdog.start()


if __name__ == "__main__":
    main()
