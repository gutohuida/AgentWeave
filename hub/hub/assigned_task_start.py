"""An assigned task outside a flow starts (`a-red-main-does-not-hold-the-night`, FR-9, FR-10, D7).

2026-10-27 on the operator's Hub: a fix task was moved to `assigned` at 01:24 and nothing was
queued for its assignee until the mender messaged it at 02:55. A flow staffs its own tasks; a task
outside any flow had nothing that started it -- `create_task_for_actor` commits and broadcasts, and
the stall sweep looks only at `in_progress` work.

**One rule, several nudges.** The rule (`start`): a task in `assigned`, in no flow (`loop_id` null),
whose assignee is an open agent and whose prerequisites are met, with no entry bound to it queued,
delivered or withdrawn for that assignee -- and no run of that assignee working it -- since it last entered
`assigned`, gets one entry queued for the assignee, bound to the task (`task_id`, so the runtime
moves it to `in_progress` when the turn starts), and a turn is asked for. The nudges ask the rule
after a commit: `apply_transition` (a move to `assigned`), `create_task_for_actor` (created
`assigned`) and `update_task` (a new assignee while `assigned`); the stall sweep asks it for every
such task as the backstop (one assigned before this change, while the Hub was down, or whose
prerequisites have since cleared).

"Since it entered `assigned`" is what keeps a delivered turn that ended without starting the task
from being re-queued in a spin: that turn is a divergence, recorded elsewhere. A `pending` task with
an assignee is not started: `assigned` is the operator's "work this now".

The entry's origin is `operator`, or `agent` with `origin_agent` when an agent's run made the move,
one hop past that run as an agent's message is (`api/v1/messages.py`). No new origin type, so no
rebuild of `ck_inbound_queue_origin_type`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, Tuple

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_PENDING_KEY = "assigned_task_start_pending"
#: Strong references to every start in flight, so none is collected early.
_in_flight: Set["asyncio.Task[Any]"] = set()
#: One start at a time per event loop: two nudges for one task must not queue two entries.
_locks: Dict[int, asyncio.Lock] = {}


def _lock() -> asyncio.Lock:
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _locks:
        _locks[loop_id] = asyncio.Lock()
    return _locks[loop_id]


def _aware(moment: Optional[datetime]) -> Optional[datetime]:
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def start_after_commit(session: AsyncSession, task_id: str, by_run: Optional[str] = None) -> None:
    """Ask the rule for *task_id* once *session*'s root transaction commits, never if it does not.
    *by_run* is the run whose agent made the move, `None` for the operator."""
    session.sync_session.info.setdefault(_PENDING_KEY, {})[task_id] = by_run


def request(task_id: str, by_run: Optional[str] = None) -> None:
    """Ask the rule for *task_id* now, in the background. Never raises."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    job = loop.create_task(start(task_id, by_run=by_run))
    _in_flight.add(job)
    job.add_done_callback(_in_flight.discard)


async def settled() -> None:
    """Wait for every start in flight (tests)."""
    while _in_flight:
        await asyncio.gather(*list(_in_flight), return_exceptions=True)


async def _entered_assigned_at(session: AsyncSession, task: Any) -> Optional[datetime]:
    """When *task* last entered `assigned`: its latest move there, else its creation."""
    from .db.models import TaskTransition

    entered = await session.scalar(
        select(func.max(TaskTransition.created_at)).where(
            TaskTransition.task_id == task.id, TaskTransition.to_status == "assigned"
        )
    )
    return _aware(entered) or _aware(task.created_at)


async def _already_started(session: AsyncSession, task: Any, since: Optional[datetime]) -> bool:
    """Whether a turn for *task* was queued for its assignee since *since* -- in any state: queued,
    delivered, or **withdrawn** -- or one of the assignee's runs is working it.

    A withdrawn entry counts (review of slice M): the Hub withdraws an entry after
    `DELIVERY_ATTEMPT_LIMIT` refusals or at once on an unretryable failure (F489), and the operator
    can withdraw one from the app. Not counting it re-queued a turn and a new conversation on every
    sweep, forever. So a task is started at most once per entry into `assigned`; moving it there
    again (or a new assignee) is what starts it again."""
    from .db.models import InboundQueueEntry, Run

    query = select(InboundQueueEntry.id).where(
        InboundQueueEntry.project_id == task.project_id,
        InboundQueueEntry.agent == task.assignee,
        InboundQueueEntry.task_id == task.id,
    )
    if since is not None:
        query = query.where(InboundQueueEntry.arrived_at >= since)
    if await session.scalar(query.limit(1)) is not None:
        return True
    running = await session.scalar(
        select(Run.id)
        .where(Run.task_id == task.id, Run.agent == task.assignee, Run.status == "running")
        .limit(1)
    )
    return running is not None


