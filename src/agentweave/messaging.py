"""Messaging system for AgentWeave."""

import logging
import re
from typing import Any, Dict, List, Optional

from .constants import MESSAGE_TYPES, MESSAGES_ARCHIVE_DIR, MESSAGES_PENDING_DIR, TransportType
from .locking import lock
from .utils import generate_id, load_json, now_iso, save_json, write_json_atomic

logger = logging.getLogger(__name__)

# S2: defense-in-depth id validation at the transport boundary.
# Message IDs are generated as 'msg-{8-hex}' so they always match this
# loose regex; the regex is tight enough to block '..', '/', '\\', and
# other path-traversal characters. We don't impose a length bound
# because generated IDs are short and we want the helper to be a
# permissive check, not a strict validation gate.
_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _check_id_safe(message_id: Any) -> None:
    """Raise ValueError if message_id is not a safe filesystem name.

    Defense in depth at the transport boundary: even if an upstream
    caller forgets to validate, we won't read or write a file outside
    the messages/ directory.
    """
    if not isinstance(message_id, str) or not _SAFE_ID_RE.match(message_id):
        raise ValueError(f"invalid message id: {message_id!r}")


class Message:
    """Represents a message between agents."""

    def __init__(self, data: Dict[str, Any]):
        """Initialize message with data."""
        self._data = data

    @property
    def id(self) -> str:
        """Get message ID."""
        return self._data.get("id", "unknown")

    @property
    def sender(self) -> str:
        """Get sender agent."""
        return self._data.get("from", "unknown")

    @property
    def recipient(self) -> str:
        """Get recipient agent."""
        return self._data.get("to", "unknown")

    @property
    def subject(self) -> str:
        """Get message subject."""
        return self._data.get("subject", "")

    @property
    def content(self) -> str:
        """Get message content."""
        return self._data.get("content", "")

    @property
    def message_type(self) -> str:
        """Get message type."""
        return self._data.get("type", "message")

    @property
    def timestamp(self) -> str:
        """Get timestamp."""
        return self._data.get("timestamp", "")

    @property
    def is_read(self) -> bool:
        """Check if message is read."""
        return self._data.get("read", False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self._data

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        lines = [
            f"## Message from {self.sender.upper()}",
            "",
            f"**To:** {self.recipient}",
            f"**Subject:** {self.subject or '(no subject)'}",
            f"**Time:** {self.timestamp}",
            f"**Type:** {self.message_type}",
            "",
            self.content,
            "",
        ]
        return "\n".join(lines)

    @classmethod
    def load(cls, message_id: str, pending: bool = True) -> Optional["Message"]:
        """Load message by ID."""
        _check_id_safe(message_id)
        if pending:
            filepath = MESSAGES_PENDING_DIR / f"{message_id}.json"
        else:
            filepath = MESSAGES_ARCHIVE_DIR / f"{message_id}.json"

        data = load_json(filepath)
        if data:
            return cls(data)
        return None

    def save(self, pending: bool = True) -> bool:
        """Save message to file."""
        _check_id_safe(self.id)
        if pending:
            filepath = MESSAGES_PENDING_DIR / f"{self.id}.json"
        else:
            filepath = MESSAGES_ARCHIVE_DIR / f"{self.id}.json"
        return save_json(filepath, self._data)

    def mark_read(self) -> bool:
        """Mark message as read and move to archive.

        Uses an atomic os.replace to move pending → archive first, then
        a tmp + os.replace in-place write of the read flag. Closes the
        two-step tear (write archive, unlink pending) that could leave
        a message in both directories on crash (M8, M9).
        """
        with lock(f"msg-archive-{self.id}"):
            _check_id_safe(self.id)
            pending_path = MESSAGES_PENDING_DIR / f"{self.id}.json"
            archive_path = MESSAGES_ARCHIVE_DIR / f"{self.id}.json"

            if not pending_path.exists():
                return False

            import os

            os.replace(pending_path, archive_path)

            data = load_json(archive_path) or {}
            data["read"] = True
            data["read_at"] = now_iso()
            result = write_json_atomic(archive_path, data)

            if result:
                logger.info(
                    "msg_read",
                    extra={
                        "event": "msg_read",
                        "data": {
                            "msg_id": self.id,
                            "agent": self.recipient,
                            "from": self.sender,
                        },
                    },
                )
            return result

    @classmethod
    def create(
        cls,
        sender: str,
        recipient: str,
        content: str,
        subject: str = "",
        message_type: str = "message",
        task_id: Optional[str] = None,
    ) -> "Message":
        """Create a new message."""
        if message_type not in MESSAGE_TYPES:
            message_type = "message"

        data = {
            "id": generate_id("msg"),
            "from": sender,
            "to": recipient,
            "subject": subject,
            "content": content,
            "type": message_type,
            "timestamp": now_iso(),
            "read": False,
            "task_id": task_id,
        }

        return cls(data)


class MessageBus:
    """Manages message routing and storage."""

    @staticmethod
    def send(message: Message) -> bool:
        """Send a message via the active transport."""
        from .transport import get_transport

        result = get_transport().send_message(message.to_dict())
        if result:
            logger.info(
                "msg_sent",
                extra={
                    "event": "msg_sent",
                    "data": {
                        "msg_id": message.id,
                        "subject": message.subject,
                        "from": message.sender,
                        "to": message.recipient,
                    },
                },
            )
        else:
            logger.error(
                "msg_send_failed",
                extra={
                    "event": "msg_send_failed",
                    "data": {
                        "msg_id": message.id,
                        "subject": message.subject,
                        "from": message.sender,
                        "to": message.recipient,
                    },
                },
            )
        return result

    @staticmethod
    def get_inbox(agent: str) -> List[Message]:
        """Get all pending messages for an agent via the active transport."""
        from .transport import get_transport

        data_list = get_transport().get_pending_messages(agent)
        return [Message(d) for d in data_list]

    @staticmethod
    def get_outbox(agent: str) -> List[Message]:
        """Get all sent messages from an agent."""
        messages = []

        # Check pending
        for filepath in MESSAGES_PENDING_DIR.glob("*.json"):
            data = load_json(filepath)
            if data and data.get("from") == agent:
                messages.append(Message(data))

        # Check archive
        for filepath in MESSAGES_ARCHIVE_DIR.glob("*.json"):
            data = load_json(filepath)
            if data and data.get("from") == agent:
                messages.append(Message(data))

        return sorted(messages, key=lambda m: m.timestamp)

    @staticmethod
    def mark_read(message_id: str) -> bool:
        """Mark a message as read via the active transport."""
        from .transport import get_transport

        t = get_transport()
        if t.get_transport_type() == TransportType.LOCAL:
            message = Message.load(message_id, pending=True)
            if message:
                return message.mark_read()
            return False
        return t.archive_message(message_id)
