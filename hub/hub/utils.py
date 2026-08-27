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


#: The only severities the operator's views recognise (`EventRow.tsx`'s `SEVERITY_CHIP`,
#: `ActivityLog.tsx`'s `SEVERITY_FILTERS`). Anything else — a caller's typo, an external
#: `POST /logs` request, the historical `"warning"` spelling — is normalised to `"warn"` rather
#: than written through, so an unrecognised spelling can never reach the operator unfiltered.
_KNOWN_SEVERITIES = frozenset({"info", "warn", "error", "debug"})


async def persist_event(
    session: AsyncSession,
    project_id: str,
    event_type: str,
    data: Optional[Dict[str, Any]] = None,
    agent: Optional[str] = None,
    severity: str = "info",
    loop_id: Optional[str] = None,
    commit: bool = True,
) -> str:
    """Write one row to event_logs and return the (normalised) severity written.

    Import is deferred to avoid circular imports.

    `loop_id` (design D13, task A4.1): the caller states it explicitly when the event is about a
    specific loop — never re-derived from `data` here, so a payload shaped differently than
    expected cannot silently leave the column NULL.

    `commit=False` (`every-run-knows-its-task`, task 4.8) is for a caller that is itself called
    from inside another function's uncommitted transaction — `resolve_divergences_for_task`,
    reached from `apply_transition` before its own caller commits. Committing here would land the
    caller's still-in-flight write early, ahead of the "the caller commits" contract
    `apply_transition` states of itself. Every other caller keeps the default: an event usually is
    the transaction, not a passenger in someone else's.
    """
    from .db.models import EventLog

    normalised_severity = severity if severity in _KNOWN_SEVERITIES else "warn"

    entry = EventLog(
        id=f"evt-{short_id()}",
        project_id=project_id,
        event_type=event_type,
        agent=agent,
        loop_id=loop_id,
        data=data or {},
        severity=normalised_severity,
    )
    session.add(entry)
    if commit:
        await session.commit()
    return normalised_severity
