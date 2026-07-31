"""Shared agent-heartbeat status derivation."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from .db.models import AgentHeartbeat

HEARTBEAT_STALE_AFTER = timedelta(seconds=120)
STALLED_STATUS_MESSAGE = (
    "No heartbeat received for more than 2 minutes. The run may have stopped; "
    "check or restart the host watchdog."
)


def heartbeat_is_stale(
    heartbeat: AgentHeartbeat,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Return whether a heartbeat is older than the watchdog health window."""
    observed_at = heartbeat.timestamp
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    current_time = now or datetime.now(timezone.utc)
    return observed_at < current_time - HEARTBEAT_STALE_AFTER


def effective_heartbeat_status(
    heartbeat: Optional[AgentHeartbeat],
    *,
    now: Optional[datetime] = None,
) -> Tuple[str, Optional[str]]:
    """Convert an abandoned ``running`` heartbeat into an actionable state."""
    if heartbeat is None:
        return "idle", None
    if heartbeat.status == "running" and heartbeat_is_stale(heartbeat, now=now):
        return "stalled", STALLED_STATUS_MESSAGE
    return heartbeat.status, heartbeat.message
