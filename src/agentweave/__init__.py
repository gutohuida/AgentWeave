"""
AgentWeave - Multi-agent AI collaboration framework.

File-based protocol for N AI agents (Claude, Kimi, Gemini, Codex, etc.)
to collaborate through a shared .agentweave/ directory.
"""

try:
    from importlib.metadata import PackageNotFoundError as _PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    try:
        __version__ = _pkg_version("agentweave-ai")
    except _PackageNotFoundError:
        __version__ = _pkg_version("agentweave")
except _PackageNotFoundError:
    # Reached only when no package metadata exists (e.g. running straight from a
    # source checkout). Deliberately not a real release number — a hardcoded
    # version here silently goes stale and then misreports itself as a release.
    __version__ = "0.0.0+dev"
__author__ = "AgentWeave Team"

from .cli import main
from .roles import (
    add_role_to_agent,
    get_agent_roles,
    get_available_roles,
    remove_role_from_agent,
    set_agent_roles,
)
from .session import Session
from .task import Task, TaskStatus

__all__ = [
    "main",
    "Session",
    "Task",
    "TaskStatus",
    "get_agent_roles",
    "add_role_to_agent",
    "remove_role_from_agent",
    "set_agent_roles",
    "get_available_roles",
]
