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
from typing import Any, Dict, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import loose_close, workspace_preparation
from .db.models import (
    EventLog,
    LandingBatch,
    Question,
    Run,
    Task,
    TaskCheckRun,
    TaskLanding,
    TaskTransition,
)

NOT_STARTED = "not_started"
#: Its turn is starting: the Hub is preparing the task's checkout (`workspace_preparation`).
PREPARING_CHECKOUT = "preparing_checkout"
WORKING = "working"
WAITING_FOR_ANSWER = "waiting_for_answer"
WAITING_FOR_REVIEW = "waiting_for_review"
#: Completed, and its review is held for its pre-review checks (`project_checks.review_wait`).
PRE_REVIEW_CHECKS = "pre_review_checks"
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


#: A check state's kinds (`task-stages-in-the-build-view-and-dependency-map` FR-3).
KIND_PRE_REVIEW = "pre_review"
KIND_LANDING = "landing"
#: The statuses a task reaches after its work is finished: a pre-review run started while the work
#: was being completed still counts on them, so the window opens when the round of work began.
_AFTER_THE_WORK = ("completed", "under_review", "revision_needed", "approved")


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

    # The author a send-back would restart but the cap held back (`send_back_restart`).
    held_back: Dict[str, Tuple[datetime, Optional[str]]] = {}
    for data, at in await session.execute(
        select(EventLog.data, EventLog.timestamp)
        .where(
            EventLog.project_id == project_id,
            EventLog.event_type == "send_back_held",
            EventLog.data["task_id"].as_string().in_(ids),
        )
        .order_by(EventLog.timestamp)
    ):
        if isinstance(data, dict) and data.get("task_id") in ids:
            held_back[data["task_id"]] = (at, data.get("reason"))

    preparing = workspace_preparation.preparing_task_ids(project_id)

    # The review hold of each completed task: the one decision the review waits on, so the stage
    # cannot disagree with it (FR-1).
    holds = await review_waits(
        session,
        [r.id for r in responses if r.status == "completed" and not r.awaiting_answer_reason],
    )
    checks = await check_states(
        session, [(r.id, r.status) for r in responses], project_id=project_id, holds=holds
    )

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
            why = held_back.get(r.id)
            entered_at = entered.get((r.id, "revision_needed"))
            if why is not None and (entered_at is None or _aware(why[0]) >= _aware(entered_at)):
                detail = _one_line(why[1], limit=400)
        elif r.status == "blocked" or r.awaiting_answer_reason:
            stage = WAITING_FOR_ANSWER
            waits = askers.get(r.id)
        elif r.status == "completed" and holds.get(r.id) is not None:
            stage = PRE_REVIEW_CHECKS
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
        elif r.id in preparing:
            stage = PREPARING_CHECKOUT
            since = preparing[r.id]
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
        r.check_state = checks.get(r.id)


async def review_waits(session: AsyncSession, task_ids: Sequence[str]) -> Dict[str, Any]:
    """`project_checks.review_wait` of each of *task_ids* (all `completed`): what holds its review
    for its checks, by task, `None` where nothing does. The same function the review hold itself
    calls, so the `pre_review_checks` stage is that decision, not a second reading (FR-1). Never
    raises: a task whose hold cannot be read reads as not held, as before this stage existed."""
    from . import project_checks

    holds: Dict[str, Any] = {}
    if not task_ids:
        return holds
    for task in (await session.execute(select(Task).where(Task.id.in_(list(task_ids))))).scalars():
        try:
            holds[task.id] = await project_checks.review_wait(session, task)
        except Exception:  # noqa: BLE001 -- a read never fails for a stage
            holds[task.id] = None
    return holds


def run_check_state(run: TaskCheckRun, *, waiting_for_slot: bool) -> Optional[str]:
    """A check run's state in the words every surface shows (FR-3, FR-13); `None` for a superseded
    run, which is never shown. A run that judged nothing (state `error`, interrupted, or failed
    only because a check could not run, by `project_checks`' own reading) could not run; a run that
    found the work does not merge onto main failed, as it sends the work back."""
    from . import project_checks

    if run.state == "running":
        return "waiting" if waiting_for_slot else "running"
    if run.state == "passed":
        return "passed"
    if run.state == "failed":
        if not project_checks.own_failure(run.results) and project_checks.could_not_run_results(
            run.results
        ):
            return "could_not_run"
        return "failed"
    if run.state == "error":
        return "failed" if project_checks.conflicted(run) else "could_not_run"
    if run.state == "interrupted":
        return "could_not_run"
    return None


