"""Shared agent-output / context-usage recording, used by both compatibility self-report HTTP
endpoints (`POST /agents/{name}/output`, `.../context-usage`) and the
Hub's own direct-spawn output loop (`agent_trigger.py`). Factored out so a Hub-spawned run's
output is recorded through the exact same DB-write + SSE-broadcast shape a self-reporting
agent already produces — one path, not two that can drift.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .conversations import latest_open_conversation, new_conversation
from .db.models import AgentOutput, Conversation, EventLog, Run
from .model_catalog import context_window_for_model
from .sse import sse_manager
from .utils import persist_event, short_id


async def record_agent_output(
    db: AsyncSession,
    project_id: str,
    agent: str,
    *,
    content: str,
    session_id: Optional[str],
    conversation_id: Optional[str] = None,
    kind: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    sequence: Optional[int] = None,
) -> AgentOutput:
    """Persist one AgentOutput row and broadcast it, mirroring `POST .../output`."""
    if conversation_id is None and run_id:
        run_result = await db.execute(
            select(Run.conversation_id).where(
                Run.id == run_id,
                Run.project_id == project_id,
                Run.agent == agent,
            )
        )
        conversation_id = run_result.scalar_one_or_none()
    if conversation_id is None and session_id:
        conversation_result = await db.execute(
            select(Conversation.id).where(
                Conversation.project_id == project_id,
                Conversation.agent == agent,
                Conversation.provider_session_id == session_id,
            )
        )
        conversation_id = conversation_result.scalar_one_or_none()
    if conversation_id is None:
        conversation = None
        if session_id is None:
            conversation = await latest_open_conversation(db, project_id=project_id, agent=agent)
        if conversation is None:
            # Reached only when output arrives that no conversation and no run accounts for —
            # a self-reporting agent's session the Hub did not open. `operator` is the floor:
            # the thread it reconstructs is the one the operator sees the agent working in.
            conversation = new_conversation(project_id=project_id, agent=agent, origin="operator")
            conversation.provider_session_id = session_id
            db.add(conversation)
            await db.flush()
        conversation_id = conversation.id
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
        conversation_id=conversation_id,
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
            "conversation_id": conversation_id,
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


def resolve_usage_limit(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in `limit_tokens` from the model catalog, and derive `percent` from it.

    Claude reports how many tokens a request carried but not how large its window is; it reports
    the window separately, in a different message, with no tokens. Waiting for those two to meet
    is what produced 329 samples and zero usable percentages. The catalog is authoritative about
    the window, and the sample already knows its model — so the reading completes here, on its
    own, at the one place every write path funnels through.

    Nothing is invented: a model the catalog does not declare leaves `limit_tokens` and `percent`
    as they were. A sample that already carries a limit (Codex reports its own) is untouched.
    """
    if payload.get("limit_tokens") is not None or payload.get("percent") is not None:
        return payload
    context_tokens = payload.get("context_tokens")
    if not isinstance(context_tokens, int) or isinstance(context_tokens, bool):
        return payload
    model = payload.get("model")
    limit = context_window_for_model(model) if isinstance(model, str) else None
    if not limit or limit <= 0:
        return payload
    return {
        **payload,
        "limit_tokens": limit,
        "percent": round(min(100.0, max(0.0, (context_tokens / limit) * 100)), 2),
    }


async def record_context_usage(
    db: AsyncSession, project_id: str, agent: str, sample_payload: Dict[str, Any]
) -> str:
    """Persist a context-usage snapshot and broadcast it, mirroring `POST .../context-usage`.

    Returns "ok" or "ignored" (a strictly-older observation for the same agent).
    """
    payload = resolve_usage_limit({**sample_payload, "agent": agent})
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
