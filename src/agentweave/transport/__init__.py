"""Transport layer for AgentWeave.

The transport layer abstracts message and task I/O behind a BaseTransport
interface, enabling single-machine (local), cross-machine (git), and
future hub-based (http/MCP) collaboration without changing CLI commands.

Usage:
    from agentweave.transport import get_transport, BaseTransport

    t = get_transport()                          # reads .agentweave/transport.json
    t.send_message(message_data)
    pending = t.get_pending_messages("kimi")

Transport selection (auto, based on .agentweave/transport.json):
    No transport.json  →  LocalTransport   (default, unchanged behavior)
    type: "git"        →  GitTransport     (orphan branch, cross-machine)
    type: "http"       →  HttpTransport    (AgentWeave Hub, not yet implemented)
"""

from .base import BaseTransport
from .config import get_transport
from .git import GitTransport
from .http import HttpTransport
from .local import LocalTransport

__all__ = [
    "BaseTransport",
    "get_transport",
    "LocalTransport",
    "GitTransport",
    "HttpTransport",
]
