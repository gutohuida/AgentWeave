"""A flow advances when its work moves, not at its next tick.

Measured on the operator's Hub (loop-df5f74816122, 2026-10-25): every hand-off -- `completed ->
under_review` with a reviewer, `revision_needed -> in_progress` with the author, the next wave once
a prerequisite is approved -- happened only when the flow's `*/5` job fired. About twenty hand-offs
waited ~2.5 minutes each, and reviewers sat idle for part of every 27-43 minute review wait.

So a move that hands work on -- a task of a flow reaching `completed`, `revision_needed`,
`approved` or `rejected`, or a run bound to one ending -- asks for the flow's firing now. It is the
**same firing** the cron makes (`JobScheduler._fire_job_by_id`), so it decides exactly what the
tick would, and the tick stays as the backstop. Three properties keep that safe:

* **after the commit, never before**, and never for a rolled-back move (`after_commit`, the shape
  `chapters_job.fire_after_commit` uses), so the firing reads the move;
* **debounced and coalesced** per loop: one firing `DEBOUNCE_SECONDS` after the first request, and
  any request arriving meanwhile joins it (a reviewer's verdict and the end of its run are one
  hand-off, not two firings);
* **serialised with the tick** by `JobScheduler`'s per-job lock, so two firings of one job never
  decide at once -- each reads what the other committed, the idempotence every tick relies on.

Flows only (a loop with a document). A documentless loop's finished work awaits the operator's
landing, and its job filling an empty queue early would be a change nobody asked for. The job's
own moves (`origin="job"`) never ask: a firing does not re-fire itself.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Set

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: The statuses that hand a flow's work to somebody else.
HANDOFF_STATUSES = frozenset({"completed", "revision_needed", "approved", "rejected"})
#: Long enough to coalesce a verdict with the end of its run, short against a five-minute tick.
DEBOUNCE_SECONDS = 3.0

_PENDING_KEY = "flow_advance_pending"
#: Loops with a firing already requested and not yet started: a later request joins it.
_scheduled: Dict[str, "asyncio.Task[Any]"] = {}
#: Strong references to every task started here, so none is collected early.
_in_flight: Set["asyncio.Task[Any]"] = set()


def advance_after_commit(session: AsyncSession, loop_id: str) -> None:
    """Ask for *loop_id*'s firing once *session*'s root transaction commits, and never if it does
    not. Whether the loop is a live flow with an enabled job is judged when it fires."""
    session.sync_session.info.setdefault(_PENDING_KEY, set()).add(loop_id)


def request(loop_id: str) -> None:
    """Ask for *loop_id*'s firing now (debounced). Never raises."""
    if loop_id in _scheduled:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_advance_soon(loop_id))
    _scheduled[loop_id] = task
    _in_flight.add(task)
    task.add_done_callback(_in_flight.discard)


def after_run(project_id: str, run_id: str) -> None:
    """A run has ended and its work is committed: if it was bound to a flow's task, ask for the
    flow's firing (the author's run ending is when its finished work becomes reviewable). Never
    raises; called right after the run's closing commit."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_after_run(project_id, run_id))
    _in_flight.add(task)
    task.add_done_callback(_in_flight.discard)


async def settled() -> None:
    """Wait for every request in flight (tests)."""
    while _in_flight:
        await asyncio.gather(*list(_in_flight), return_exceptions=True)


async def _after_run(project_id: str, run_id: str) -> None:
    from .db.engine import async_session_factory
    from .db.models import Run, Task

    try:
        async with async_session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None or run.project_id != project_id or not run.task_id:
                return
            task = await session.get(Task, run.task_id)
            loop_id = task.loop_id if task is not None else None
        if loop_id:
            request(loop_id)
    except Exception:  # noqa: BLE001 -- a background request must not raise
        logger.debug("could not ask for a flow's firing after run %s", run_id, exc_info=True)


async def _advance_soon(loop_id: str) -> None:
    from .db.engine import async_session_factory
    from .db.models import AIJob, Loop
    from .scheduler import get_scheduler

    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)
    finally:
        # Released before the firing, so a move the firing itself causes, or one arriving while it
        # runs, asks for a firing after it rather than being lost inside it.
        _scheduled.pop(loop_id, None)
    try:
        async with async_session_factory() as session:
            loop = await session.get(Loop, loop_id)
            if (
                loop is None
                or loop.spec_document_id is None
                or loop.ending_state is not None
                or loop.archived_at is not None
            ):
                return
            job = await session.get(AIJob, loop.job_id)
            if job is None or not job.enabled or job.archived_at is not None:
                return
            job_id = job.id
        scheduler = get_scheduler()
        if scheduler is None:
            return
        await scheduler._fire_job_by_id(job_id)
    except Exception:  # noqa: BLE001 -- a background firing must not raise
        logger.warning("flow %s could not advance early; its tick will", loop_id, exc_info=True)


@event.listens_for(Session, "after_commit")
def _request_pending(session: Session) -> None:
    if session.in_nested_transaction():
        return
    for loop_id in session.info.pop(_PENDING_KEY, set()):
        request(loop_id)


@event.listens_for(Session, "after_transaction_end")
def _drop_pending(session: Session, transaction) -> None:
    if transaction.parent is None:
        session.info.pop(_PENDING_KEY, None)
