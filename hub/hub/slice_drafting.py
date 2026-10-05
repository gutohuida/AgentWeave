"""Draft a roadmap's next slice once the approved slice is built (C1a D4, amended by D4a for F496).

Approving a slice document with `draft_next_slice` records the request as a `next_slice_requested`
event on that document. The drafting turn is queued only when no task linked to the document is
still open: in the approval request itself when it has no task, otherwise from
`task_transition_service.apply_transition`, when the last linked task reaches `approved` or
`rejected`. A `next_slice_queued` event naming the request makes that happen once per request.

The turn is queued as the operator, because the operator asked for it in the approval request, to
the agent that created the slice document, in the conversation where it created it. Its spec
document is the roadmap, so it is a specification turn with no file-write tools.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from . import spec_lifecycle, spec_service
from .db.models import Run, SpecDocument, SpecDocumentEvent, Task
from .inbound_queue import new_entry
from .task_transitions import TERMINAL_STATUSES

logger = logging.getLogger(__name__)

REQUESTED = "next_slice_requested"
QUEUED = "next_slice_queued"

_PENDING_KEY = "slice_drafting_pending_schedules"
#: Strong references to the scheduling tasks an `after_commit` listener starts, so none is
#: collected before it runs.
_in_flight: Set["asyncio.Task[Any]"] = set()


def outcome(
    state: str,
    slice_key: Optional[str] = None,
    agent: Optional[str] = None,
    open_tasks: Optional[int] = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {"state": state, "slice": slice_key, "agent": agent}
    if open_tasks is not None:
        result["open_tasks"] = open_tasks
    return result


async def request_next_slice(
    session: AsyncSession,
    project_id: str,
    workspace,
    document: SpecDocument,
    payload: Optional[Dict[str, Any]],
    actor: spec_lifecycle.Actor,
) -> Dict[str, Any]:
    """Record the operator's request, and queue the turn now if the slice has no open task.

    Runs after the approval commits, and never raises: the approval stands whatever happens here.
    A failure to record or queue reports `not_queued`; a failure to schedule leaves the committed
    entry for the next drain, so it still reports `queued`.
    """
    link = (payload or {}).get("roadmap")
    if document.kind != "change-spec" or not isinstance(link, dict):
        return outcome("not_a_slice")
    roadmap_path, approved_key = str(link.get("document")), str(link.get("slice"))
    slices = spec_service.roadmap_slices(workspace, roadmap_path)
    keys = [str(item["key"]) for item in slices]
    position = keys.index(approved_key) if approved_key in keys else len(keys)
    if position + 1 >= len(keys):
        return outcome("last_slice")
    approved_slice, following = slices[position], slices[position + 1]
    next_key = str(following["key"])

    created = (
        await session.execute(
            select(SpecDocumentEvent)
            .where(
                SpecDocumentEvent.document_id == document.id, SpecDocumentEvent.kind == "created"
            )
            .order_by(SpecDocumentEvent.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if created is None or created.actor_kind != "agent" or not created.actor:
        return outcome("no_author", next_key)
    agent = created.actor
    run = await session.get(Run, created.run_id) if created.run_id else None
    if run is None or not run.conversation_id:
        return outcome("no_conversation", next_key, agent)

    roadmap_row = await spec_lifecycle.get_document(session, project_id, roadmap_path)
    # Carried on the request, so the transition that fires it reads no file. The roadmap is
    # approved now; if it is reopened and changed before the slice is built, the turn still tells
    # the agent to read it, and the new slice's link is checked again when it is proposed.
    detail = {
        "roadmap": roadmap_path,
        "roadmap_title": roadmap_row.title if roadmap_row is not None else roadmap_path,
        "approved_slice": {k: approved_slice.get(k) for k in ("key", "title")},
        "next_slice": {k: following.get(k) for k in ("key", "title", "intent", "done")},
        "agent": agent,
        "conversation_id": run.conversation_id,
    }
    try:
        await spec_lifecycle.record_event(
            session, document, kind=REQUESTED, actor=actor, detail=detail
        )
        await session.flush()
        open_tasks = len(await _open_tasks(session, document.id))
        queued = open_tasks == 0 and await _queue_if_built(session, document) is not None
        await session.commit()
    except Exception:  # noqa: BLE001 -- the approval is committed; say the turn was not queued
        await session.rollback()
        logger.warning(
            "could not request the next slice of %s from %s", roadmap_path, agent, exc_info=True
        )
        return outcome("not_queued", next_key, agent)
    if not queued:
        return outcome("waiting", next_key, agent, open_tasks)

    from . import turn_scheduler

    try:
        await turn_scheduler.schedule_agent(project_id, agent)
    except Exception:  # noqa: BLE001 -- the entry is durable; the next drain delivers it
        logger.warning("could not schedule %s for the next slice", agent, exc_info=True)
    return outcome("queued", next_key, agent)


async def on_task_closed(session: AsyncSession, task: Task) -> None:
    """Queue the drafting turn if *task* was the last open task of a slice that asked for it.

    Called by `apply_transition` inside the caller's transaction. Runs in a savepoint and never
    raises: a task's approval is a judgement about the task, and this is not grounds to undo it.
    """
    if task.status not in TERMINAL_STATUSES or not task.spec_document_id:
        return
    try:
        async with session.begin_nested():
            document = await session.get(SpecDocument, task.spec_document_id)
            agent = await _queue_if_built(session, document) if document is not None else None
    except Exception:  # noqa: BLE001 -- never fail the transition
        logger.warning("could not queue the next slice after %s closed", task.id, exc_info=True)
        return
    if agent is not None:
        _schedule_after_commit(session, task.project_id, agent)


async def _open_tasks(session: AsyncSession, document_id: str) -> List[Task]:
    rows = await session.execute(select(Task).where(Task.spec_document_id == document_id))
    return [t for t in rows.scalars().all() if t.status not in TERMINAL_STATUSES]


async def _queue_if_built(session: AsyncSession, document: SpecDocument) -> Optional[str]:
    """Stage the drafting entry for the latest unanswered request, if no linked task is open.

    Returns the agent it is queued to, or None when nothing was queued.
    """
    events = (
        (
            await session.execute(
                select(SpecDocumentEvent)
                .where(
                    SpecDocumentEvent.document_id == document.id,
                    SpecDocumentEvent.kind.in_((REQUESTED, QUEUED)),
                )
                .order_by(SpecDocumentEvent.created_at)
            )
        )
        .scalars()
        .all()
    )
    requests = [e for e in events if e.kind == REQUESTED]
    if not requests:
        return None
    request = requests[-1]
    if any(e.kind == QUEUED and (e.detail or {}).get("request") == request.id for e in events):
        return None
    tasks = (
        (
            await session.execute(
                select(Task)
                .where(Task.spec_document_id == document.id)
                .order_by(Task.created_at, Task.id)
            )
        )
        .scalars()
        .all()
    )
    if any(t.status not in TERMINAL_STATUSES for t in tasks):
        return None

    detail = request.detail or {}
    agent = str(detail["agent"])
    session.add(
        new_entry(
            project_id=document.project_id,
            agent=agent,
            origin_type="operator",
            content=next_slice_message(detail, approved_path=document.path, tasks=tasks),
            hop_depth=0,
            conversation_id=detail["conversation_id"],
            spec_document=detail["roadmap"],
        )
    )
    await spec_lifecycle.record_event(
        session,
        document,
        kind=QUEUED,
        actor=spec_lifecycle.Actor(kind="system"),
        detail={"request": request.id, "agent": agent, "tasks": [t.id for t in tasks]},
    )
    return agent


def next_slice_message(detail: Dict[str, Any], *, approved_path: str, tasks: List[Task]) -> str:
    """The fixed Hub text of the drafting turn (C1a D4, D4a)."""
    roadmap_path = detail["roadmap"]
    approved = detail.get("approved_slice") or {}
    following = detail.get("next_slice") or {}
    link = f'{{"document": "{roadmap_path}", "slice": "{following.get("key")}"}}'
    lines = [
        f"Slice `{approved.get('key')}` ({approved.get('title') or ''}) of the roadmap "
        f"{detail.get('roadmap_title')!r} (`{roadmap_path}`), specified by `{approved_path}`, is "
        "built: none of its tasks is still open. When the operator approved it, they asked you to "
        "draft the next slice once it was built.",
        "Its tasks and how they ended:",
        *(
            [f"- `{t.id}` {t.title}: {t.status}" for t in tasks]
            or ["- none: no task was linked to it"]
        ),
        f"The next slice is `{following.get('key')}`: {following.get('title') or ''}.",
        f"- Intent: {following.get('intent') or '(not stated)'}",
        f"- Done when: {following.get('done') or '(not stated)'}",
        "Before drafting, read the roadmap with `read_spec_document`, and read those tasks (their "
        "notes and evidence) with `get_task` and `list_evidence`: what building that slice taught "
        "you belongs in this one, and a rejected task's work is not done.",
        "Then create a change document with `create_spec_document` and submit it with "
        f"`roadmap: {link}`. Keep it to about a dozen requirements or fewer, as a few tasks. Do "
        "not implement anything.",
    ]
    return "\n".join(lines)


def _schedule_after_commit(session: AsyncSession, project_id: str, agent: str) -> None:
    """Schedule *agent* once the session's root transaction commits, and never if it does not."""
    session.sync_session.info.setdefault(_PENDING_KEY, []).append((project_id, agent))


@event.listens_for(Session, "after_commit")
def _schedule_pending(session: Session) -> None:
    if session.in_nested_transaction():
        return
    pending = session.info.pop(_PENDING_KEY, [])
    if not pending:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("no event loop to schedule the next slice; the next drain delivers it")
        return
    for project_id, agent in pending:
        task = loop.create_task(_schedule(project_id, agent))
        _in_flight.add(task)
        task.add_done_callback(_in_flight.discard)


@event.listens_for(Session, "after_transaction_end")
def _drop_pending(session: Session, transaction) -> None:
    if transaction.parent is None:
        session.info.pop(_PENDING_KEY, None)


async def _schedule(project_id: str, agent: str) -> None:
    from . import turn_scheduler

    try:
        await turn_scheduler.schedule_agent(project_id, agent)
    except Exception:  # noqa: BLE001 -- the entry is durable; the next drain delivers it
        logger.warning("could not schedule %s for the next slice", agent, exc_info=True)
