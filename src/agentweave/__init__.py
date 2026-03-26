"""
AgentWeave - Multi-agent AI collaboration framework.

File-based protocol for N AI agents (Claude, Kimi, Gemini, Codex, etc.)
to collaborate through a shared .agentweave/ directory.
"""

try:
    from importlib.metadata import PackageNotFoundError as _PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("agentweave")
except _PackageNotFoundError:
    __version__ = "0.9.5"  # fallback during development / editable installs
__author__ = "AgentWeave Team"

from .cli import main
from .messaging import Message, MessageBus
from .session import Session
from .task import Task, TaskStatus

__all__ = [
    "main",
    "Session",
    "Task",
    "TaskStatus",
    "Message",
    "MessageBus",
]
