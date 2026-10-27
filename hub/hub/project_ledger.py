"""The project's ledger (slice project-ledger of the visibility roadmap).

One read of what the Hub already records about a project, in lanes: what merged into main (and what
was skipped), what was spent over time by agent and by task, the runs that diverged from their
task, the messages agents sent each other, where the work came from, and the notices the log would
otherwise repeat line by line (`context_warning`, folded into one counted row).

Every lane is newest first except the spend series, which is by day oldest first so it draws left to
right. Nothing here writes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import work_tally
from .db.models import EventLog, Message, RunDivergence, Task, TaskIntegration

#: The notice kinds folded into one counted row each rather than listed (roadmap decision 4).
FOLDED_NOTICES = ("context_warning",)

#: How many rows a lane returns; the lane says how many there are in all.
LANE_LIMIT = 200

#: Who an operator message is from or to, as `messages` records it.
OPERATOR_NAMES = {"user", "operator"}


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _usd(micros: Optional[int]) -> Optional[float]:
    """Dollars, or None when no record reports a cost: unknown is never $0."""
    return None if micros is None else round(micros / 1_000_000, 4)


def _origin(task: Task) -> str:
    """Where a task came from: a spec document's approval, a loop, an agent's run, or the operator."""
    if task.spec_document_id:
        return "spec"
    if task.loop_id:
        return "loop"
    if task.created_by_run_id:
        return "agent"
    return "operator"


async def ledger(session: AsyncSession, project_id: str) -> Dict[str, Any]:
    tasks = {
        row.id: row
        for row in (await session.execute(select(Task).where(Task.project_id == project_id)))
        .scalars()
        .all()
    }

    def title(task_id: Optional[str]) -> Optional[str]:
        task = tasks.get(task_id) if task_id else None
        return task.title if task else None

    # Merges into main, and integrations that were skipped, newest first.
    integrations = (
        (
            await session.execute(
                select(TaskIntegration)
                .where(TaskIntegration.project_id == project_id)
                .order_by(TaskIntegration.created_at.desc(), TaskIntegration.id.desc())
            )
        )
        .scalars()
        .all()
    )
    merges = [
        {
            "id": row.id,
            "task_id": row.task_id,
            "task_title": title(row.task_id),
            "outcome": row.outcome,
            "commit_sha": row.commit_sha,
            "source_branch": row.source_branch,
            "target_branch": row.target_branch,
            "reason": row.reason,
            "actor_kind": row.actor_kind,
            "actor": row.actor,
            "at": _iso(row.created_at),
        }
        for row in integrations
    ]

    # Spend: every figure comes from the work tally (`work_tally.py`), the one place that sums them.
    whole = await work_tally.tally(session, project_id)
    project_row = whole["project"]
    spend = {
        "total_usd": _usd(project_row["cost_micros"]["total"]),
        "total_tokens": project_row["tokens"] or 0,
        "worker_usd": _usd(whole["workers"]["cost_micros"]["total"]) or 0.0,
        "unpriced": project_row["unpriced"],
        "by_day": work_tally.spend_by_day(whole),
        "by_agent": sorted(
            (
                {
                    "agent": group["key"],
                    "usd": _usd(group["row"]["cost_micros"]["total"]),
                    "tokens": group["row"]["tokens"] or 0,
                    "turns": group["row"]["turns"],
                    "unpriced": group["row"]["unpriced"],
                }
                for group in whole["groups"]["agent"]
                if group["key"] is not None and group["row"]["turns"]
            ),
            key=lambda entry: (-(entry["usd"] or 0), -entry["tokens"], entry["agent"]),
        ),
        "by_task": sorted(
            (
                {
                    "task_id": task_id,
                    "task_title": title(task_id),
                    "usd": _usd(figures.get("usd")),
                    "tokens": figures.get("tokens", 0),
                    "turns": figures.get("turns", 0),
                }
                for task_id, figures in whole["spend"]["by_task"].items()
            ),
            key=lambda entry: (-(entry["usd"] or 0), -entry["tokens"], entry["task_id"]),
        ),
    }

    divergence_rows = (
        (
            await session.execute(
                select(RunDivergence)
                .where(RunDivergence.project_id == project_id)
                .order_by(RunDivergence.created_at.desc(), RunDivergence.sequence.desc())
            )
        )
        .scalars()
        .all()
    )
    divergences = [
        {
            "id": row.id,
            "run_id": row.run_id,
            "agent": row.agent,
            "task_id": row.task_id,
            "task_title": title(row.task_id),
            "task_status_at_end": row.task_status_at_end,
            "run_exit_status": row.run_exit_status,
            "policy_applied": row.policy_applied,
            "outcome": row.outcome,
            "at": _iso(row.created_at),
            "resolved_at": _iso(row.resolved_at),
        }
        for row in divergence_rows
    ]

    message_rows = (
        (
            await session.execute(
                select(Message)
                .where(
                    Message.project_id == project_id,
                    Message.sender.notin_(OPERATOR_NAMES),
                    Message.recipient.notin_(OPERATOR_NAMES),
                )
                .order_by(Message.timestamp.desc(), Message.id.desc())
                .limit(LANE_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    messages = [
        {
            "id": row.id,
            "sender": row.sender,
            "recipient": row.recipient,
            "subject": row.subject,
            "excerpt": (row.content or "")[:280],
            "task_id": row.task_id,
            "task_title": title(row.task_id),
            "at": _iso(row.timestamp),
        }
        for row in message_rows
    ]

    origins: Dict[str, int] = {"spec": 0, "loop": 0, "agent": 0, "operator": 0}
    for task in tasks.values():
        origins[_origin(task)] += 1

    notices = []
    for kind in FOLDED_NOTICES:
        count, first, last = (
            await session.execute(
                select(
                    func.count(EventLog.id),
                    func.min(EventLog.timestamp),
                    func.max(EventLog.timestamp),
                ).where(EventLog.project_id == project_id, EventLog.event_type == kind)
            )
        ).one()
        if not count:
            continue
        agents = (
            await session.execute(
                select(EventLog.agent, func.count(EventLog.id))
                .where(EventLog.project_id == project_id, EventLog.event_type == kind)
                .group_by(EventLog.agent)
                .order_by(func.count(EventLog.id).desc())
            )
        ).all()
        notices.append(
            {
                "kind": kind,
                "count": count,
                "first_at": _iso(first),
                "last_at": _iso(last),
                "by_agent": [{"agent": agent or None, "count": n} for agent, n in agents],
            }
        )

    return {
        "merges": merges,
        "spend": spend,
        "divergences": divergences,
        "messages": messages,
        "origins": origins,
        "notices": notices,
        "totals": {
            "merged": sum(1 for m in merges if m["outcome"] == "merged"),
            "integrations": len(merges),
            "divergences": len(divergences),
            "open_divergences": sum(1 for d in divergences if d["resolved_at"] is None),
            "tasks": len(tasks),
        },
    }