async def _waiting(session: AsyncSession, task: Any) -> bool:
    """The rule's question about *task*, without its queue: assigned, in no flow, held by an open
    agent, prerequisites met."""
    from .agent_roster import assignee_refusal
    from .dependency_gate import evaluate as evaluate_dependencies

    if task is None or task.status != "assigned" or task.loop_id or not task.assignee:
        return False
    if await assignee_refusal(session, task.project_id, task.assignee) is not None:
        return False
    return not (await evaluate_dependencies(session, task)).refuses


def _briefing(task: Any) -> str:
    from .scheduler import _briefing_completion_lines

    lines = [
        f"Work task {task.id} ('{task.title}'): it is assigned to you.",
        "",
    ]
    if (task.description or "").strip():
        lines += [task.description.strip(), ""]
    lines += _briefing_completion_lines(task, is_flow=False)
    return "\n".join(lines).strip()


async def _queue(task_id: str, by_run: Optional[str]) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    """Queue the entry if the rule says so: `(project_id, agent, payload)`, else `None`."""
    from .conversations import inherit_runtime_overrides, name_conversation, new_conversation
    from .db.engine import async_session_factory
    from .db.models import Run, Task
    from .inbound_queue import new_entry

    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        if not await _waiting(session, task):
            return None
        if await _already_started(session, task, await _entered_assigned_at(session, task)):
            return None
        origin_agent: Optional[str] = None
        hop_depth = 0
        run = await session.get(Run, by_run) if by_run else None
        if run is not None and run.agent:
            origin_agent = run.agent
            hop_depth = (run.turn_depth or 0) + 1
        conversation = new_conversation(
            project_id=task.project_id,
            agent=task.assignee,
            origin="peer" if origin_agent else "operator",
        )
        name_conversation(conversation, f"Task {task.id}: {task.title}"[:120])
        session.add(conversation)
        await inherit_runtime_overrides(session, conversation)
        await session.flush()
        entry = new_entry(
            project_id=task.project_id,
            agent=task.assignee,
            origin_type="agent" if origin_agent else "operator",
            origin_agent=origin_agent,
            content=_briefing(task),
            hop_depth=hop_depth,
            conversation_id=conversation.id,
            task_id=task.id,
        )
        session.add(entry)
        await session.commit()
        payload = {
            "entry_id": entry.id,
            "agent": entry.agent,
            "origin_type": entry.origin_type,
            "origin_agent": entry.origin_agent,
            "hop_depth": hop_depth,
            "conversation_id": conversation.id,
            "task_id": task.id,
        }
        return task.project_id, task.assignee, payload


async def start(task_id: str, *, by_run: Optional[str] = None) -> bool:
    """Apply the rule to *task_id*: queue its turn and ask for it to start. Whether an entry was
    queued. Never raises."""
    from . import turn_scheduler
    from .sse import sse_manager

    try:
        async with _lock():
            queued = await _queue(task_id, by_run)
        if queued is None:
            return False
        project_id, agent, payload = queued
        try:
            await sse_manager.broadcast(project_id, "queue_entry_queued", payload)
        except Exception:  # noqa: BLE001 -- the entry is durable; the board catches up
            logger.debug("queue broadcast failed", exc_info=True)
        await turn_scheduler.schedule_accepted(project_id, agent)
        return True
    except Exception:  # noqa: BLE001 -- the stall sweep asks again
        logger.warning("could not start assigned task %s", task_id, exc_info=True)
        return False


async def sweep() -> int:
    """The stall sweep's backstop (FR-10): the rule for every task left `assigned` outside a flow.
    How many were started. Never raises."""
    from .db.engine import async_session_factory
    from .db.models import Task

    try:
        async with async_session_factory() as session:
            ids = (
                (
                    await session.execute(
                        select(Task.id).where(
                            Task.status == "assigned",
                            Task.loop_id.is_(None),
                            Task.assignee.is_not(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
    except Exception:  # noqa: BLE001
        logger.warning("could not look for assigned tasks to start", exc_info=True)
        return 0
    started = 0
    for task_id in ids:
        started += int(await start(task_id))
    return started


@event.listens_for(Session, "after_commit")
def _request_pending(session: Session) -> None:
    if session.in_nested_transaction():
        return
    for task_id, by_run in session.info.pop(_PENDING_KEY, {}).items():
        request(task_id, by_run)


@event.listens_for(Session, "after_transaction_end")
def _drop_pending(session: Session, transaction) -> None:
    if transaction.parent is None:
        session.info.pop(_PENDING_KEY, None)
