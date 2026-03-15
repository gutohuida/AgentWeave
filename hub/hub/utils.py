"""Shared utilities for the Hub package."""

import uuid
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession


def short_id() -> str:
    """Return an 8-character random hex ID segment."""
    return str(uuid.uuid4())[:8]


async def persist_event(
    session: AsyncSession,
    project_id: str,
    event_type: str,
    data: Optional[Dict[str, Any]] = None,
    agent: Optional[str] = None,
    severity: str = "info",
) -> None:
    """Write one row to event_logs. Import is deferred to avoid circular imports."""
    from .db.models import EventLog

    entry = EventLog(
        id=f"evt-{short_id()}",
        project_id=project_id,
        event_type=event_type,
        agent=agent,
        data=data or {},
        severity=severity,
    )
    session.add(entry)
    await session.commit()
