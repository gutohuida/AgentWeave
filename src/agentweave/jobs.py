"""AI Jobs - scheduled recurring agent tasks for AgentWeave."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import JOBS_DIR, JOBS_HISTORY_DIR
from .locking import lock
from .utils import generate_id, load_json, now_iso, save_json

logger = logging.getLogger(__name__)

# Optional croniter import (only required for [jobs] extra)
try:
    from croniter import CroniterBadCronError, croniter  # type: ignore[import-untyped]

    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False
    CroniterBadCronError = ValueError  # type: ignore


@dataclass
class JobRun:
    """Represents a single job execution."""

    id: str
    job_id: str
    fired_at: str
    status: str  # "fired" or "failed"
    trigger: str  # "scheduled" or "manual"
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "fired_at": self.fired_at,
            "status": self.status,
            "trigger": self.trigger,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobRun":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            job_id=data["job_id"],
            fired_at=data["fired_at"],
            status=data["status"],
            trigger=data["trigger"],
            session_id=data.get("session_id"),
        )

    def save(self) -> bool:
        """Save this job run to history directory."""
        history_dir = JOBS_HISTORY_DIR / self.job_id
        filepath = history_dir / f"{self.fired_at}.json"
        return save_json(filepath, self.to_dict())

    @classmethod
    def list_for_job(cls, job_id: str, limit: int = 100) -> List["JobRun"]:
        """List job runs for a job, sorted by fired_at descending, with pruning.

        Args:
            job_id: The job ID to list runs for
            limit: Maximum number of entries to keep (oldest beyond limit are pruned)

        Returns:
            List of JobRun objects, sorted by fired_at descending (newest first)
        """
        history_dir = JOBS_HISTORY_DIR / job_id
        if not history_dir.exists():
            return []

        # Get all history files sorted by filename (ISO timestamp)
        files = sorted(history_dir.glob("*.json"), reverse=True)

        runs = []
        for i, filepath in enumerate(files):
            if i < limit:
                data = load_json(filepath)
                if data:
                    runs.append(cls.from_dict(data))
            else:
                # Prune old entries beyond limit
                import contextlib

                with contextlib.suppress(OSError):
                    filepath.unlink()

        return runs


@dataclass
class Job:
    """Represents an AI Job - a scheduled recurring task for an agent."""

    id: str
    name: str
    agent: str
    message: str
    cron: str
    session_mode: str = "new"  # "new" or "resume"
    enabled: bool = True
    created_at: str = ""
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    source: str = "local"  # "local" or "hub"
    synced: bool = False
    last_session_id: Optional[str] = None  # For resume mode

    def __post_init__(self) -> None:
        """Set default created_at if not provided."""
        if not self.created_at:
            self.created_at = now_iso()

    @property
    def job_file(self) -> Path:
        """Get the file path for this job."""
        return JOBS_DIR / f"{self.id}.json"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "agent": self.agent,
            "message": self.message,
            "cron": self.cron,
            "session_mode": self.session_mode,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
            "source": self.source,
            "synced": self.synced,
            "last_session_id": self.last_session_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        """Create a Job from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            agent=data["agent"],
            message=data["message"],
            cron=data["cron"],
            session_mode=data.get("session_mode", "new"),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", ""),
            last_run=data.get("last_run"),
            next_run=data.get("next_run"),
            run_count=data.get("run_count", 0),
            source=data.get("source", "local"),
            synced=data.get("synced", False),
            last_session_id=data.get("last_session_id"),
        )

    @staticmethod
    def validate_cron(cron: str) -> None:
        """Validate a cron expression.

        Args:
            cron: The cron expression to validate

        Raises:
            ValueError: If the cron expression is invalid
        """
        if not CRONITER_AVAILABLE:
            raise ValueError(
                "croniter is required for cron validation. "
                "Install with: pip install agentweave-ai[jobs]"
            )

        try:
            croniter(cron)
        except CroniterBadCronError as e:
            raise ValueError(f"Invalid cron expression: {e}") from e

    def compute_next_run(self) -> Optional[str]:
        """Compute the next run time based on cron expression.

        Returns:
            ISO timestamp of next scheduled run, or None if croniter unavailable
        """
        if not CRONITER_AVAILABLE:
            return None

        try:
            itr = croniter(self.cron, datetime.now(timezone.utc))
            next_dt = itr.get_next(datetime)
            return next_dt.isoformat()
        except CroniterBadCronError:
            return None

    def save(self) -> bool:
        """Save job to file.

        Returns:
            True if saved successfully, False otherwise
        """
        with lock("jobs"):
            return save_json(self.job_file, self.to_dict())

    @classmethod
    def load(cls, job_id: str) -> Optional["Job"]:
        """Load job by ID.

        Args:
            job_id: The job ID to load

        Returns:
            Job instance or None if not found
        """
        # Validate job_id format to prevent path traversal
        if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
            return None

        filepath = JOBS_DIR / f"{job_id}.json"
        data = load_json(filepath)

        if data:
            return cls.from_dict(data)
        return None

    @classmethod
    def create(
        cls,
        name: str,
        agent: str,
        message: str,
        cron: str,
        session_mode: str = "new",
    ) -> "Job":
        """Create a new job.

        Args:
            name: Human-readable job name
            agent: Target agent name
            message: Message to send to the agent
            cron: Cron expression for scheduling
            session_mode: "new" or "resume"

        Returns:
            New Job instance

        Raises:
            ValueError: If cron expression is invalid
        """
        # Validate cron
        cls.validate_cron(cron)

        job = cls(
            id=generate_id("job"),
            name=name,
            agent=agent,
            message=message,
            cron=cron,
            session_mode=session_mode if session_mode in ("new", "resume") else "new",
            created_at=now_iso(),
        )

        # Compute initial next_run
        job.next_run = job.compute_next_run()

        return job

    @classmethod
    def list_all(cls, agent: Optional[str] = None) -> List["Job"]:
        """List all jobs, optionally filtered by agent.

        Args:
            agent: Optional agent name to filter by

        Returns:
            List of Job instances
        """
        jobs: List[Job] = []

        if not JOBS_DIR.exists():
            return jobs

        for filepath in JOBS_DIR.glob("*.json"):
            data = load_json(filepath)
            if data:
                job = cls.from_dict(data)
                if agent is None or job.agent == agent:
                    jobs.append(job)

        return jobs

    def delete(self) -> bool:
        """Delete job and its history.

        Returns:
            True if deleted successfully, False otherwise
        """
        with lock("jobs"):
            # Delete job file
            try:
                if self.job_file.exists():
                    self.job_file.unlink()
            except OSError as e:
                logger.error(f"Failed to delete job file: {e}")
                return False

            # Delete history
            history_dir = JOBS_HISTORY_DIR / self.id
            if history_dir.exists():
                try:
                    for filepath in history_dir.glob("*.json"):
                        filepath.unlink()
                    history_dir.rmdir()
                except OSError as e:
                    logger.error(f"Failed to delete job history: {e}")

            return True

    def record_run(
        self,
        status: str = "fired",
        trigger: str = "scheduled",
        session_id: Optional[str] = None,
    ) -> JobRun:
        """Record a job execution and update job stats.

        Args:
            status: "fired" or "failed"
            trigger: "scheduled" or "manual"
            session_id: The session ID used for this run

        Returns:
            The created JobRun
        """
        fired_at = now_iso()

        # Update job stats
        self.last_run = fired_at
        self.run_count += 1
        self.last_session_id = session_id
        self.next_run = self.compute_next_run()
        self.save()

        # Create and save run record
        run = JobRun(
            id=generate_id("run"),
            job_id=self.id,
            fired_at=fired_at,
            status=status,
            trigger=trigger,
            session_id=session_id,
        )
        run.save()

        logger.info(
            "job_fired",
            extra={
                "event": "job_fired",
                "data": {
                    "job_id": self.id,
                    "job_name": self.name,
                    "agent": self.agent,
                    "trigger": trigger,
                    "status": status,
                },
            },
        )

        return run

    def should_fire(self) -> bool:
        """Check if the job should fire based on cron schedule.

        Returns:
            True if the job should fire now, False otherwise
        """
        if not self.enabled:
            return False

        if not CRONITER_AVAILABLE:
            return False

        try:
            now = datetime.now(timezone.utc)
            itr = croniter(self.cron, now)
            prev_run = itr.get_prev(datetime)

            # Check if we're within the current minute
            time_since_prev = (now - prev_run).total_seconds()

            # Must be within current minute (0-60 seconds since last cron tick)
            if time_since_prev > 60:
                return False

            # Guard against double-firing: skip if last_run is within 50 seconds
            if self.last_run:
                last_run_dt = datetime.fromisoformat(self.last_run)
                # Ensure timezone-aware for comparison
                if last_run_dt.tzinfo is None:
                    last_run_dt = last_run_dt.replace(tzinfo=timezone.utc)
                time_since_last = (now - last_run_dt).total_seconds()
                if time_since_last < 50:
                    return False

            return True

        except (CroniterBadCronError, ValueError):
            return False
