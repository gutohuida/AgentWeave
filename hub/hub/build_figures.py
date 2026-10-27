"""What a build has taken so far: its runs, where its wall time went and who its money went to
(`the-spec-page-redesigned`, requirement `build-progress-on-the-document`).

Read from what `builds.py` and the task machine already record -- the runs bound to the build's tasks,
their `turn_usage`, the tasks' transitions and their check runs -- and never stored, so a figure can
only be as stale as the read. Roadmap slice G will replace this with one tally shared by every
surface; this module is the single place the page's figures come from, so that swap is one file.

Wall time is the build's elapsed time from its start to now (or to when it stopped), split by what
the build was doing at each instant, in this order of precedence: **building** (some task is being
worked), **checks** (the project's checks are running on some task), **waiting for review** (some
task is done and not yet decided), **waiting to be handed out** (a task is ready or assigned and
nobody has it). An instant where every task is decided, or the build has none, counts toward no part.
Tasks run side by side, so these are seconds of the build's clock, not task-seconds.

Cost is the API-equivalent cost of every turn of the build's runs, split by who spent it: the lead
(runs in the lead's build conversation), the reviewers (an agent in the build's reviewer pool and not
among its builders), and the builders (everything else bound to a task of the build).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Build, Run, Task, TaskCheckRun, TaskTransition, TurnUsage

MICROS = 1_000_000

_BUILDING = {"in_progress"}
_REVIEW = {"completed", "under_review", "revision_needed"}
_WAITING = {"pending", "assigned"}
#: Precedence when several tasks are in different states at once.
_PARTS = ("building", "checks", "review", "waiting")


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _part(statuses: List[str], checking: int) -> Optional[str]:
    if any(s in _BUILDING for s in statuses):
        return "building"
    if checking > 0:
        return "checks"
    if any(s in _REVIEW for s in statuses):
        return "review"
    if any(s in _WAITING for s in statuses):
        return "waiting"
    return None


async def _time(session: AsyncSession, build: Build, now: datetime) -> Dict[str, int]:
    start = _aware(build.created_at)
    end = _aware(build.stopped_at) or now
    split = dict.fromkeys(_PARTS, 0)
    if start is None or end <= start:
        return split
    tasks = (await session.execute(select(Task).where(Task.build_id == build.id))).scalars().all()
    if not tasks:
        return split
    ids = [t.id for t in tasks]
    transitions = (
        (
            await session.execute(
                select(TaskTransition)
                .where(TaskTransition.task_id.in_(ids))
                .order_by(TaskTransition.sequence)
            )
        )
        .scalars()
        .all()
    )
    check_runs = (
        (await session.execute(select(TaskCheckRun).where(TaskCheckRun.task_id.in_(ids))))
        .scalars()
        .all()
    )

    # Each task's status when the build began, then every change inside the build's span.
    status: Dict[str, str] = {}
    changes: List[Tuple[datetime, str, str]] = []
    for transition in transitions:
        when = _aware(transition.created_at)
        if when is not None and when <= start:
            status[transition.task_id] = transition.to_status
        elif when is not None:
            status.setdefault(transition.task_id, transition.from_status)
            changes.append((when, transition.task_id, transition.to_status))
    for task in tasks:
        status.setdefault(task.id, "pending")
    checking = 0
    toggles: List[Tuple[datetime, int]] = []
    for run in check_runs:
        began, ended = _aware(run.started_at), _aware(run.ended_at) or end
        if began is None:
            continue
        if began <= start < ended:
            checking += 1
        elif began > start:
            toggles.append((began, 1))
        if start < ended <= end and began <= ended:
            toggles.append((ended, -1))

    events: List[Tuple[datetime, int, Any]] = [(c[0], 0, c) for c in changes] + [
        (t[0], 1, t) for t in toggles
    ]
    events.sort(key=lambda e: (e[0], e[1]))
    cursor = start
    for when, kind, payload in events:
        when = min(max(when, start), end)
        part = _part(list(status.values()), checking)
        if part is not None and when > cursor:
            split[part] += int((when - cursor).total_seconds())
        cursor = max(cursor, when)
        if kind == 0:
            status[payload[1]] = payload[2]
        else:
            checking += payload[1]
    part = _part(list(status.values()), checking)
    if part is not None and end > cursor:
        split[part] += int((end - cursor).total_seconds())
    return split


async def figures(
    session: AsyncSession, build: Build, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """`{id, runs, time, cost}` for one build, as the document page draws it."""
    now = now or datetime.now(timezone.utc)
    task_ids = select(Task.id).where(Task.build_id == build.id)
    bound = Run.task_id.in_(task_ids)
    where = bound
    if build.lead_conversation_id:
        where = bound | (Run.conversation_id == build.lead_conversation_id)

    runs = (
        await session.execute(
            select(func.count(Run.id)).where(Run.project_id == build.project_id, where)
        )
    ).scalar_one()

    rows = (
        await session.execute(
            select(Run.agent, Run.conversation_id, TurnUsage.api_equivalent_usd_micros)
            .select_from(TurnUsage)
            .join(Run, Run.id == TurnUsage.run_id)
            .where(Run.project_id == build.project_id, where)
        )
    ).all()
    builders, reviewers = set(build.builders or []), set(build.reviewers or [])
    micros = {"build": 0, "review": 0, "lead": 0}
    for agent, conversation_id, cost in rows:
        if cost is None:
            continue
        if build.lead_conversation_id and conversation_id == build.lead_conversation_id:
            micros["lead"] += cost
        elif agent in reviewers and agent not in builders:
            micros["review"] += cost
        else:
            micros["build"] += cost

    return {
        "id": build.id,
        "runs": int(runs or 0),
        "time": await _time(session, build, now),
        "cost": {role: round(value / MICROS, 2) for role, value in micros.items()},
    }


async def running_progress(session: AsyncSession, project_id: str) -> Dict[str, Dict[str, Any]]:
    """For each document with a running build: `{id, done, total}`, the tasks of that build that are
    approved of those it covers. Keyed by document id; a document with none has no entry."""
    running = (
        (
            await session.execute(
                select(Build).where(Build.project_id == project_id, Build.state == "running")
            )
        )
        .scalars()
        .all()
    )
    progress: Dict[str, Dict[str, Any]] = {}
    for build in running:
        counts = dict(
            (
                await session.execute(
                    select(Task.status, func.count(Task.id))
                    .where(Task.build_id == build.id)
                    .group_by(Task.status)
                )
            ).all()
        )
        progress[build.document_id] = {
            "id": build.id,
            "done": int(counts.get("approved", 0)),
            "total": int(sum(counts.values())),
        }
    return progress
