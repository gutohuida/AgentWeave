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


@dataclass(frozen=True)
class TurnRefusal:
    """A refusal about what a request asked for, carried out to the caller that asked it.

    Exists so a caller can answer *no* instead of *queued* (F108). Its **presence** is the
    classification, which is why it is a separate object rather than another boolean beside
    `terminal_failure`: that flag defaults to `True` and six early returns below take the default
    without meaning it, so a caller gating on it would report a working request as failed. Nothing
    but the refusal branch can construct one of these, so no early return can produce a false
    positive however its defaults are written.

    `entry_ids` is what makes it attributable. `schedule_agent` builds its turn from the oldest
    eligible entry across the agent's *whole* queue, so a refusal frequently belongs to a
    conversation the current caller never mentioned; without the ids, answering *no* to whoever
    happened to arrive would report a refusal about somebody else's input.
    """

    status_code: int
    detail: str
    entry_ids: Tuple[str, ...]


@dataclass
class ScheduleResult:
    response: Optional[object] = None
    waiting_reason: Optional[str] = None
    terminal_failure: bool = True
    refusal: Optional[TurnRefusal] = None


def _lock_for(project_id: str, agent: str) -> asyncio.Lock:
    return _agent_locks.setdefault((project_id, agent), asyncio.Lock())


def _entry_kind(entry: InboundQueueEntry) -> Optional[str]:
    """Returns "review" or "work", or `None` for an entry naming neither (design D3, F66).

    `review_task_id` wins when both are set — the divergence response that restaffs a failed
    review sets both to the same task (`run_divergence.py`), and that entry needs the review
    checkout, not the ordinary worktree, so it is a review turn regardless of the `task_id` beside
    it.
    """
    if entry.review_task_id is not None:
        return "review"
    if entry.task_id is not None:
        return "work"
    return None


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

        # Filter by depth and by kind, as well as by conversation. `can_start` asks whether the
        # turn may begin; nothing used to ask which entries may ride on it, so an over-budget
        # entry was bundled into a turn admitted by a shallower one and delivered anyway (design
        # D1, finding F5). F66 is the same defect one column over: a review entry and a work entry
        # batched together delivered a turn that was neither, so the controlling entry's kind
        # decides the turn and the other kind's entries are deferred to the next one (design D3).
        # An entry naming neither — a plain message riding beside a delegation — has no kind to
        # conflict with either and always rides along.
        controlling_kind = _entry_kind(controlling)
        selected = [
            entry
            for entry in entries
            if entry.conversation_id == conversation.id
            and entry.hop_depth <= hop_budget
            and (
                controlling_kind is None
                or _entry_kind(entry) is None
                or _entry_kind(entry) == controlling_kind
            )
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
            # Written down before the classification is even asked, because it matters in both
            # branches and for the same reason: this is the only place the refusal's own words
            # exist. `GET /queue/{agent}/status` re-derives what it can and reported
            # `waiting_reason: null` for everything it could not — a D8 checkout collision, an
            # unimplemented runner, a work_dir the project does not contain (F97). Recording it
            # here is what keeps the status route from having to restate each condition, and what
            # makes the *next* refusal visible without another edit.
            for entry in selected:
                entry.waiting_reason = exc.detail
            await db.commit()
            # Does this refusal clear on its own? `workspace_unavailable` was the first refusal
            # that did, and it still selects the operator event below, but it is no longer the only
            # one: a turn refused because another agent holds the task's checkout (design D8) waits
            # for that turn to end. Asking the classification rather than enumerating the causes is
            # what stops the next transient refusal from having to edit this branch again.
            transient = getattr(exc, "transient", workspace_unavailable)
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
            elif not transient and not getattr(exc, "agent_wide", False):
                # No `Run` was ever created for this attempt, so `selected` never became
                # `delivered` and `return_run_entries`'s own abandonment bookkeeping never runs
                # for it (F56) — a refusal raised here (a review target with no evidence naming a
                # commit, an archived agent, a task that does not exist, ...) repeats identically
                # forever, and every entry queued behind it starves along with it. Count the
                # attempt the same way a spawned-and-failed run's does, and give up on the same
                # schedule, so a permanently wrong entry stops wedging the whole queue.
                #
                # **`and not agent_wide` is F114, and it is the same rule the `transient` half of
                # this condition already applies.** F56's reasoning holds wherever the refused
                # entry is *in the way of other input* — which is every example in the list above.
                # It does not hold where the refusal stops the agent running at all: no runner is
                # bound, its CLI is not installed, its runner row is gone. Nothing is starving
                # behind that entry, because nothing for that agent could run either way, so
                # dropping the head of the queue buys nobody a turn — and it costs the operator
                # the input the product promised to hold until they performed the repair (F96).
                #
                # Measured before this line existed: three messages to an unbound agent destroyed
                # the first in under two seconds, and two clicks of the Continue button — the
                # control the conversation view offers for exactly this situation — destroyed it
                # faster. Every schedule counted an attempt, so the operator's own attempts to
                # find out why nothing was happening were what consumed the allowance.
                #
                # Only refusals that are *certainly* agent-wide carry the flag. A refusal that
                # blocks one entry keeps counting, including the one that looks environmental and
                # is not: a task's checkout that could not be prepared is the **task's** workspace,
                # not the agent's, so other input really could run and the head entry really is in
                # the way (design D3a).
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
            # A transient refusal that is not the paused-workspace one records nothing at all,
            # which is the shape the sibling per-agent rule already has: `schedule_agent` returns
            # "agent is already running" above without an event, because a queue waiting its turn
            # is the system working. The entry keeps `delivery_attempts` at whatever it was, stays
            # `queued`, and the next tick tries again.
            # Carried out only when the refusal is about what was asked (design D10). A
            # non-transient refusal about the *environment* — no runner bound, the CLI missing
            # from PATH — is why the queue exists: the entry waits, the operator performs the
            # repair, and binding a runner delivers it (F96). Answering those as failures would
            # discard input the Hub promised to keep.
            refusal = (
                TurnRefusal(
                    status_code=exc.status_code,
                    detail=exc.detail,
                    entry_ids=tuple(entry.id for entry in selected),
                )
                if getattr(exc, "request_level", False) and not transient
                else None
            )
            return ScheduleResult(
                waiting_reason=exc.detail,
                terminal_failure=not transient,
                refusal=refusal,
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
