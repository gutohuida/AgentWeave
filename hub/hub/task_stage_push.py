"""Each task's stage, pushed to the open pages the moment it may have moved (`task-stages-in-the-
build-view-and-dependency-map` FR-6, FR-11).

The build view, the board and the map each read the stage from their own route, and on a busy Hub
those routes answer the same event up to two seconds apart (drive runs 174800 and 184251): the
pages agree only once the slowest read is back. A `task_stage` frame carries the stage itself,
derived once by `stage_reads` -- the derivation every one of those routes uses -- and reaches every
open page at the same moment, so they move together and the reads that follow only confirm it.

Two things name the tasks whose stage may have moved: an event that names a task (or a run, whose
task is looked up), and a commit that wrote a task, a check run, a landing, a run's status or a
queue entry. The commit is what makes the stage readable, so a frame always follows the write it
reflects. Frames are coalesced per project, one derivation in flight at a time, and none is
derived for a project nobody is listening to. Never raises into a writer.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Iterable, Optional, Set, Tuple

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

STAGE_EVENT = "task_stage"

#: The fields a frame carries for each task, as the task list's rows carry them.
STAGE_FIELDS = ("stage", "stage_since", "stage_detail", "stage_waits_on", "check_state")

_TOUCHED_KEY = "aw_stage_touched"

#: project id -> what to derive next: task ids, and run ids whose task is looked up.
_pending: Dict[str, Tuple[Set[str], Set[str]]] = {}
_running: Set[str] = set()


def _listening(project_id: str) -> bool:
    from .sse import sse_manager

    return sse_manager.has_listeners(project_id)


def note(
    project_id: Optional[str],
    task_ids: Iterable[Optional[str]] = (),
    run_ids: Iterable[Optional[str]] = (),
) -> None:
    """Derive and push the stage of *task_ids* (and of *run_ids*' tasks) soon, once."""
    if not project_id:
        return
    tasks = {t for t in task_ids if isinstance(t, str) and t}
    runs = {r for r in run_ids if isinstance(r, str) and r}
    if not (tasks or runs) or not _listening(project_id):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # a write outside the Hub's loop: nobody to push to
        return
    pending_tasks, pending_runs = _pending.setdefault(project_id, (set(), set()))
    pending_tasks.update(tasks)
    pending_runs.update(runs)
    if project_id in _running:
        return  # the derivation in flight reads these too, once it is done with the last ones
    _running.add(project_id)
    loop.create_task(_flush(project_id))


def note_event(project_id: str, event_type: str, data: Any) -> None:
    """The tasks an event names: `task_id`/`task_ids`, a `task_*` event's own `id`, a run's id."""
    if event_type == STAGE_EVENT or not isinstance(data, dict):
        return
    tasks = [data.get("task_id")]
    if isinstance(data.get("task_ids"), list):
        tasks += data["task_ids"]
    if event_type.startswith("task_"):
        tasks.append(data.get("id"))
    runs = [data.get("run_id")] if event_type.startswith("run_") else []
    note(project_id, tasks, runs)


async def _flush(project_id: str) -> None:
    from .db import engine as db_engine
    from .sse import sse_manager

    try:
        while project_id in _pending:
            tasks, runs = _pending.pop(project_id)
            async with db_engine.async_session_factory() as session:
                frame = await stage_frame(session, project_id, tasks, runs)
            if frame["tasks"]:
                sse_manager.publish(project_id, STAGE_EVENT, frame)
    except Exception:  # noqa: BLE001 -- the reads still carry the stage; a frame is a head start
        logger.exception("task stage push for %s failed", project_id)
        _pending.pop(project_id, None)
    finally:
        _running.discard(project_id)


async def stage_frame(
    session, project_id: str, task_ids: Set[str], run_ids: Set[str]
) -> Dict[str, Any]:
    """`{"tasks": [{"id", <STAGE_FIELDS>}]}` for *task_ids*, the tasks *run_ids* work on or review,
    and their landing batches' other tasks, derived as every task surface's route derives it."""
    from .api.v1.tasks import stage_rows
    from .db.models import InboundQueueEntry, Run, Task, TaskLanding

    wanted = set(task_ids)
    if run_ids:
        wanted.update(
            t
            for (t,) in await session.execute(
                select(Run.task_id).where(Run.id.in_(run_ids), Run.task_id.isnot(None))
            )
        )
        wanted.update(
            t
            for (t,) in await session.execute(
                select(InboundQueueEntry.review_task_id).where(
                    InboundQueueEntry.delivered_in_run_id.in_(run_ids),
                    InboundQueueEntry.review_task_id.isnot(None),
                )
            )
        )
    if not wanted:
        return {"tasks": []}
    # A landing batch's run is recorded on its first task but shown on every task of the batch
    # (FR-4): its mates move with it, or one shows the run ended while another still shows it running.
    batches = select(TaskLanding.batch_id).where(
        TaskLanding.task_id.in_(wanted), TaskLanding.batch_id.isnot(None)
    )
    wanted.update(
        t
        for (t,) in await session.execute(
            select(TaskLanding.task_id).where(
                TaskLanding.project_id == project_id, TaskLanding.batch_id.in_(batches)
            )
        )
    )
    rows = (
        (
            await session.execute(
                select(Task).where(Task.project_id == project_id, Task.id.in_(wanted))
            )
        )
        .scalars()
        .all()
    )
    return {"tasks": await stage_rows(session, project_id, list(rows))}


# --------------------------------------------------------------------------- the commit seam


def _touched(obj: Any) -> Optional[Tuple[str, str]]:
    """(project id, task id) of a row whose write can move a task's stage, else None."""
    from .db.models import InboundQueueEntry, Run, Task, TaskCheckRun, TaskLanding

    project_id = getattr(obj, "project_id", None)
    if isinstance(obj, Task):
        return (project_id, obj.id) if obj.id else None
    if isinstance(obj, (TaskCheckRun, TaskLanding)):
        return (project_id, obj.task_id) if obj.task_id else None
    if isinstance(obj, Run):
        # A heartbeat rewrites the run every few seconds; only its status moves a stage.
        state = inspect(obj)
        if not obj.task_id or not (state.pending or state.attrs.status.history.has_changes()):
            return None
        return (project_id, obj.task_id)
    if isinstance(obj, InboundQueueEntry):
        task_id = obj.review_task_id or obj.task_id
        return (project_id, task_id) if task_id else None
    return None


@event.listens_for(Session, "after_flush")
def _collect(session: Session, flush_context) -> None:  # noqa: ANN001
    try:
        touched = session.info.setdefault(_TOUCHED_KEY, set())
        for obj in (*session.new, *session.dirty):
            hit = _touched(obj)
            if hit and hit[0]:
                touched.add(hit)
    except Exception:  # noqa: BLE001 -- never fail a write for a push
        logger.exception("collecting the tasks a flush touched failed")


@event.listens_for(Session, "after_commit")
def _push_committed(session: Session) -> None:
    if session.in_nested_transaction():
        return
    touched = session.info.pop(_TOUCHED_KEY, None)
    if not touched:
        return
    try:
        by_project: Dict[str, Set[str]] = {}
        for project_id, task_id in touched:
            by_project.setdefault(project_id, set()).add(task_id)
        for project_id, tasks in by_project.items():
            note(project_id, tasks)
    except Exception:  # noqa: BLE001 -- the commit has landed
        logger.exception("pushing committed task stages failed")


@event.listens_for(Session, "after_rollback")
def _drop_touched(session: Session) -> None:
    session.info.pop(_TOUCHED_KEY, None)
