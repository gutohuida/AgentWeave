"""Start queued agent turns when an agent is idle and within the hop budget."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from sqlalchemy import select

from .conversations import get_conversation_by_id
from .db.engine import async_session_factory
from .db.models import InboundQueueEntry, Run
from .inbound_queue import can_start, format_turn_prompt, project_limits, queued_entries
from .sse import sse_manager
from .usage_accounting import project_budget_state
from .utils import persist_event

_agent_locks: Dict[Tuple[str, str], asyncio.Lock] = {}


@dataclass
class ScheduleResult:
    response: Optional[object] = None
    waiting_reason: Optional[str] = None
    terminal_failure: bool = True


def _lock_for(project_id: str, agent: str) -> asyncio.Lock:
    return _agent_locks.setdefault((project_id, agent), asyncio.Lock())


async def schedule_agent(project_id: str, agent: str) -> ScheduleResult:
    """Start at most one turn for *agent*; leave work durable when it cannot start."""
    from .api.v1.agent_trigger import TriggerAgentError, trigger_agent_directly

    async with _lock_for(project_id, agent), async_session_factory() as db:
        running = await db.execute(
            select(Run.id)
            .where(Run.project_id == project_id, Run.agent == agent, Run.status == "running")
            .limit(1)
        )
        if running.scalar_one_or_none() is not None:
            return ScheduleResult(waiting_reason="agent is already running", terminal_failure=False)

        entries = await queued_entries(db, project_id, agent)
        if not entries:
            return ScheduleResult(waiting_reason="queue is empty")
        hop_budget, cap = await project_limits(db, project_id)
        if not can_start(entries, hop_budget):
            return ScheduleResult(waiting_reason="hop budget exhausted")

        controlling = next((entry for entry in entries if entry.hop_depth <= hop_budget), None)
        if controlling is None or controlling.conversation_id is None:
            return ScheduleResult(waiting_reason="queued entry has no conversation")
        conversation = await get_conversation_by_id(db, controlling.conversation_id)
        if (
            conversation is None
            or conversation.project_id != project_id
            or conversation.agent != agent
            or conversation.lifecycle != "open"
        ):
            return ScheduleResult(waiting_reason="conversation is unavailable")

        selected = [entry for entry in entries if entry.conversation_id == conversation.id][:cap]
        controlling_operator = next(
            (entry for entry in selected if entry.origin_type == "operator"), None
        )
        initiator = "operator" if controlling_operator is not None else "autonomous"
        budget = await project_budget_state(db, project_id)
        if initiator == "autonomous" and budget["exhausted"]:
            return ScheduleResult(waiting_reason="token budget exhausted")
        work_dir = controlling_operator.work_dir if controlling_operator is not None else None
        # Read from the same entry `work_dir` comes from, for the same reason: a turn can batch
        # several entries, and the operator's own is the one whose viewing position describes
        # what they asked. An agent's or a job's entry never carries one.
        spec_document = (
            controlling_operator.spec_document if controlling_operator is not None else None
        )

        try:
            response = await trigger_agent_directly(
                project_id=project_id,
                agent=agent,
                message=format_turn_prompt(selected),
                conversation_id=conversation.id,
                work_dir=work_dir,
                spec_document=spec_document,
                session=db,
                queue_entry_ids=[entry.id for entry in selected],
                turn_depth=min(entry.hop_depth for entry in selected),
                initiator=initiator,
            )
        except TriggerAgentError as exc:
            if getattr(exc, "workspace_unavailable", False):
                await persist_event(
                    db,
                    project_id,
                    "queue_agent_paused",
                    {
                        "agent": agent,
                        "reason": exc.detail,
                        "directory_state": exc.directory_state,
                    },
                    agent=agent,
                    severity="warn",
                )
                await sse_manager.broadcast(
                    project_id,
                    "queue_agent_paused",
                    {
                        "agent": agent,
                        "reason": exc.detail,
                        "directory_state": exc.directory_state,
                    },
                )
            return ScheduleResult(
                waiting_reason=exc.detail,
                terminal_failure=not getattr(exc, "workspace_unavailable", False),
            )
        return ScheduleResult(response=response, terminal_failure=False)


async def redrain_queued_agents(project_id: str) -> None:
    """Re-evaluate every queued agent after repair or settings change."""
    async with async_session_factory() as db:
        agents = (
            (
                await db.execute(
                    select(InboundQueueEntry.agent)
                    .where(
                        InboundQueueEntry.project_id == project_id,
                        InboundQueueEntry.state == "queued",
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        for agent in agents:
            await schedule_agent(project_id, agent)
