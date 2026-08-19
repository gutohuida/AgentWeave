"""Crash reconciliation on Hub start (task 3.8, design.md Decision 8).

A Hub restart — crash, deploy, manual bounce — leaves behind `Run` rows still marked
`"running"` whose owning process may or may not still exist; the restarted process has no
in-memory `PtySession` for any of them, only what's persisted (`pid`, `agent`, `project_id`).
Without this pass those rows stay `"running"` forever: the agent's status badge would show
"running" indefinitely, and `POST /agent/trigger`'s "already has a run in progress" guard
would permanently refuse new runs for that agent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from .db.engine import async_session_factory
from .db.models import JobRun, Run
from .inbound_queue import abandoned_for_run, return_run_entries
from .permission_requests import expire_pending_for_run
from .pty_runner import pid_alive
from .sse import sse_manager
from .utils import persist_event

logger = logging.getLogger(__name__)


async def reconcile_interrupted_runs() -> int:
    """Mark every `Run` row still `"running"` whose process is no longer alive as
    `"interrupted"`, persisting and broadcasting a `run_interrupted` event for each.

    Returns the number of runs reconciled.
    """
    reconciled = 0
    agents_to_schedule = set()
    divergences_to_evaluate: list[str] = []
    async with async_session_factory() as db:
        result = await db.execute(select(Run).where(Run.status == "running"))
        for run in result.scalars().all():
            if run.pid is not None and pid_alive(run.pid):
                continue

            run.status = "interrupted"
            run.ended_at = datetime.now(timezone.utc)
            reconciled += 1
            # The restart case is the one this matters most for: a Hub bounced while an operator
            # decision was on screen leaves a row nobody will ever poll again, and without this
            # the card outlives not just its run but the Hub process that served it.
            await expire_pending_for_run(db, run.id)
            returned_entry_ids = await return_run_entries(db, run.id)
            agents_to_schedule.add((run.project_id, run.agent))
            # A crash is a run boundary too, and a bound run that died holding its task is exactly
            # what the operator wants to know about. Deferred until after the commit below, so the
            # check reads the interrupted status rather than "running".
            #
            # Skipped when this run's input went back to the queue: the work is about to be handed
            # to a new run that will bind to the same task, so nothing has been dropped.
            if run.task_id and not returned_entry_ids:
                divergences_to_evaluate.append(run.id)

            # An entry the Hub has given up on is not coming back, so it is named separately
            # rather than folded into the returned set — those are the ids a later run will pick
            # up, and these are the ones nothing ever will.
            abandoned = await abandoned_for_run(db, run.id)
            payload = {
                "agent": run.agent,
                "run_id": run.id,
                "pid": run.pid,
                "returned_entry_ids": returned_entry_ids,
                "abandoned_entry_ids": [entry.id for entry in abandoned],
            }
            await persist_event(
                db,
                run.project_id,
                "run_interrupted",
                payload,
                agent=run.agent,
                severity="warn",
            )
            await sse_manager.broadcast(run.project_id, "run_interrupted", payload)

        if reconciled:
            await db.commit()

    for diverged_run_id in divergences_to_evaluate:
        from .run_divergence import evaluate_run_end

        await evaluate_run_end(diverged_run_id)

    if reconciled:
        logger.warning(
            "Reconciled %d orphaned run(s) to status=interrupted on Hub start", reconciled
        )
        from .turn_scheduler import schedule_agent

        for project_id, agent in agents_to_schedule:
            await schedule_agent(project_id, agent)
    return reconciled


async def reconcile_stale_job_runs() -> int:
    """Mark every `JobRun` row still `"in_progress"` whose firing has no live `Run` behind
    it as `"failed"` (task A4.5, design D13).

    `JobRun` and `Run` share no foreign key, only `conversation_id`
    (`db/models.py`'s own comment on `JobRun.conversation_id`), the same correlation
    `scheduler.py::finalize_job_run_for_conversation` uses on the normal end-of-turn path —
    this is that same correlation, run in the other direction (from a stuck `JobRun` to its
    `Run`) for the firings a crash meant that path never reached. Call this AFTER
    `reconcile_interrupted_runs()` in the same startup pass: a `Run` this restart just found
    dead has already been flipped to `"interrupted"` by the time this reads `Run.status`, so
    a plain `!= "running"` check is enough without re-deriving `pid_alive` here too.

    A `JobRun` can reach `"in_progress"` with no `Run` row ever created at all — not just one
    whose `Run` died — when the firing queued its entry but nothing ever spawned a process for
    it (an agent with no runner bound is the live example this was diagnosed against on the
    trial Hub: `job-0b490274`, agent `claude-1`, `runner_id` NULL). That firing is exactly as
    stuck as a crashed one and gets the same treatment here, not a narrower one.
    """
    reconciled = 0
    async with async_session_factory() as db:
        result = await db.execute(select(JobRun).where(JobRun.status == "in_progress"))
        for job_run in result.scalars().all():
            run = None
            if job_run.conversation_id is not None:
                run_result = await db.execute(
                    select(Run).where(Run.conversation_id == job_run.conversation_id)
                )
                run = run_result.scalars().first()
            if run is not None and run.status == "running":
                continue

            job_run.status = "failed"
            job_run.error_summary = "Reconciled on Hub start: no live run behind this firing"
            reconciled += 1

        if reconciled:
            await db.commit()

    if reconciled:
        logger.warning("Reconciled %d stale job run(s) to status=failed on Hub start", reconciled)
    return reconciled
