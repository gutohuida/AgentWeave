"""Transport factory — reads .interagent/transport.json and returns the active transport."""

from .base import BaseTransport
from ..constants import TRANSPORT_CONFIG_FILE
from ..utils import load_json


def get_transport() -> BaseTransport:
    """Return the configured transport, defaulting to LocalTransport.

    If .interagent/transport.json does not exist, LocalTransport is returned,
    preserving 100% of existing single-machine behavior.

    transport.json shape:
        {"type": "git", "remote": "origin", "branch": "interagent/collab",
         "poll_interval": 10, "cluster": "alice"}
        {"type": "http", "url": "https://...", "api_key": "iaf_live_xxx", "project_id": "proj-abc"}

    The "cluster" key is optional. When set, outgoing messages are stamped with
    "{cluster}.{agent}" as the sender, and inbox filtering matches both
    "{cluster}.{agent}" and plain "{agent}" for backward compatibility.
    """
    config = load_json(TRANSPORT_CONFIG_FILE)
    if not config:
        from .local import LocalTransport
        return LocalTransport()

    transport_type = config.get("type", "local")

    if transport_type == "git":
        from .git import GitTransport
        return GitTransport(
            remote=config.get("remote", "origin"),
            branch=config.get("branch", "interagent/collab"),
            poll_interval=int(config.get("poll_interval", 10)),
            cluster=config.get("cluster", ""),
        )
    elif transport_type == "http":
        from .http import HttpTransport
        return HttpTransport(
            url=config.get("url", ""),
            api_key=config.get("api_key", ""),
            project_id=config.get("project_id", ""),
        )
    else:
        from .local import LocalTransport
        return LocalTransport()
