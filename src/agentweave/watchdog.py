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
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

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
        self._last_context_posted: Dict[str, dict] = {}  # agent -> last context data posted to Hub
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
        print(f"[JOB] Firing {job.name} → {agent} (trigger: {trigger})")

        # Load env_vars from session config for claude_proxy agents
        env_vars = None
        from .session import Session

        session = Session.load()
        if session:
            runner_config = session.get_runner_config(agent)
            if runner_config.get("runner") == "claude_proxy" and runner_config.get("env_vars"):
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

                # Auto-trigger agent for messages from "user" (job triggers, direct triggers)
                sender = msg.get("from", "")
                recipient = msg.get("to", "")
                if sender == "user" and recipient:
                    # Skip messages already handled by _make_direct_trigger_callback
                    # (those with "Direct message from Hub" in subject)
                    subject = msg.get("subject", "")
                    if "Direct message from Hub" not in subject:
                        self._trigger_agent_from_message(recipient, msg)

        tasks = self.transport.get_active_tasks(self.agent or None)
        for task in tasks:
            task_id = task.get("id", "")
            if task_id and task_id not in self.known_tasks:
                self.known_tasks.add(task_id)
                self.callback("new_task", task)

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
            print(f"[PILOT] Skipping execution for pilot agent {agent} (manual control)")
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
            print(f"[SKIP] Cannot trigger {agent}: CLI not found", file=sys.stderr)
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
        print(f"[TRIGGER] Firing {agent} from Hub message (session: {session_id or 'new'})")

        # Load env_vars from session config for claude_proxy agents
        env_vars = None
        from .session import Session

        session = Session.load()
        if session:
            runner_config = session.get_runner_config(agent)
            if runner_config.get("runner") == "claude_proxy" and runner_config.get("env_vars"):
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
    Kimi uses --print (plain Python-repr events) or --wire (JSON-RPC 2.0) with --session for resumption.
    Claude/claude_proxy use --output-format stream-json --verbose with --resume.
    """
    from .session import Session

    runner_type = _get_runner_type(agent)
    rc = RUNNER_CONFIGS.get(runner_type, RUNNER_CONFIGS["native"])

    if runner_type == "kimi":
        # Use wire mode for JSON-RPC streaming with context usage reporting
        cmd = ["kimi", "--wire"]
        if session_id:
            cmd += ["--session", session_id]
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
    from .constants import ROLES_DIR
    from .roles import get_agent_roles

    version_comment = f"AgentWeave v{__version__}"
    lines = []
    # Start with HTML comments (Kimi expects this format, not markdown headers)
    lines.append(f"<!-- Auto-generated by {version_comment} on trigger from Hub -->")
    lines.append(f"<!-- Context for {agent} — tells you who you are in this session -->")
    lines.append("")

    # --- Identity section ---
    lines.append(f"# You are {agent}")
    lines.append("")
    agent_roles = get_agent_roles(agent)
    if agent_roles:
        lines.append("Role(s): " + ", ".join(agent_roles))
    else:
        lines.append("(No specific role assigned)")
    lines.append("")

    # --- Team Directory ---
    lines.append("## Team")
    lines.append("")
    for ag in session.agent_names:
        runner_type = session.get_runner_config(ag).get("runner", "native")
        display_model = {
            "claude": "Claude",
            "claude_proxy": session.get_runner_config(ag).get("model", "Claude Proxy"),
            "kimi": "Kimi",
            "manual": "Manual",
        }.get(runner_type, runner_type.title())

        ag_roles = get_agent_roles(ag)
        roles_str = ", ".join(ag_roles) if ag_roles else "no role"
        marker = " **← YOU**" if ag == agent else ""
        lines.append(f"- **{ag}** ({display_model}): {roles_str}{marker}")
    lines.append("")

    # --- Role Guide(s) ---
    if agent_roles:
        lines.append("## Your Responsibilities")
        lines.append("")
        for role_id in agent_roles:
            role_file = ROLES_DIR / f"{role_id}.md"
            if role_file.exists():
                try:
                    role_content = role_file.read_text(encoding="utf-8").strip()
                    # Add role content without the header (we already have one)
                    lines.append(role_content)
                    lines.append("")
                except Exception:
                    lines.append(f"- Role `{role_id}` (content unavailable)")
            else:
                lines.append(
                    f"- Role `{role_id}` (guide not found at .agentweave/roles/{role_id}.md)"
                )
        lines.append("")

    # --- Quick Start ---
    lines.append("## Quick Start")
    lines.append("")
    lines.append(f'1. Check inbox: `get_inbox("{agent}")`')
    lines.append("2. List tasks: `list_tasks()`")
    lines.append("3. Read current focus: `.agentweave/shared/context.md`")
    lines.append("")

    return "\n".join(lines) + "\n"


def _load_triggered_ids(max_age_hours: int = 24) -> Set[str]:
    """Load recently-triggered direct-trigger message IDs from disk.

    Returns IDs whose timestamp is within max_age_hours. Also rewrites the file
    without expired entries so it doesn't grow unboundedly.
    """
    if not TRIGGERED_DIRECT_FILE.exists():
        return set()
    try:
        data: Dict[str, str] = json.loads(TRIGGERED_DIRECT_FILE.read_text())
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
                existing = json.loads(TRIGGERED_DIRECT_FILE.read_text())
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
        print(f"[SKIP] {agent} is already running, skipping spawn", file=sys.stderr)
        return

    try:
        _do_run_agent_subprocess(
            agent, cmd, subject, transport, is_http, env_vars, prompt, known_session_id
        )
    finally:
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
    # Detect wire mode: --wire flag in cmd indicates JSON-RPC bidirectional mode
    is_wire_mode = is_kimi and "--wire" in cmd

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

    session_id: Optional[str] = known_session_id
    # Mutable container so the stderr thread can read the latest session_id
    session_id_ref: List[Optional[str]] = [known_session_id]
    # Collect all stdout lines for Kimi session ID extraction (print mode only)
    kimi_stdout_lines: List[str] = []
    # Select appropriate parser based on mode
    kimi_parser: Optional[Any] = None
    if is_wire_mode:
        kimi_parser = _KimiWireParser()
    elif is_kimi:
        kimi_parser = _KimiParser()

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

        # Wire mode requires bidirectional stdin/stdout communication
        stdin_config = subprocess.PIPE if is_wire_mode else subprocess.DEVNULL

        proc = subprocess.Popen(
            run_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=stdin_config,
            text=True,
            bufsize=1,
            env=proc_env,
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

            if is_wire_mode and kimi_parser is not None:
                # Parse Kimi's JSON-RPC wire mode events
                readable_lines = kimi_parser.feed(line)
                # Close stdin on TurnEnd — clean signal that kimi finished this turn
                if kimi_parser.is_turn_ended() and proc.stdin and not proc.stdin.closed:
                    with contextlib.suppress(OSError):
                        proc.stdin.close()  # type: ignore[union-attr]
                # Extract context usage from StatusUpdate events
                wire_context_usage = kimi_parser.get_context_usage()
                if wire_context_usage is not None:
                    usage_data_for_context = wire_context_usage
                # Check for compaction events - only reset on transition into compaction
                is_in_compaction = kimi_parser.is_in_compaction()
                if is_in_compaction and not was_in_compaction:
                    _reset_context_usage(agent)
                was_in_compaction = is_in_compaction
                # Capture session ID from TurnEnd events
                # Always update — Kimi may create a new session even when resuming with --session
                wire_session_id = kimi_parser.get_session_id()
                if wire_session_id:
                    session_id = wire_session_id
                    session_id_ref[0] = wire_session_id
            elif is_kimi:
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
                readable_lines, usage_data = _parse_claude_stream_line(line)
                # Capture usage data from result messages for context monitoring
                if usage_data:
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

        # Write context usage if we captured usage data (Claude/claude_proxy or Kimi wire mode)
        if not is_kimi and usage_data_for_context and proc.returncode == 0:
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

        # Write context usage for Kimi wire mode (uses context_usage ratio instead of input_tokens)
        if is_wire_mode and usage_data_for_context and proc.returncode == 0:
            ctx_data = _write_context_usage_from_wire(agent, usage_data_for_context)
            if is_http and ctx_data:
                with contextlib.suppress(Exception):
                    transport.post_context_usage(agent, ctx_data)

        return proc.returncode or 0

    try:
        returncode = _run_cmd(cmd, session_id)

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

    # Sync session_id from cross-thread reference — the stderr drain thread may
    # have captured the ID from Kimi's "To resume this session: kimi -r <uuid>"
    # line even when the wire-mode TurnEnd event did not include a session_id.
    if session_id is None and session_id_ref[0] is not None:
        session_id = session_id_ref[0]

    # Extract Kimi session ID from collected stdout lines (post-exit) for print mode
    # Wire mode captures session ID from TurnEnd events in real-time
    if is_kimi and not is_wire_mode and session_id is None and kimi_stdout_lines:
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

    # Wire mode: log if we captured session ID from TurnEnd event
    if is_wire_mode and session_id:
        logger.info(
            "watchdog_kimi_wire_session_found",
            extra={
                "event": "watchdog_kimi_wire_session_found",
                "data": {"session_id": session_id, "method": "TurnEnd_event"},
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

        # Check if agent is in pilot mode - skip auto-execution
        from .session import Session as _Session

        _sess = _Session.load()
        if _sess and _sess.get_agent_pilot(recipient):
            logger.debug(
                "agent_ping_skipped_pilot",
                extra={
                    "event": "agent_ping_skipped_pilot",
                    "data": {"agent": recipient, "msg_id": msg_id, "reason": "pilot mode"},
                },
            )
            print(f"[PILOT] Skipping ping for pilot agent {recipient} (manual control)")
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
            print(f"[PILOT] Skipping direct trigger for pilot agent {recipient} (manual control)")
            return

        # Extract optional session ID from content tag, then discard raw content.
        # We do NOT pass raw content directly as the prompt — agents need to go through
        # their normal get_inbox flow so that output capture (MCP tool events, stream-json
        # events) works correctly.  The message stays unread in the DB so the agent can
        # retrieve it via get_inbox.  The seen-set above prevents re-triggering within
        # this watchdog session.
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
    callbacks.append(
        _make_direct_trigger_callback(transport=watchdog.transport, watchdog_instance=watchdog)
    )
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
