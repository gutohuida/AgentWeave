"""Base transport interface for InterAgent."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseTransport(ABC):
    """Abstract base class for all transport backends.

    All message and task I/O goes through this interface, enabling
    LocalTransport (filesystem), GitTransport (orphan branch), and
    future McpTransport (InterAgent Hub) to be swapped transparently.
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
