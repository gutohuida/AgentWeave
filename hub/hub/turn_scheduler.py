"""Start queued agent turns when an agent is idle and within the hop budget."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from sqlalchemy import select

from .conversations import get_conversation_by_id
from .db.engine import async_session_factory
from .db.models import InboundQueueEntry, Run
from .inbound_queue import (
    DELIVERY_ATTEMPT_LIMIT,
    can_start,
    format_turn_prompt,
    project_limits,
    queued_entries,
)
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

        # Filter by depth as well as conversation. `can_start` asks whether the turn may begin;
        # nothing used to ask which entries may ride on it, so an over-budget entry was bundled
        # into a turn admitted by a shallower one and delivered anyway (design D1, finding F5).
        selected = [
            entry
            for entry in entries
            if entry.conversation_id == conversation.id and entry.hop_depth <= hop_budget
        ][:cap]
        if not selected:
            return ScheduleResult(waiting_reason="hop budget exhausted")
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
                # The admitting entry's depth, not `min()` across the batch. `min()` was never a
                # decision — it let a turn batching a hop-0 entry with a deeper one restart the
                # count from zero, so the chain ran backwards (design D2). With the filter above,
                # every delivered entry is within budget and `controlling` is the first of them.
                turn_depth=controlling.hop_depth,
                initiator=initiator,
            )
        except TriggerAgentError as exc:
            workspace_unavailable = getattr(exc, "workspace_unavailable", False)
            if workspace_unavailable:
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
            else:
                # No `Run` was ever created for this attempt, so `selected` never became
                # `delivered` and `return_run_entries`'s own abandonment bookkeeping never runs
                # for it (F56) — a refusal raised here (a review target with no evidence naming a
                # commit, an archived agent, a task that does not exist, ...) repeats identically
                # forever, and every entry queued behind it starves along with it. Count the
                # attempt the same way a spawned-and-failed run's does, and give up on the same
                # schedule, so a permanently wrong entry stops wedging the whole queue.
                abandoned: list[InboundQueueEntry] = []
                for entry in selected:
                    entry.delivery_attempts = (entry.delivery_attempts or 0) + 1
                    if entry.delivery_attempts >= DELIVERY_ATTEMPT_LIMIT:
                        entry.state = "withdrawn"
                        entry.withdrawn_at = datetime.now(timezone.utc)
                        entry.abandoned_reason = (
                            f"delivery failed {entry.delivery_attempts} times "
                            f"({exc.detail}); the Hub stopped retrying"
                        )
                        abandoned.append(entry)
                await db.commit()
                # Same shape `_report_abandoned_entries` broadcasts for a spawned-and-failed run,
                # `run_id: None` because none was ever created — the operator's signal that input
                # is being dropped should not depend on which of the two paths dropped it.
                for entry in abandoned:
                    payload = {
                        "entry_id": entry.id,
                        "agent": agent,
                        "run_id": None,
                        "attempts": entry.delivery_attempts,
                        "reason": entry.abandoned_reason,
                        "conversation_id": entry.conversation_id,
                    }
                    await persist_event(
                        db,
                        project_id,
                        "queue_entry_abandoned",
                        payload,
                        agent=agent,
                        severity="warn",
                    )
                    await sse_manager.broadcast(project_id, "queue_entry_abandoned", payload)
            return ScheduleResult(
                waiting_reason=exc.detail,
                terminal_failure=not workspace_unavailable,
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
