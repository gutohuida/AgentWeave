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
    loop_id: Optional[str] = None,
) -> None:
    """Write one row to event_logs. Import is deferred to avoid circular imports.

    `loop_id` (design D13, task A4.1): the caller states it explicitly when the event is about a
    specific loop — never re-derived from `data` here, so a payload shaped differently than
    expected cannot silently leave the column NULL.
    """
    from .db.models import EventLog

    entry = EventLog(
        id=f"evt-{short_id()}",
        project_id=project_id,
        event_type=event_type,
        agent=agent,
        loop_id=loop_id,
        data=data or {},
        severity=severity,
    )
    session.add(entry)
    await session.commit()
