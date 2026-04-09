"""Transport factory — reads .agentweave/transport.json and returns the active transport."""

from pathlib import Path
from typing import Optional

from ..constants import TRANSPORT_CONFIG_FILE
from ..utils import load_json
from .base import BaseTransport


def _find_transport_config() -> Optional[dict]:
    """Find and load transport.json by walking up from CWD.

    Searches CWD and every parent directory for .agentweave/transport.json.
    This allows the MCP server (started by an agent from any working directory)
    to find the project's transport config without requiring an exact CWD match.

    Returns None if no config is found in any ancestor directory.
    """
    # First try the standard relative path (fast path for CLI use)
    config = load_json(TRANSPORT_CONFIG_FILE)
    if config:
        return config

    # Walk up the directory tree — handles MCP server CWD != project dir
    try:
        current = Path.cwd()
    except (OSError, FileNotFoundError):
        # CWD may have been deleted (e.g., temp dir cleaned up)
        # Fall back to looking in common locations
        current = None

    if current:
        for directory in current.parents:
            candidate = directory / ".agentweave" / "transport.json"
            config = load_json(candidate)
            if config:
                return config

    return None


def get_transport() -> BaseTransport:
    """Return the configured transport, defaulting to LocalTransport.

    Searches the current directory and all ancestor directories for
    .agentweave/transport.json, so the MCP stdio server (which may run from
    any working directory) can still find the project's transport config.

    If no transport.json is found anywhere, LocalTransport is returned,
    preserving 100% of existing single-machine behavior.

    transport.json shape:
        {"type": "git", "remote": "origin", "branch": "agentweave/collab",
         "poll_interval": 10, "cluster": "alice"}
        {"type": "http", "url": "https://...", "api_key": "iaf_live_xxx", "project_id": "proj-abc"}

    The "cluster" key is optional. When set, outgoing messages are stamped with
    "{cluster}.{agent}" as the sender, and inbox filtering matches both
    "{cluster}.{agent}" and plain "{agent}" for backward compatibility.
    """
    config = _find_transport_config()
    if not config:
        from .local import LocalTransport

        return LocalTransport()

    transport_type = config.get("type", "local")

    if transport_type == "git":
        from .git import GitTransport

        return GitTransport(
            remote=config.get("remote", "origin"),
            branch=config.get("branch", "agentweave/collab"),
            poll_interval=int(config.get("poll_interval", 10)),
            cluster=config.get("cluster", ""),
        )
    elif transport_type == "http":
        from .http import HttpTransport

        transport = HttpTransport(
            url=config.get("url", ""),
            api_key=config.get("api_key", ""),
            project_id=config.get("project_id", ""),
        )
        # Sync local jobs to Hub on connect
        import contextlib

        with contextlib.suppress(Exception):  # Don't fail transport creation if sync fails
            transport.sync_local_jobs()
        return transport
    else:
        from .local import LocalTransport

        return LocalTransport()
