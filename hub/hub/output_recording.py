"""Shared agent-output / context-usage recording, used by both the self-report HTTP
endpoints (`POST /agents/{name}/output`, `.../context-usage` — the watchdog's path) and the
Hub's own direct-spawn output loop (`agent_trigger.py`). Factored out so a Hub-spawned run's
output is recorded through the exact same DB-write + SSE-broadcast shape a self-reporting
agent already produces — one path, not two that can drift.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import AgentOutput, EventLog
from .sse import sse_manager
from .utils import persist_event, short_id


async def record_agent_output(
    db: AsyncSession,
    project_id: str,
    agent: str,
    *,
    content: str,
    session_id: Optional[str],
    kind: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    sequence: Optional[int] = None,
) -> AgentOutput:
    """Persist one AgentOutput row and broadcast it, mirroring `POST .../output`."""
    is_new_session = False
    if session_id:
        count_result = await db.execute(
            select(AgentOutput.id)
            .where(
                AgentOutput.project_id == project_id,
                AgentOutput.agent == agent,
                AgentOutput.session_id == session_id,
            )
            .limit(1)
        )
        is_new_session = count_result.scalar() is None

    row = AgentOutput(
        id=f"out-{short_id()}",
        project_id=project_id,
        agent=agent,
        session_id=session_id,
        content=content,
        kind=kind,
        payload=payload,
        run_id=run_id,
        sequence=sequence,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    await sse_manager.broadcast(
        project_id,
        "agent_output",
        {
            "id": row.id,
            "agent": agent,
            "session_id": session_id,
            "content": content,
            "kind": kind,
            "payload": payload,
            "run_id": run_id,
            "sequence": sequence,
            "timestamp": row.timestamp.isoformat(),
        },
    )
    if is_new_session:
        await sse_manager.broadcast(
            project_id, "agent_session_changed", {"agent": agent, "session_id": session_id}
        )
    return row


async def record_context_usage(
    db: AsyncSession, project_id: str, agent: str, sample_payload: Dict[str, Any]
) -> str:
    """Persist a context-usage snapshot and broadcast it, mirroring `POST .../context-usage`.

    Returns "ok" or "ignored" (a strictly-older observation for the same agent).
    """
    payload = {**sample_payload, "agent": agent}
    latest_result = await db.execute(
        select(EventLog)
        .where(
            EventLog.project_id == project_id,
            EventLog.event_type == "context_warning",
            EventLog.agent == agent,
        )
        .order_by(EventLog.timestamp.desc())
        .limit(1)
    )
    latest = latest_result.scalars().first()
    if latest and isinstance(latest.data, dict):
        latest_observed = latest.data.get("observed_at")
        observed_at = payload.get("observed_at")
        if (
            isinstance(latest_observed, (int, float))
            and isinstance(observed_at, (int, float))
            and observed_at <= latest_observed
        ):
            return "ignored"
    await persist_event(db, project_id, "context_warning", payload, agent=agent, severity="info")
    await sse_manager.broadcast(project_id, "context_warning", payload)
    return "ok"
