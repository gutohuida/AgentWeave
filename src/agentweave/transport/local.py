"""Local filesystem transport — wraps the existing .agentweave/ behavior."""

from typing import Any, Dict, List, Optional

from ..constants import (
    MESSAGES_ARCHIVE_DIR,
    MESSAGES_PENDING_DIR,
    TASKS_ACTIVE_DIR,
)
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
