"""The project's record per model: what each model built, was sent back for, and cost.

`every-task-comes-with-a-recommended-builder-and-checker` FR-14. The author of a spec judges which
model suits a task; this is the figures it judges by. The Hub holds no price table and no scoring
rule -- it reports counts and the API-equivalent cost each turn already recorded, and the author
judges.

Attribution is by the model that **ran** a task's build turns (`TurnUsage.model` of the runs the
runtime bound to the task, `Run.task_id`), never by the task's assignee: an agent can be rebound
to another model between tasks, and crediting the agent would credit the wrong model. A review
turn also carries `Run.task_id`, and the queue entry that started it may name `review_task_id` or,
when a message started it, only `task_id`. So a review turn is marked by what it did: a run that
moved the task to `approved`, `revision_needed` or `rejected` gave a verdict, and a run delivered an
entry naming `review_task_id` is a review. Both are the checker's, not the builder's, and are left out.

A task counts, with its send-backs, under the model of the run behind its latest move to
`completed` (the run that finished the build), else under the latest remaining build turn that
names a model; the other models its build turns ran under are listed in `models_seen`. Each turn's count and cost go under the model that ran *that turn*. A finished turn
with no usage row, or with a row carrying no price, is **unpriced**: counted and reported, never
added to the cost as zero. A turn still running has no usage row yet and is reported as
`running_turns`, neither priced nor unpriced.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import InboundQueueEntry, Run, Task, TaskTransition, TurnUsage
from .task_transitions import SEND_BACK_CLASSES

UNKNOWN_MODEL = "unknown"
_VERDICTS = ("approved", "revision_needed", "rejected")


def _row() -> Dict[str, Any]:
    return {
        "tasks_built": 0,
        "tasks_approved": 0,
        "send_backs": {"total": 0, **dict.fromkeys(SEND_BACK_CLASSES, 0), "unclassified": 0},
        "turns": 0,
        "priced_turns": 0,
        "unpriced_turns": 0,
        "running_turns": 0,
        "cost_usd_micros": 0,
        "tasks": [],
    }


async def model_record(session: AsyncSession, project_id: str) -> Dict[str, Any]:
    """The record per model for *project_id*, models in name order."""
    runs = list(
        (
            await session.execute(
                select(Run)
                .where(Run.project_id == project_id, Run.task_id.is_not(None))
                .order_by(Run.started_at, Run.id)
            )
        )
        .scalars()
        .all()
    )
    usage = {
        row.run_id: row
        for row in (
            await session.execute(select(TurnUsage).where(TurnUsage.project_id == project_id))
        )
        .scalars()
        .all()
    }
    tasks = {
        task.id: task
        for task in (await session.execute(select(Task).where(Task.project_id == project_id)))
        .scalars()
        .all()
    }
    all_moves = list(
        (
            await session.execute(
                select(TaskTransition)
                .join(Task, Task.id == TaskTransition.task_id)
                .where(
                    Task.project_id == project_id,
                    TaskTransition.to_status.in_(_VERDICTS + ("completed",)),
                )
                .order_by(TaskTransition.sequence)
            )
        )
        .scalars()
        .all()
    )
    moves = [m for m in all_moves if m.to_status == "revision_needed"]
    # A run that moved a task to a verdict status gave a verdict: it is the checker's turn,
    # whatever queue entry started it (a message names only `task_id`, not `review_task_id`).
    verdict_runs = {m.run_id for m in all_moves if m.to_status in _VERDICTS and m.run_id}
    # The run behind each task's latest move to `completed` is the run that finished the build.
    finishing_run: Dict[str, str] = {}
    for m in all_moves:
        if m.to_status == "completed" and m.run_id:
            finishing_run[m.task_id] = m.run_id

    review_runs = set(
        (
            await session.execute(
                select(InboundQueueEntry.delivered_in_run_id).where(
                    InboundQueueEntry.project_id == project_id,
                    InboundQueueEntry.review_task_id.is_not(None),
                    InboundQueueEntry.delivered_in_run_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    by_task: Dict[str, List[Run]] = {}
    for run in runs:
        if run.task_id in tasks and run.id not in review_runs and run.id not in verdict_runs:
            by_task.setdefault(run.task_id, []).append(run)

    models: Dict[str, Dict[str, Any]] = {}
    model_of: Dict[str, str] = {}
    for task_id, task_runs in by_task.items():
        named = [usage[r.id].model for r in task_runs if r.id in usage and usage[r.id].model]
        finished = usage.get(finishing_run.get(task_id, ""))
        if finished is not None and finished.model:
            model = finished.model
        else:
            model = named[-1] if named else UNKNOWN_MODEL
        model_of[task_id] = model
        row = models.setdefault(model, _row())
        task = tasks[task_id]
        row["tasks_built"] += 1
        row["tasks_approved"] += 1 if task.status == "approved" else 0
        for run in task_runs:
            measured = usage.get(run.id)
            if measured is None and run.status == "running":
                row["running_turns"] += 1
                continue
            turn_row = models.setdefault(
                (measured.model if measured and measured.model else UNKNOWN_MODEL), _row()
            )
            turn_row["turns"] += 1
            micros: Optional[int] = measured.api_equivalent_usd_micros if measured else None
            if micros is None:
                turn_row["unpriced_turns"] += 1
            else:
                turn_row["priced_turns"] += 1
                turn_row["cost_usd_micros"] += micros
        row["tasks"].append(
            {
                "task_id": task_id,
                "readable_id": task.readable_id,
                "status": task.status,
                "models_seen": sorted(set(named)),
            }
        )

    for move in moves:
        model = model_of.get(move.task_id)
        if model is None:
            continue  # a send-back of a task nothing built under a recorded run
        sends = models[model]["send_backs"]
        sends["total"] += 1
        sends[move.reason_class if move.reason_class in SEND_BACK_CLASSES else "unclassified"] += 1

    return {
        "models": [{"model": name, **models[name]} for name in sorted(models)],
        "sample": {
            "tasks_built": sum(r["tasks_built"] for r in models.values()),
            "turns": sum(r["turns"] for r in models.values()),
            "unpriced_turns": sum(r["unpriced_turns"] for r in models.values()),
            "running_turns": sum(r["running_turns"] for r in models.values()),
        },
        "note": (
            "Cost is the API-equivalent figure each priced turn recorded, in millionths of a "
            "dollar; an unpriced turn is counted in unpriced_turns and added to no cost. A task "
            "counts under the model of the run that completed it, else its latest build turn that names one; "
            "review and verdict turns are excluded, and "
            "each turn's cost is under the model that ran it."
        ),
    }
