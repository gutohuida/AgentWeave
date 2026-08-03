"""Transport layer for AgentWeave.

Single-runtime (`openspec/changes/single-runtime`) removed local and git transport. HTTP, to a
locally-owned Hub, is the only transport.

Usage:
    from agentweave.transport import get_transport, BaseTransport

    t = get_transport()                          # reads .agentweave/transport.json
    t.send_message(message_data)
    pending = t.get_pending_messages("kimi")
"""

from .base import BaseTransport
from .config import get_transport
from .http import HttpTransport

__all__ = [
    "BaseTransport",
    "get_transport",
    "HttpTransport",
]
