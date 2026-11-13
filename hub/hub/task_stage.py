"""The one true stage a task has reached, read from real state (`where-each-task-stands-is-visible-
on-the-board`, FR-9..FR-16).

The status column says what a reviewer or an agent *claimed*; it cannot say whether a run is
working on the task, or whether approved work reached main. The stage can: it reads the bound runs,
the landing rows, the open questions and the prerequisites, and names the moment the task entered
it. Derived per request and never stored, like `has_open_divergence`, so there is no second copy
to disagree with the rows it came from.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import loose_close
from .db.models import EventLog, Question, Run, Task, TaskLanding, TaskTransition

NOT_STARTED = "not_started"
WORKING = "working"
WAITING_FOR_ANSWER = "waiting_for_answer"
WAITING_FOR_REVIEW = "waiting_for_review"
UNDER_REVIEW = "under_review"
SENT_BACK = "sent_back"
APPROVED_WAITING = "approved_waiting"
CHECKING = "checking"
LANDING = "landing"
ON_MAIN = "on_main"
LANDING_HELD = "landing_held"
DID_NOT_LAND = "did_not_land"
CLOSED = "closed"

_LANDING_STAGE = {
    "queued": APPROVED_WAITING,
    "checking": CHECKING,
    "landing": LANDING,
    "held": LANDING_HELD,
    "landed": ON_MAIN,
    "not_landed": DID_NOT_LAND,
    "sent_back": DID_NOT_LAND,
}


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def _one_line(text: Optional[str], limit: int = 160) -> Optional[str]:
    line = " ".join((text or "").split())
    if not line:
        return None
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


async def attach_stages(session: AsyncSession, responses: list, *, project_id: str) -> None:
    """Fill `stage`, `stage_since`, `stage_detail` and `stage_waits_on` on each response.

    Runs after the prerequisites and the open-question reasons are attached, because it reads both.
    """
    ids = {r.id for r in responses}
    if not ids:
        return

    running: Dict[str, datetime] = {}
    for task_id, started in await session.execute(
        select(Run.task_id, Run.started_at).where(
            Run.project_id == project_id, Run.status == "running", Run.task_id.in_(ids)
        )
    ):
        if task_id not in running or started < running[task_id]:
            running[task_id] = started

    landings: Dict[str, TaskLanding] = {}
    for landing in (
        await session.execute(
            select(TaskLanding)
            .where(TaskLanding.project_id == project_id, TaskLanding.task_id.in_(ids))
            .order_by(TaskLanding.created_at, TaskLanding.order_key)
        )
    ).scalars():
        landings[landing.task_id] = landing

    # When each task last entered its current status; later rows win.
    entered: Dict[Tuple[str, str], datetime] = {}
    # Why a closed task was cancelled, from the note of the move that closed it.
    cancelled: Dict[str, str] = {}
    for task_id, to_status, at, note in await session.execute(
        select(
            TaskTransition.task_id,
            TaskTransition.to_status,
            TaskTransition.created_at,
            TaskTransition.note,
        )
        .where(TaskTransition.project_id == project_id, TaskTransition.task_id.in_(ids))
        .order_by(TaskTransition.sequence)
    ):
        entered[(task_id, to_status)] = at
        if to_status == "rejected":
            cancelled.pop(task_id, None)
            why = loose_close.cancel_reason_of(note)
            if why is not None:
                cancelled[task_id] = why

    askers: Dict[str, str] = {}
    for question, run_task_id in await session.execute(
        select(Question, Run.task_id)
        .outerjoin(Run, Run.id == Question.created_by_run_id)
        .where(
            Question.project_id == project_id,
            Question.blocking.is_(True),
            Question.answered.is_(False),
            Question.declined.is_(False),
            Question.wait_ended_at.is_(None),
        )
        .where(
            Question.blocked_task_id.in_(ids) | ((Run.status == "running") & Run.task_id.in_(ids))
        )
        .order_by(Question.created_at, Question.batch_index)
    ):
        for candidate in (question.blocked_task_id, run_task_id):
            if candidate in ids:
                askers.setdefault(candidate, question.from_agent)

    # Why nobody reviews a completed task, where the Hub could not staff it (`review_unstaffed`,
    # written by a flow or by `review_on_completion`): the newest reason per task, oldest first.
    unstaffed: Dict[str, Tuple[datetime, Optional[str]]] = {}
    for data, at in await session.execute(
        select(EventLog.data, EventLog.timestamp)
        .where(
            EventLog.project_id == project_id,
            EventLog.event_type == "review_unstaffed",
            EventLog.data["task_id"].as_string().in_(ids),
        )
        .order_by(EventLog.timestamp)
    ):
        if isinstance(data, dict) and data.get("task_id") in ids:
            unstaffed[data["task_id"]] = (at, data.get("reason"))

    held_on = {
        landing.waits_on
        for landing in landings.values()
        if landing.state == "held" and landing.waits_on
    }
    held_names: Dict[str, str] = {}
    if held_on:
        for task_id, readable in await session.execute(
            select(Task.id, Task.readable_id).where(Task.id.in_(held_on))
        ):
            held_names[task_id] = readable or task_id

    for r in responses:
        landing = landings.get(r.id)
        stage: str
        since: Optional[datetime] = None
        detail: Optional[str] = None
        waits: Optional[str] = None
        unfinished = [
            p.readable_id or p.id for p in (r.prerequisites or []) if p.status != "approved"
        ]

        if r.status == "approved":
            if landing is None:
                stage = APPROVED_WAITING
            else:
                stage = _LANDING_STAGE.get(landing.state, APPROVED_WAITING)
                since = landing.updated_at
                if stage == ON_MAIN:
                    detail = (landing.landed_sha or "")[:7] or None
                elif stage == LANDING_HELD:
                    waits = held_names.get(landing.waits_on or "", landing.waits_on) or _one_line(
                        landing.reason
                    )
                    detail = waits
                elif stage == DID_NOT_LAND:
                    detail = _one_line(landing.reason)
        elif r.status == "rejected":
            stage = CLOSED
            detail = _one_line(cancelled.get(r.id))
        elif r.status == "revision_needed":
            stage = SENT_BACK
        elif r.status == "blocked" or r.awaiting_answer_reason:
            stage = WAITING_FOR_ANSWER
            waits = askers.get(r.id)
        elif r.status == "completed":
            stage = WAITING_FOR_REVIEW
            # Said since it entered `completed`, so a reason from an earlier round is not shown.
            why = unstaffed.get(r.id)
            entered_at = entered.get((r.id, "completed"))
            if why is not None and (entered_at is None or _aware(why[0]) >= _aware(entered_at)):
                detail = _one_line(why[1], limit=400)
        elif r.status == "under_review":
            stage = UNDER_REVIEW if r.id in running else WAITING_FOR_REVIEW
        elif r.id in running:
            stage = WORKING
            since = running[r.id]
        else:
            stage = NOT_STARTED
            if unfinished:
                waits = ", ".join(unfinished)

        if since is None:
            since = entered.get((r.id, r.status)) or r.updated
        r.stage = stage
        r.stage_since = since
        r.stage_detail = detail
        r.stage_waits_on = waits
