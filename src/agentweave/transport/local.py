"""Local filesystem transport — wraps the existing .agentweave/ behavior."""

from typing import Any, Dict, List, Optional

from ..constants import (
    MESSAGES_ARCHIVE_DIR,
    MESSAGES_PENDING_DIR,
    TASKS_ACTIVE_DIR,
)
from ..jobs import Job, JobRun
from ..utils import load_json, now_iso, save_json
from .base import BaseTransport


class LocalTransport(BaseTransport):
    """Transport backed by the local .agentweave/ filesystem.

    This is the default transport when no transport.json is present.
    Behavior is identical to what MessageBus did before the transport layer
    was introduced — existing single-machine users see zero change.
    """

    def send_message(self, message_data: Dict[str, Any]) -> bool:
        msg_id = message_data.get("id", "unknown")
        filepath = MESSAGES_PENDING_DIR / f"{msg_id}.json"
        return save_json(filepath, message_data)

    def get_pending_messages(self, agent: str) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        if not MESSAGES_PENDING_DIR.exists():
            return result
        for filepath in MESSAGES_PENDING_DIR.glob("*.json"):
            data = load_json(filepath)
            if data and data.get("to") == agent:
                result.append(data)
        return sorted(result, key=lambda d: d.get("timestamp", ""))

    def archive_message(self, message_id: str) -> bool:
        pending_path = MESSAGES_PENDING_DIR / f"{message_id}.json"
        archive_path = MESSAGES_ARCHIVE_DIR / f"{message_id}.json"

        data = load_json(pending_path)
        if not data:
            return False

        data["read"] = True
        data["read_at"] = now_iso()
        save_json(archive_path, data)

        if pending_path.exists():
            pending_path.unlink()
            return True
        return False

    def send_task(self, task_data: Dict[str, Any]) -> bool:
        task_id = task_data.get("id", "unknown")
        filepath = TASKS_ACTIVE_DIR / f"{task_id}.json"
        return save_json(filepath, task_data)

    def get_active_tasks(self, agent: Optional[str] = None) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        if not TASKS_ACTIVE_DIR.exists():
            return result
        for filepath in TASKS_ACTIVE_DIR.glob("*.json"):
            data = load_json(filepath)
            if data and (agent is None or data.get("assignee") == agent):
                result.append(data)
        return sorted(result, key=lambda d: d.get("created_at", ""))

    def get_transport_type(self) -> str:
        return "local"

    # ------------------------------------------------------------------
    # AI Jobs
    # ------------------------------------------------------------------

    def create_job(self, job_data: Dict[str, Any]) -> Optional[str]:
        """Create a new AI job locally."""
        try:
            job = Job.create(
                name=job_data["name"],
                agent=job_data["agent"],
                message=job_data["message"],
                cron=job_data["cron"],
                session_mode=job_data.get("session_mode", "new"),
            )
            job.save()
            return job.id
        except (ValueError, KeyError):
            return None

    def list_jobs(self, agent: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all local jobs."""
        jobs = Job.list_all(agent=agent)
        return [job.to_dict() for job in jobs]

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a single job by ID with history."""
        job = Job.load(job_id)
        if not job:
            return None

        result = job.to_dict()
        # Include last 10 history entries
        history = JobRun.list_for_job(job_id, limit=10)
        result["history"] = [run.to_dict() for run in history]
        return result

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update job fields."""
        job = Job.load(job_id)
        if not job:
            return False

        # Update allowed fields
        if "name" in updates:
            job.name = updates["name"]
        if "message" in updates:
            job.message = updates["message"]
        if "cron" in updates:
            try:
                Job.validate_cron(updates["cron"])
                job.cron = updates["cron"]
                job.next_run = job.compute_next_run()
            except ValueError:
                return False
        if "session_mode" in updates:
            job.session_mode = updates["session_mode"]
        if "enabled" in updates:
            job.enabled = bool(updates["enabled"])

        return job.save()

    def delete_job(self, job_id: str) -> bool:
        """Delete a job and its history."""
        job = Job.load(job_id)
        if not job:
            return False
        return job.delete()

    def fire_job(self, job_id: str, trigger: str = "manual") -> bool:
        """Fire a job immediately by triggering the agent."""
        import threading

        job = Job.load(job_id)
        if not job or not job.enabled:
            return False

        # Record the run first
        try:
            run = job.record_run(status="fired", trigger=trigger)
        except Exception:
            return False

        # Trigger the agent in a background thread (non-blocking)
        import contextlib

        def _trigger() -> None:
            with contextlib.suppress(Exception):  # Error already logged
                self._do_fire_job(job, run, trigger)

        t = threading.Thread(target=_trigger, daemon=True)
        t.start()
        return True

    def _do_fire_job(self, job: Any, run: Any, trigger: str) -> None:
        """Actually fire the job by running the agent subprocess."""
        import logging
        import subprocess

        logger = logging.getLogger(__name__)

        # Determine session_id for resume mode
        session_id = None
        if job.session_mode == "resume":
            session_id = job.last_session_id

        # Build command: agentweave run <agent> "<message>"
        cmd = ["agentweave", "run", job.agent, job.message]
        if session_id:
            cmd.extend(["--session", session_id])

        logger.info(
            "job_firing",
            extra={
                "event": "job_firing",
                "data": {
                    "job_id": job.id,
                    "job_name": job.name,
                    "agent": job.agent,
                    "trigger": trigger,
                    "session_id": session_id,
                },
            },
        )

        try:
            # Run without waiting (fire and forget)
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:
            logger.error(f"Failed to fire job {job.id}: {e}")
            # Update run status to failed
            try:
                run.status = "failed"
                run.save()
            except Exception:
                pass
