"""A review's send-back restarts the author of a hand-started task (F1196).

`review_on_completion` finds a reviewer when a task outside any build completes. The way back was
missing: when that review moved the task to `revision_needed` nothing started its author, so it sat
until somebody re-sent it (AW-146, 2026-11-16, 14:16 until the Architect did). A flow does this
itself (`flow_advance`); this is the same hand-off for work no flow owns:

    a review turn (an agent, not the operator) moves `under_review -> revision_needed`
    on a task in no running build and no live loop
        -> the author (the holder `apply_transition` returned the task to) gets a turn, briefed with
           the reviewer's notes (`assigned_task_start.start_for_new_holder`).

**The cap.** An automatic build-review ping-pong spends quota with nobody watching (F1190 looped
exactly so). After `MAX_SEND_BACKS` consecutive send-backs by reviews with no approval between, the
author is not queued; a `send_back_held` event says so, and the board shows it on the task's
`sent_back` stage (`task_stage`), so the operator decides. The operator's own send-backs never
restart anybody: they are already looking.

Asked after the move's commit (the same shape as `assigned_task_start`), so the turn reads the
committed verdict. Never raises.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Set

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: Consecutive review send-backs after which the Hub stops restarting the author.
MAX_SEND_BACKS = 3
#: What the story and the board's stage read when the cap held the author back.
HELD_EVENT = "send_back_held"

_PENDING_KEY = "send_back_restart_pending"
_in_flight: Set["asyncio.Task[Any]"] = set()
_locks: Dict[str, asyncio.Lock] = {}


def ask_after_commit(session: AsyncSession, task_id: str) -> None:
    """Ask for *task_id*'s author to be restarted once *session*'s root transaction commits, and
    never if it does not."""
    session.sync_session.info.setdefault(_PENDING_KEY, set()).add(task_id)


def request(task_id: str) -> None:
    """Ask now, in the background. Never raises."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    job = loop.create_task(restart(task_id))
    _in_flight.add(job)
    job.add_done_callback(_in_flight.discard)


async def settled() -> None:
    """Wait for every request in flight (tests)."""
    while _in_flight:
        await asyncio.gather(*list(_in_flight), return_exceptions=True)


async def consecutive_send_backs(session: AsyncSession, task_id: str) -> int:
    """Send-backs made by a review (not the operator) since the task's last approval."""
    from .db.models import TaskTransition

    approved = await session.scalar(
        select(func.max(TaskTransition.sequence)).where(
            TaskTransition.task_id == task_id, TaskTransition.to_status == "approved"
        )
    )
    query = select(func.count(TaskTransition.sequence)).where(
        TaskTransition.task_id == task_id,
        TaskTransition.to_status == "revision_needed",
        TaskTransition.from_status == "under_review",
        TaskTransition.actor_kind != "operator",
    )
    if approved is not None:
        query = query.where(TaskTransition.sequence > approved)
    return int(await session.scalar(query) or 0)


async def _reviewers_send_back(session: AsyncSession, task: Any) -> bool:
    """Whether the task's latest move is a review turn's send-back."""
    from .db.models import TaskTransition

    latest = (
        await session.execute(
            select(TaskTransition)
            .where(TaskTransition.task_id == task.id)
            .order_by(TaskTransition.sequence.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return (
        latest is not None
        and latest.to_status == "revision_needed"
        and latest.from_status == "under_review"
        and latest.actor_kind != "operator"
    )


async def _already_restarted(session: AsyncSession, task: Any) -> bool:
    """A turn for the holder was queued since the task was sent back: asked twice, queued once."""
    from .db.models import InboundQueueEntry, TaskTransition

    sent_back_at = await session.scalar(
        select(func.max(TaskTransition.created_at)).where(
            TaskTransition.task_id == task.id, TaskTransition.to_status == "revision_needed"
        )
    )
    query = select(InboundQueueEntry.id).where(
        InboundQueueEntry.project_id == task.project_id,
        InboundQueueEntry.agent == task.assignee,
        InboundQueueEntry.task_id == task.id,
    )
    if sent_back_at is not None:
        query = query.where(InboundQueueEntry.arrived_at >= sent_back_at)
    return await session.scalar(query.limit(1)) is not None


async def _hold(session: AsyncSession, task: Any, count: int) -> None:
    from .sse import sse_manager
    from .utils import persist_event

    payload = {
        "task_id": task.id,
        "task_title": task.title,
        "send_backs": count,
        "reason": (
            f"Its review has sent {task.display_id} back {count} times running, so its author was "
            f"not restarted automatically (the limit is {MAX_SEND_BACKS}). Read the reviewer's "
            f"notes and decide: re-send it to its author, change the work, or approve it."
        ),
    }
    await persist_event(session, task.project_id, HELD_EVENT, payload, severity="warning")
    await sse_manager.broadcast(task.project_id, HELD_EVENT, payload)


async def restart(task_id: str) -> bool:
    """Apply the rule to *task_id*: whether its author's turn was queued. Never raises."""
    from . import assigned_task_start, review_on_completion
    from .agent_roster import assignee_refusal
    from .db.engine import async_session_factory
    from .db.models import Task

    try:
        lock = _locks.setdefault(task_id, asyncio.Lock())
        async with lock:
            async with async_session_factory() as session:
                task = await session.get(Task, task_id)
                if task is None or task.status != "revision_needed" or not task.assignee:
                    return False
                if not await _reviewers_send_back(session, task):
                    return False
                if await review_on_completion._a_build_or_loop_reviews_it(session, task):
                    return False
                if await _already_restarted(session, task):
                    return False
                if await assignee_refusal(session, task.project_id, task.assignee) is not None:
                    return False
                count = await consecutive_send_backs(session, task_id)
                if count >= MAX_SEND_BACKS:
                    await _hold(session, task, count)
                    return False
            await assigned_task_start.start_for_new_holder(task_id)
            return True
    except Exception:  # noqa: BLE001 -- the board and the operator's own controls still work
        logger.warning("could not restart the author of %s", task_id, exc_info=True)
        return False


@event.listens_for(Session, "after_commit")
def _request_pending(session: Session) -> None:
    if session.in_nested_transaction():
        return
    for task_id in session.info.pop(_PENDING_KEY, set()):
        request(task_id)


@event.listens_for(Session, "after_transaction_end")
def _drop_pending(session: Session, transaction) -> None:
    if transaction.parent is None:
        session.info.pop(_PENDING_KEY, None)
