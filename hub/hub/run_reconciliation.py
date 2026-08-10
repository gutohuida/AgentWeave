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
from .db.models import Run
from .inbound_queue import return_run_entries
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

            payload = {
                "agent": run.agent,
                "run_id": run.id,
                "pid": run.pid,
                "returned_entry_ids": returned_entry_ids,
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
