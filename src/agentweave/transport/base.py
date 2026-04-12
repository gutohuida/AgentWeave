"""Base transport interface for AgentWeave."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseTransport(ABC):
    """Abstract base class for all transport backends.

    All message and task I/O goes through this interface, enabling
    LocalTransport (filesystem), GitTransport (orphan branch), and
    future McpTransport (AgentWeave Hub) to be swapped transparently.
    """

    @abstractmethod
    def send_message(self, message_data: Dict[str, Any]) -> bool:
        """Persist a message so the recipient's agent can receive it."""

    @abstractmethod
    def get_pending_messages(self, agent: str) -> List[Dict[str, Any]]:
        """Return all unread message dicts addressed to `agent`."""

    @abstractmethod
    def archive_message(self, message_id: str) -> bool:
        """Mark a message as read / archived."""

    @abstractmethod
    def send_task(self, task_data: Dict[str, Any]) -> bool:
        """Publish a task so the assignee's agent can receive it."""

    @abstractmethod
    def get_active_tasks(self, agent: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all active task dicts, optionally filtered by assignee."""

    @abstractmethod
    def get_transport_type(self) -> str:
        """Return transport identifier: 'local', 'git', or 'http'."""

    # ------------------------------------------------------------------
    # AI Jobs (optional, raises NotImplementedError if not supported)
    # ------------------------------------------------------------------

    def create_job(self, job_data: Dict[str, Any]) -> Optional[str]:
        """Create a new AI job. Returns job ID or None on failure."""
        raise NotImplementedError("Jobs not supported by this transport")

    def list_jobs(self, agent: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all jobs, optionally filtered by agent."""
        raise NotImplementedError("Jobs not supported by this transport")

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a single job by ID, including history."""
        raise NotImplementedError("Jobs not supported by this transport")

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update job fields (enabled, name, message, cron, session_mode)."""
        raise NotImplementedError("Jobs not supported by this transport")

    def delete_job(self, job_id: str) -> bool:
        """Delete a job and its history."""
        raise NotImplementedError("Jobs not supported by this transport")

    def fire_job(self, job_id: str, trigger: str = "manual") -> bool:
        """Fire a job immediately."""
        raise NotImplementedError("Jobs not supported by this transport")

    def push_session(self, session_data: Dict[str, Any]) -> bool:
        """Push session data to the backend (no-op on non-HTTP transports)."""
        return False

    def push_roles_config(self, roles_config: Dict[str, Any]) -> bool:
        """Push roles config to the backend (no-op on non-HTTP transports)."""
        return False

    def push_log(
        self,
        event_type: str,
        agent: str,
        data: Optional[Dict[str, Any]],
        severity: str,
    ) -> None:
        """Push a log event to the backend (no-op on non-HTTP transports)."""
        return

    def register_session(self, agent: str, session_id: str) -> Optional[Dict[str, Any]]:
        """Register a session ID for a pilot agent (no-op on non-HTTP transports)."""
        raise NotImplementedError("Session registration not supported by this transport")
