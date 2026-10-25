"""Choosing which `context_warning` row to report as *the* context reading.

One definition, because the rule is subtle and two surfaces need it: the agent roster reports a
reading per agent, and a conversation reports its own. A second copy would drift, and the drift
would be invisible — both would still return a plausible percentage.
"""

from typing import Any, Callable, Dict, Iterable, List

from sqlalchemy import bindparam, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Agent, Conversation, EventLog


def usable_context_reading(rows: List[Any]) -> Any:
    """Pick the reading to report from a set of `context_warning` rows, newest first.

    Taking the newest row alone is what made Claude agents report nothing for 329 samples: the
    end-of-turn message reports a context window with no token count, so the last row to arrive
    routinely carried no usable percentage and hid the complete one behind it.

    The newest row still wins whenever it carries a percentage. Otherwise the newest row **from
    the same provider session** that does is used — scoped to the session because a compaction or
    a fresh session resets usage, and reporting a pre-reset percentage as current would be worse
    than reporting none. An unscoped fallback would do exactly that.
    """
    if not rows:
        return None
    newest = rows[0]
    if not isinstance(newest, dict) or newest.get("percent") is not None:
        return newest
    session_id = newest.get("session_id")
    if session_id is None:
        return newest
    for row in rows[1:]:
        if (
            isinstance(row, dict)
            and row.get("percent") is not None
            and row.get("session_id") == session_id
        ):
            return row
    return newest


# --- Reading them back without reading the history (`the-app-stays-responsive-while-agents-run`,
# design D5). The roster and the conversation lists used to load every `context_warning` row the
# project ever recorded — 61% of `event_logs` on the operator's Hub — and decode all of them in
# Python to use one per agent. These read the newest row per agent or conversation, and the
# session fallback's rows, through the partial indexes declared on `EventLog`. The rule applied is
# still `usable_context_reading`'s; only which rows reach it changes.

CONTEXT_EVENT = "context_warning"

# Rendered as literals, not bound parameters: SQLite uses a partial index only when the query's
# WHERE names the index's own condition literally, and matches an expression index only against
# the identical expression. A bound `?` in either place silently falls back to a scan.
IS_CONTEXT_READING = EventLog.event_type == literal_column(f"'{CONTEXT_EVENT}'")
reading_conversation = func.json_extract(EventLog.data, literal_column("'$.conversation_id'"))
reading_session = func.json_extract(EventLog.data, literal_column("'$.session_id'"))
reading_percent = func.json_extract(EventLog.data, literal_column("'$.percent'"))


def _newest_data(*where: Any) -> Any:
    return (
        select(EventLog.data)
        .where(EventLog.project_id == bindparam("project_id"), IS_CONTEXT_READING, *where)
        .order_by(EventLog.timestamp.desc())
        .limit(1)
        .scalar_subquery()
    )


async def _usable(
    session: AsyncSession,
    project_id: str,
    newest: Dict[str, Any],
    scope: Callable[[str], Any],
) -> Dict[str, Any]:
    """Apply `usable_context_reading` to each key's newest row, fetching fallbacks only if needed.

    The fallback is needed only where the newest row carries no percentage but names a session.
    Its rows are read through the session index, newest first, stopping at the first with a
    percentage — the same row the full newest-first list would have yielded.
    """
    readings: Dict[str, Any] = {}
    for key, data in newest.items():
        if (
            not isinstance(data, dict)
            or data.get("percent") is not None
            or data.get("session_id") is None
        ):
            readings[key] = data
            continue
        fallback = (
            await session.execute(
                select(EventLog.data)
                .where(
                    EventLog.project_id == project_id,
                    IS_CONTEXT_READING,
                    reading_session == data["session_id"],
                    reading_percent.isnot(None),
                    scope(key),
                )
                .order_by(EventLog.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        readings[key] = usable_context_reading([data] + ([fallback] if fallback else []))
    return readings


async def context_reading_by_agent(
    session: AsyncSession, project_id: str, agent_names: Iterable[str]
) -> Dict[str, Any]:
    """Each named agent's context reading; agents with no reading are absent."""
    names = list(agent_names)
    if not names:
        return {}
    newest_rows = await session.execute(
        select(Agent.name, _newest_data(EventLog.agent == Agent.name)).where(
            Agent.project_id == project_id, Agent.name.in_(names)
        ),
        {"project_id": project_id},
    )
    newest = {name: data for name, data in newest_rows if data is not None}
    return await _usable(session, project_id, newest, lambda name: EventLog.agent == name)


async def context_reading_by_conversation(
    session: AsyncSession, project_id: str, conversation_ids: Iterable[str]
) -> Dict[str, Any]:
    """Each conversation's own context reading; conversations with none are absent.

    `context_warning` rows carry `data["conversation_id"]`, resolved when the reading is recorded
    (`output_recording.record_context_usage`).
    """
    ids = list(conversation_ids)
    if not ids:
        return {}
    # `+conversations.id`, not the bare column: the column's TEXT affinity would apply to the
    # comparison, and SQLite then refuses the expression index (which has none) and scans every
    # reading in the project. Unary `+` drops the affinity; the values compared are unchanged.
    conversation_id_without_affinity = literal_column(f"+{Conversation.__tablename__}.id")
    newest_rows = await session.execute(
        select(
            Conversation.id, _newest_data(reading_conversation == conversation_id_without_affinity)
        ).where(Conversation.id.in_(ids)),
        {"project_id": project_id},
    )
    newest = {conversation_id: data for conversation_id, data in newest_rows if data is not None}
    return await _usable(
        session, project_id, newest, lambda conversation_id: reading_conversation == conversation_id
    )
