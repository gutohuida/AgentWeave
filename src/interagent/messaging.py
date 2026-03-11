"""Messaging system for InterAgent."""

from typing import Any, Dict, List, Optional

from .constants import MESSAGES_PENDING_DIR, MESSAGES_ARCHIVE_DIR, MESSAGE_TYPES
from .utils import load_json, save_json, generate_id, now_iso


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
        if pending:
            filepath = MESSAGES_PENDING_DIR / f"{self.id}.json"
        else:
            filepath = MESSAGES_ARCHIVE_DIR / f"{self.id}.json"
        return save_json(filepath, self._data)

    def mark_read(self) -> bool:
        """Mark message as read and move to archive."""
        from .eventlog import log_event
        pending_path = MESSAGES_PENDING_DIR / f"{self.id}.json"
        archive_path = MESSAGES_ARCHIVE_DIR / f"{self.id}.json"

        self._data["read"] = True
        self._data["read_at"] = now_iso()

        save_json(archive_path, self._data)

        if pending_path.exists():
            pending_path.unlink()
            log_event("msg_read", msg_id=self.id, agent=self.recipient, **{"from": self.sender})
            return True
        return False

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
        from .eventlog import log_event
        result = get_transport().send_message(message.to_dict())
        if result:
            log_event(
                "msg_sent",
                msg_id=message.id,
                subject=message.subject,
                **{"from": message.sender, "to": message.recipient},
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
        if t.get_transport_type() == "local":
            message = Message.load(message_id, pending=True)
            if message:
                return message.mark_read()
            return False
        return t.archive_message(message_id)
