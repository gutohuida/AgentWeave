"""Stable per-Hub-instance identity, carried in every minted run credential.

Deliberately NOT a database row. The scenario this defends against
(`openspec/changes/2026-08-06-agent-messaging-delivery/design.md`, Decision 3) is a future
deployment where multiple Hub processes share one database — if the identity itself lived
in that shared database, every process reading the same row would appear to be the same
instance, defeating the point. Instead it is a small marker file on this process's own
local filesystem, read once at startup and cached, mirroring `bound_address.py`'s
module-global pattern for the same reason: `trigger_agent_directly` is called with no
FastAPI `Request` in flight, so nothing but a previously observed/loaded value is
available at that call site.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from pathlib import Path
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)

_instance_id: Optional[str] = None


def _marker_path() -> Optional[Path]:
    """Where the marker file belongs, or `None` if there is nowhere durable to put it.

    An in-memory sqlite database (`:memory:`, what the test suite uses) has no durable
    state at all — writing a marker file next to it would mean writing into whatever the
    process's current working directory happens to be, which is not this module's call to
    make. Treated the same as "nothing to persist": `load_or_create` mints a
    process-lifetime-only id instead.
    """
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
        if db_path == ":memory:":
            return None
        base_dir = os.path.dirname(db_path) or "."
    else:
        base_dir = "data"
    return Path(base_dir) / "instance_identity.json"


def load_or_create() -> str:
    """Read this Hub process's stable instance id from disk, minting one on first run."""
    global _instance_id
    path = _marker_path()
    if path is None:
        _instance_id = secrets.token_urlsafe(16)
        return _instance_id

    path.parent.mkdir(parents=True, exist_ok=True)

    instance_id: Optional[str] = None
    if path.exists():
        try:
            instance_id = json.loads(path.read_text(encoding="utf-8"))["instance_id"]
        except (json.JSONDecodeError, KeyError, OSError):
            logger.warning("Instance identity marker at %s is unreadable; minting a new one", path)

    if not instance_id:
        instance_id = secrets.token_urlsafe(16)
        path.write_text(json.dumps({"instance_id": instance_id}), encoding="utf-8")

    _instance_id = instance_id
    return instance_id


def get() -> Optional[str]:
    """Return the cached instance id. `None` until `load_or_create()` has run once."""
    return _instance_id
