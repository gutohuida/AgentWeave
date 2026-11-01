"""The project's record per model: what each model built, was sent back for, and cost.

`every-task-comes-with-a-recommended-builder-and-checker` FR-14. The author of a spec judges which
model suits a task; this is the figures it judges by. The Hub holds no price table and no scoring
rule -- it reports counts and the API-equivalent cost each turn already recorded, and the author
judges.

Attribution is by the model that **ran** a task's build turns (`TurnUsage.model` of the runs the
runtime bound to the task, `Run.task_id`), never by the task's assignee: an agent can be rebound
to another model between tasks, and crediting the agent would credit the wrong model. Review turns
are bound by `Run.review_task_id`, not `task_id`, so they are not build turns.

A task whose build turns ran under more than one model counts under the model of its latest turn
that names one (the model that finished it), and lists the others in `models_seen`. A turn with no
usage row, or with a row carrying no price, is **unpriced**: counted as a turn and reported, never
added to the cost as zero.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Run, Task, TaskTransition, TurnUsage
from .task_transitions import SEND_BACK_CLASSES

UNKNOWN_MODEL = "unknown"


def _row() -> Dict[str, Any]:
    return {
        "tasks_built": 0,
        "tasks_approved": 0,
        "send_backs": {"total": 0, **dict.fromkeys(SEND_BACK_CLASSES, 0), "unclassified": 0},
        "turns": 0,
        "priced_turns": 0,
        "unpriced_turns": 0,
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
    moves = list(
        (
            await session.execute(
                select(TaskTransition)
                .join(Task, Task.id == TaskTransition.task_id)
                .where(Task.project_id == project_id, TaskTransition.to_status == "revision_needed")
            )
        )
        .scalars()
        .all()
    )

    by_task: Dict[str, List[Run]] = {}
    for run in runs:
        if run.task_id in tasks:
            by_task.setdefault(run.task_id, []).append(run)

    models: Dict[str, Dict[str, Any]] = {}
    model_of: Dict[str, str] = {}
    for task_id, task_runs in by_task.items():
        named = [usage[r.id].model for r in task_runs if r.id in usage and usage[r.id].model]
        model = named[-1] if named else UNKNOWN_MODEL
        model_of[task_id] = model
        row = models.setdefault(model, _row())
        task = tasks[task_id]
        row["tasks_built"] += 1
        row["tasks_approved"] += 1 if task.status == "approved" else 0
        for run in task_runs:
            row["turns"] += 1
            measured = usage.get(run.id)
            micros: Optional[int] = measured.api_equivalent_usd_micros if measured else None
            if micros is None:
                row["unpriced_turns"] += 1
            else:
                row["priced_turns"] += 1
                row["cost_usd_micros"] += micros
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
        },
        "note": (
            "Cost is the API-equivalent figure each priced turn recorded, in millionths of a "
            "dollar; an unpriced turn is counted in unpriced_turns and added to no cost. A task "
            "counts under the model of its latest build turn that names one."
        ),
    }
