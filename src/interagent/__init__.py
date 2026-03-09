"""
InterAgent - A framework for Claude Code and Kimi Code collaboration.

This package provides tools for managing inter-agent collaboration through
structured protocols, task delegation, and shared state.
"""

__version__ = "0.2.0"
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
