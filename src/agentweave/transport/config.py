"""Transport factory — reads .agentweave/transport.json and returns the active transport."""

from pathlib import Path
from typing import Optional

from ..constants import TRANSPORT_CONFIG_FILE
from ..utils import generate_id, load_json, save_json
from .base import BaseTransport


def _ensure_spec_source_id(config: dict, path: Path) -> str:
    """Return this workspace's stable, non-secret spec-sync source ID.

    Generated once (at `transport setup --type http` or lazily on first use
    by an existing config) and persisted at `path`, the exact transport.json
    this config was loaded from — which may be in a parent directory when
    called from a nested CWD. Contains no credential or machine-identifying
    path, just a random token the Hub uses to tell apart snapshots from
    different checkouts of the same project.
    """
    source_id = config.get("spec_source_id")
    if isinstance(source_id, str) and source_id:
        return source_id
    source_id = generate_id("spec-src", uuid_length=16)
    config["spec_source_id"] = source_id
    save_json(path, config)
    return source_id


def _find_transport_config() -> Optional[tuple]:
    """Find and load transport.json by walking up from CWD.

    Searches CWD and parent directories for the nearest AgentWeave project's
    .agentweave/transport.json. An .agentweave directory is a project boundary:
    if the nearest one has no transport config, do not inherit a transport from
    an unrelated parent project.

    This allows the MCP server (started from a subdirectory) to find its
    project's transport config without leaking configuration into nested
    AgentWeave projects.

    Returns (config, path) for the first match, or None if no config is
    found in any ancestor directory.
    """
    # First try the standard relative path (fast path for CLI use)
    config = load_json(TRANSPORT_CONFIG_FILE)
    if config:
        return config, TRANSPORT_CONFIG_FILE
    if TRANSPORT_CONFIG_FILE.parent.exists():
        return None

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
                return config, candidate
            if candidate.parent.exists():
                return None

    return None


def get_transport() -> BaseTransport:
    """Return the configured transport, defaulting to LocalTransport.

    Searches the current directory and ancestors for the nearest AgentWeave
    project's .agentweave/transport.json, so the MCP stdio server (which may
    run from a project subdirectory) can still find the correct config.

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
    found = _find_transport_config()
    if not found:
        from .local import LocalTransport

        return LocalTransport()
    config, config_path = found

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
            source_id=_ensure_spec_source_id(config, config_path),
        )
        # Sync local jobs to Hub on connect
        import contextlib

        with contextlib.suppress(Exception):  # Don't fail transport creation if sync fails
            transport.sync_local_jobs()
        return transport
    else:
        from .local import LocalTransport

        return LocalTransport()
