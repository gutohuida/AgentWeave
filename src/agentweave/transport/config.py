"""Transport factory — reads .agentweave/transport.json and returns the active transport."""

import os
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
    """Return the configured HTTP transport.

    Single-runtime (`openspec/changes/single-runtime`) removed local and git transport:
    AgentWeave is a locally-installed app whose CLI always talks to its own co-located Hub over
    HTTP. There is no single-machine no-Hub fallback left to default to.

    Searches the current directory and ancestors for the nearest AgentWeave project's
    .agentweave/transport.json, so the MCP stdio server (which may run from a project
    subdirectory) can still find the correct config.

    transport.json shape:
        {"type": "http", "url": "https://...", "api_key": "iaf_live_xxx", "project_id": "proj-abc"}

    Raises RuntimeError if no transport.json is found and the process is not a Hub-owned run
    (AW_RUN_TOKEN unset) — there is nothing left to fall back to.
    """
    # Hub-owned runs use their short-lived capability directly and must not load or
    # depend on a project API key from transport.json.
    run_token = os.environ.get("AW_RUN_TOKEN", "").strip()
    if run_token:
        from .http import HttpTransport

        return HttpTransport(
            url=os.environ.get("HUB_URL", "http://127.0.0.1:8000"),
            api_key="",
            project_id="",
        )

    found = _find_transport_config()
    if not found:
        raise RuntimeError(
            "No transport configured and no AW_RUN_TOKEN present. Local/git transport were "
            "removed; configure HTTP transport (.agentweave/transport.json) or run within a "
            "Hub-owned run."
        )
    config, config_path = found

    transport_type = config.get("type", "http")
    if transport_type != "http":
        raise RuntimeError(
            f"Unsupported transport type {transport_type!r} in {config_path}. Only 'http' is "
            "supported; local/git transport were removed."
        )

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