async def check_states(
    session: AsyncSession,
    tasks: Sequence[Tuple[str, str]],
    *,
    project_id: str,
    holds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, str]]:
    """The latest-check-state algorithm (`task-stages-in-the-build-view-and-dependency-map` FR-3..
    FR-5): each of *tasks* (`(id, status)`) to its one check state `{kind, state}`, absent where it
    has none. *holds* are `review_waits` of the completed ones.

    - An approved task with a landing shows its newest landing's batch run (kind `landing`), on
      every task of the batch though the run is recorded on its first; a landing queued or being
      checked with no run yet is waiting. An earlier landing's or batch's run is never shown.
    - Otherwise its newest pre-review run, superseded ones skipped, started since this round of
      work began: since it last entered its current status or, for a status after the work
      (completed, in review, sent back, approved), since it last entered one before them -- the run
      an agent's completion starts begins just before the move to `completed`, and the run that
      sends work back is the sent-back task's -- and never before its last send-back unless it is
      sent back now.
    - With no such run, a completed task whose hold asks for a run is waiting.
    - A running run still waiting for its check slot is waiting."""
    from . import project_checks

    holds = holds or {}
    status_of = dict(tasks)
    ids = list(status_of)
    states: Dict[str, Dict[str, str]] = {}
    if not ids:
        return states

    landings: Dict[str, TaskLanding] = {}
    for landing in (
        await session.execute(
            select(TaskLanding)
            .where(TaskLanding.project_id == project_id, TaskLanding.task_id.in_(ids))
            .order_by(TaskLanding.created_at, TaskLanding.order_key)
        )
    ).scalars():
        landings[landing.task_id] = landing

    # Every run a landing batch recorded: never a task's pre-review run.
    batch_runs: Dict[str, str] = {}
    for batch_id, run_id in await session.execute(
        select(LandingBatch.id, LandingBatch.check_run_id).where(
            LandingBatch.project_id == project_id, LandingBatch.check_run_id.is_not(None)
        )
    ):
        batch_runs[batch_id] = run_id
    landing_run_ids = set(batch_runs.values())

    wanted = {
        batch_runs[landing.batch_id]
        for task_id, landing in landings.items()
        if status_of[task_id] == "approved" and landing.batch_id in batch_runs
    }
    landing_runs: Dict[str, TaskCheckRun] = {}
    if wanted:
        for run in (
            await session.execute(select(TaskCheckRun).where(TaskCheckRun.id.in_(list(wanted))))
        ).scalars():
            landing_runs[run.id] = run

    # When this round of work began, per task (see above).
    opened: Dict[str, datetime] = {}
    sent_back: Dict[str, datetime] = {}
    for task_id, to_status, at in await session.execute(
        select(TaskTransition.task_id, TaskTransition.to_status, TaskTransition.created_at)
        .where(TaskTransition.project_id == project_id, TaskTransition.task_id.in_(ids))
        .order_by(TaskTransition.sequence)
    ):
        status = status_of[task_id]
        if to_status == "revision_needed":
            sent_back[task_id] = at
        if status in _AFTER_THE_WORK:
            if to_status not in _AFTER_THE_WORK:
                opened[task_id] = at
        elif to_status == status:
            opened[task_id] = at
    for task_id, at in sent_back.items():
        if status_of[task_id] != "revision_needed":
            since = opened.get(task_id)
            if since is None or _aware(at) > _aware(since):
                opened[task_id] = at

    newest: Dict[str, TaskCheckRun] = {}
    for run in (
        await session.execute(
            select(TaskCheckRun)
            .where(
                TaskCheckRun.project_id == project_id,
                TaskCheckRun.task_id.in_(ids),
                TaskCheckRun.state != project_checks.SUPERSEDED,
            )
            .order_by(TaskCheckRun.started_at, TaskCheckRun.id)
        )
    ).scalars():
        if run.id in landing_run_ids:
            continue
        since = opened.get(run.task_id)
        if since is not None and _aware(run.started_at) < _aware(since):
            continue
        newest[run.task_id] = run

    for task_id in ids:
        status = status_of[task_id]
        if status == "rejected":
            continue
        landing = landings.get(task_id)
        if status == "approved" and landing is not None:
            run = landing_runs.get(batch_runs.get(landing.batch_id or "", ""))
            if run is not None:
                state = run_check_state(run, waiting_for_slot=run.slot_at is None)
                if state is not None:
                    states[task_id] = {"kind": KIND_LANDING, "state": state}
            elif landing.state in ("queued", "checking"):
                states[task_id] = {"kind": KIND_LANDING, "state": "waiting"}
            continue
        run = newest.get(task_id)
        if run is not None:
            state = run_check_state(
                run, waiting_for_slot=run.id in project_checks._waiting_for_slot
            )
            if state is not None:
                states[task_id] = {"kind": KIND_PRE_REVIEW, "state": state}
                continue
        hold = holds.get(task_id)
        if hold is not None and hold.needs_a_run:
            states[task_id] = {"kind": KIND_PRE_REVIEW, "state": "waiting"}
    return states
