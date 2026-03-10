"""
InterAgent - Multi-agent AI collaboration framework.

File-based protocol for N AI agents (Claude, Kimi, Gemini, Codex, etc.)
to collaborate through a shared .interagent/ directory.
"""

__version__ = "0.3.0"
__author__ = "InterAgent Team"

from .cli import main
from .session import Session
from .task import Task, TaskStatus
from .messaging import Message, MessageBus

__all__ = [
    "main",
    "Session",
    "Task",
    "TaskStatus",
    "Message",
    "MessageBus",
]
