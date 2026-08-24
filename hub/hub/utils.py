"""Shared utilities for the Hub package."""

import uuid
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

#: How many hex characters an id segment carries. Twelve, widened from eight on 2026-08-24.
#:
#: Eight hex characters is 32 bits, which puts the birthday bound at roughly 77,000 rows before a
#: collision is more likely than not — and `event_logs` and `agent_outputs` are both append-only
#: with nothing that prunes them, so they cross that on an ordinary week of use. Twelve moves the
#: bound to roughly 800 million, which those tables will not reach.
#:
#: No migration: every id column is already `String(64)`, and the segment is only ever generated,
#: never parsed, so ids written at eight characters keep working unchanged alongside new ones.
_ID_HEX_CHARS = 12


def short_id() -> str:
    """Return a 12-character random hex ID segment."""
    return uuid.uuid4().hex[:_ID_HEX_CHARS]


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
