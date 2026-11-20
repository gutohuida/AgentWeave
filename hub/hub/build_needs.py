"""What a build needs from the operator, computed once (`profiles-threads-and-builds-everywhere`,
FR-4, design D2 and D3).

A build needs the operator when it is stopped with a task neither approved nor rejected, or when
any of its tasks does: an open stall, an unanswered question to the operator, or a give-up by the
mender. The build view's read (`build_read`) and the project's build list (`builds.project_rows`)
both read `needs_of_builds`, so the sidebar and the build view cannot disagree (needs-parity).

A dismissal (`dismiss`) stores the needs' `fingerprint`; the build stays dismissed only while its
fingerprint is the same, so a new stall, a new question or another stop brings it back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Build, Question, Stall, Task

_DONE = ("approved", "rejected")
STOPPED_TEXT = "The build stopped before its work was done"


@dataclass
class BuildNeeds:
    """One build's needs: each task's (null where it needs nothing), the build's, and the
    fingerprint a dismissal is keyed to."""

    tasks: Dict[str, Optional[Dict[str, str]]] = field(default_factory=dict)
    build: Optional[Dict[str, str]] = None
    fingerprint: List[str] = field(default_factory=list)


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _task_need(
    task: Task, stalls: Sequence[Stall], question: Optional[Question]
) -> tuple[Optional[Dict[str, str]], Optional[str]]:
    """The task's need and what identifies it (`stall:<id>`, `question:<id>`), or (None, None).
    *stalls* are the task's, oldest first."""
    if task.status in _DONE:
        return None, None
    for stall in reversed(stalls):
        if stall.outcome == "open":
            return {"kind": "stalled", "text": stall.reason or ""}, f"stall:{stall.id}"
    if question is not None:
        return {"kind": "question", "text": question.question}, f"question:{question.id}"
    for stall in reversed(stalls):
        if stall.outcome == "gave_up":
            return (
                {"kind": "gave-up", "text": stall.outcome_detail or stall.reason or ""},
                f"gave-up:{stall.id}",
            )
    return None, None


async def needs_of_builds(
    session: AsyncSession, project_id: str, builds: Sequence[Build]
) -> Dict[str, BuildNeeds]:
    """`BuildNeeds` for each of *builds*, by build id, in three grouped reads."""
    found: Dict[str, BuildNeeds] = {b.id: BuildNeeds() for b in builds}
    if not builds:
        return found
    tasks = list(
        (
            await session.execute(
                select(Task)
                .where(Task.build_id.in_(list(found)))
                .order_by(Task.created_at, Task.id)
            )
        )
        .scalars()
        .all()
    )
    task_ids = [t.id for t in tasks]
    stalls_of: Dict[str, List[Stall]] = {}
    asked: Dict[str, Question] = {}
    if task_ids:
        for stall in (
            (
                await session.execute(
                    select(Stall)
                    .where(Stall.project_id == project_id, Stall.task_id.in_(task_ids))
                    .order_by(Stall.first_seen_at, Stall.id)
                )
            )
            .scalars()
            .all()
        ):
            stalls_of.setdefault(stall.task_id, []).append(stall)
        for question in (
            (
                await session.execute(
                    select(Question)
                    .where(
                        Question.blocked_task_id.in_(task_ids),
                        Question.answered.is_(False),
                        Question.declined.is_(False),
                    )
                    .order_by(Question.created_at, Question.id)
                )
            )
            .scalars()
            .all()
        ):
            asked.setdefault(question.blocked_task_id, question)

    unfinished: Dict[str, bool] = {}
    for task in tasks:
        entry = found[task.build_id]
        need, mark = _task_need(task, stalls_of.get(task.id, []), asked.get(task.id))
        entry.tasks[task.id] = need
        if need is not None:
            entry.build = entry.build or need
            entry.fingerprint.append(mark)
        if task.status not in _DONE:
            unfinished[task.build_id] = True

    from .builds import STOPPED

    for build in builds:
        entry = found[build.id]
        if build.state == STOPPED and unfinished.get(build.id):
            entry.build = {"kind": "stopped", "text": build.stop_reason or STOPPED_TEXT}
            entry.fingerprint.append(f"stopped:{_iso(build.stopped_at) or ''}")
        entry.fingerprint.sort()
    return found


def attention_dismissed(build: Build, needs: BuildNeeds) -> bool:
    """Whether the operator dismissed *build* and its needs are still those they dismissed."""
    from .builds import RUNNING

    stored = build.attention_dismissed
    if build.state == RUNNING or needs.build is None or not isinstance(stored, dict):
        return False
    return stored.get("fingerprint") == needs.fingerprint


def dismiss(build: Build, needs: BuildNeeds, at: Optional[datetime] = None) -> None:
    """Record that the operator dismissed *build* against its needs now."""
    at = at or datetime.now(timezone.utc)
    build.attention_dismissed = {"at": at.isoformat(), "fingerprint": list(needs.fingerprint)}
