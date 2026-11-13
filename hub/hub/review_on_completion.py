"""Finished work outside a build finds its reviewer (`a-hand-started-task-reaches-review-and-merge`,
FR-2, FR-3).

A build's flow staffs a reviewer for its completed tasks (`scheduler.resolve_reviewer`). A task the
operator started by hand from the board has no build behind it, so nothing routed it to review: the
quickstart's task sat `completed` until the operator found "Land it" (driven 2026-11-13). This is
that missing step, run where a task's checks decide (`project_checks._after_decided`) and where the
turn that completed it ends (`project_checks._after_run`, which covers a project with no checks):

    the task's own checker, if one is named        -> its review starts ("declared")
    a checker named that may not or cannot review  -> surfaced, nobody substituted
    nobody named                                   -> the build's ladder picks (rung 2), and the
                                                      story says the Hub picked them ("picked")
    nobody can be picked                           -> surfaced on the task (`review_unstaffed`)

The review itself is the mender's hand-off (`mender.hand_to_review`): a queued review turn whose
dispatch stages `completed -> under_review` with the reviewer as holder. Never raises.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.engine import async_session_factory
from .db.models import AIJob, EventLog, InboundQueueEntry, Loop, Run, Task

logger = logging.getLogger(__name__)

#: The story's record of who the Hub put on a review it staffed outside a build (FR-3).
REVIEW_STAFFED = "review_staffed"
#: The same event the flow writes when it cannot staff a review; the story and the stage read it.
REVIEW_UNSTAFFED = "review_unstaffed"

#: One staffing at a time per task: a check run deciding and the completing turn ending can ask in
#: the same moment, and both would otherwise queue a review.
_locks: Dict[str, asyncio.Lock] = {}


async def staff_review(
    project_id: str, task_id: str, *, ending_run_id: Optional[str] = None
) -> Optional[str]:
    """Start the review of *task_id* if it is finished work no build will review; the reviewer's
    name, or `None` where none was started (not this path's task, not yet, or nobody can).

    *ending_run_id* is the run whose end asked, which is not a turn still at work on the task."""
    lock = _locks.setdefault(task_id, asyncio.Lock())
    try:
        async with lock, async_session_factory() as session:
            return await _staff(session, project_id, task_id, ending_run_id)
    except Exception:  # noqa: BLE001 -- the board and the operator's own controls still work
        logger.warning("could not staff the review of %s", task_id, exc_info=True)
        return None


async def _staff(
    session: AsyncSession, project_id: str, task_id: str, ending_run_id: Optional[str]
) -> Optional[str]:
    from . import project_checks

    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id or task.status != "completed":
        return None
    if await _a_build_or_loop_reviews_it(session, task):
        return None
    if await _still_at_work(session, task, ending_run_id) or await _review_queued(session, task):
        return None
    wait = await project_checks.review_wait(session, task)
    if wait is not None:
        # Its checks have not passed yet; their decision asks again (`_after_decided`).
        if wait.needs_a_run:
            project_checks.schedule(task.project_id, task.id)
        return None

    agent, declared, reason = await _choose(session, task)
    if agent is None:
        await _surface(session, task, reason or "no agent could be found to review it.")
        return None
    return await _hand_over(session, task, agent, declared=declared)


async def _a_build_or_loop_reviews_it(session: AsyncSession, task: Task) -> bool:
    """A running build, or a live loop, owns this task's review; this path leaves it to them."""
    from . import builds

    build = await builds.build_of_task(session, task)
    if build is not None and build.state == builds.RUNNING:
        return True
    if task.loop_id:
        loop = await session.get(Loop, task.loop_id)
        if loop is not None and loop.stopped_at is None:
            job = await session.get(AIJob, loop.job_id)
            if job is not None and job.enabled:
                return True
    return False


async def _still_at_work(session: AsyncSession, task: Task, ending_run_id: Optional[str]) -> bool:
    """A turn bound to the task is still running: its work is not committed until it ends, and
    its end asks again (`project_checks.after_run`)."""
    query = select(Run.id).where(
        Run.project_id == task.project_id, Run.task_id == task.id, Run.status == "running"
    )
    if ending_run_id:
        query = query.where(Run.id != ending_run_id)
    return (await session.execute(query.limit(1))).first() is not None


async def _review_queued(session: AsyncSession, task: Task) -> bool:
    found = await session.execute(
        select(InboundQueueEntry.id)
        .where(
            InboundQueueEntry.project_id == task.project_id,
            InboundQueueEntry.review_task_id == task.id,
            InboundQueueEntry.state == "queued",
        )
        .limit(1)
    )
    return found.first() is not None


async def _exclusions(session: AsyncSession, task: Task) -> Dict[str, str]:
    """Who may not review it, and why: the flow's own derivation (`scheduler`'s staffing arm)."""
    from .task_transition_service import (
        agents_that_may_have_authored,
        agents_that_recorded_evidence_for,
        completion_attribution,
    )

    attribution = await completion_attribution(session, task.id)
    if attribution.agent is None:
        return dict.fromkeys(
            await agents_that_may_have_authored(session, task), "has worked on this task"
        )
    exclude = {attribution.agent: "is the one that completed this task"}
    for author in await agents_that_recorded_evidence_for(session, task.id):
        exclude.setdefault(author, "recorded evidence for this task")
    return exclude


async def _choose(session: AsyncSession, task: Task) -> "tuple[Optional[str], bool, Optional[str]]":
    """`(agent, declared, reason)`: the reviewer and whether somebody named them, or why nobody.

    The task's own `checker` is its declaration here: with no build there is no build's choice to
    read (`scheduler.build_checker_resolution`), and the column exists so a task waiting with no
    build keeps the checker it was filed with. Named and unable to review is surfaced, never
    replaced, as the ladder's rung 1b; named nobody, the ladder runs as a build's would.
    """
    from . import builds
    from .scheduler import resolve_reviewer

    exclude = await _exclusions(session, task)
    checker = (task.checker or "").strip()
    if checker:
        if checker in exclude:
            return (
                None,
                True,
                f"this task names {checker!r} as its checker, and that agent {exclude[checker]}. "
                f"Naming a different checker, or reviewing it yourself, is the way forward -- "
                f"nobody is substituted for a named checker.",
            )
        if checker not in await builds.open_agents(session, task.project_id):
            return None, True, builds.not_open_reason(task, "checker", checker)
        return checker, True, None
    choice = await resolve_reviewer(session, task, project_id=task.project_id, exclude=exclude)
    if choice.agent is None and choice.rung == "unstaffed":
        others = await _agents_but_the_mender(session, task.project_id) - set(exclude)
        if not others:
            # Rung 3's "no reviewer is free" reads as a wait; with nobody but the author on the
            # roster no wait ends it, and the operator is told the fact (ac-auto-none).
            from .scheduler import own_review_remedy

            authors = ", ".join(f"{name} {why}" for name, why in sorted(exclude.items()))
            return (
                None,
                False,
                "there is no agent other than the author to review this"
                + (f" ({authors})" if authors else "")
                + f". Add an agent to review it. {own_review_remedy(task)}",
            )
    return choice.agent, choice.rung == "declared", choice.reason


async def _agents_but_the_mender(session: AsyncSession, project_id: str) -> "set[str]":
    from . import builds
    from .db.models import Agent
    from .stalls import HUB_ROLE

    names = await builds.open_agents(session, project_id)
    hub_agents = (
        await session.execute(
            select(Agent.name, Agent.config).where(Agent.project_id == project_id)
        )
    ).all()
    return names - {
        name for name, config in hub_agents if (config or {}).get("hub_role") == HUB_ROLE
    }


async def _surface(session: AsyncSession, task: Task, reason: str) -> None:
    """Record why nobody reviews it, once per reason: the story and the board's stage read it."""
    from .sse import sse_manager
    from .utils import persist_event

    latest = (
        (
            await session.execute(
                select(EventLog)
                .where(
                    EventLog.project_id == task.project_id,
                    EventLog.event_type == REVIEW_UNSTAFFED,
                    EventLog.data["task_id"].as_string() == task.id,
                )
                .order_by(EventLog.timestamp.desc(), EventLog.id.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if latest is not None and (latest.data or {}).get("reason") == reason:
        return
    payload = {"task_id": task.id, "task_title": task.title, "reason": reason}
    await persist_event(session, task.project_id, REVIEW_UNSTAFFED, payload, severity="warning")
    await sse_manager.broadcast(task.project_id, REVIEW_UNSTAFFED, payload)


def staffed_sentence(display_id: str, reviewer: str, *, declared: bool) -> str:
    if declared:
        return f"{reviewer} reviews {display_id}, as the checker named for it."
    return (
        f"Nobody was declared to check {display_id}, so the Hub picked {reviewer} to review it: "
        f"an open agent other than its author, chosen as a build would choose one."
    )


async def _hand_over(
    session: AsyncSession, task: Task, reviewer: str, *, declared: bool
) -> Optional[str]:
    from fastapi import HTTPException

    from .api.v1.mender import hand_to_review
    from .utils import persist_event

    await persist_event(
        session,
        task.project_id,
        REVIEW_STAFFED,
        {
            "task_id": task.id,
            "reviewer": reviewer,
            "declared": declared,
            "reason": staffed_sentence(task.display_id, reviewer, declared=declared),
        },
        agent=reviewer,
        commit=False,
    )
    try:
        # Commits the event with the queued review, and schedules the reviewer.
        await hand_to_review(session, task, reviewer, origin="job")
    except HTTPException as exc:
        await session.rollback()
        task = await session.get(Task, task.id)
        if task is not None:
            await _surface(session, task, f"{reviewer} could not be given its review: {exc.detail}")
        return None
    return reviewer


async def _waiting_for_a_reviewer(session: AsyncSession, project_id: str) -> "list[str]":
    """Completed tasks this path once could not staff (`review_unstaffed`), oldest first.

    Rung 3 surfaces "no reviewer is free" while every other agent is mid-turn. In a build the
    flow's next tick asks again; out of one nothing would, so any run's end -- an agent going
    idle -- asks again for these. `staff_review` leaves a build's or a loop's tasks to them, and
    `_surface` writes a reason only once, so asking a task nobody can yet review costs nothing."""
    unstaffed = (
        select(EventLog.data["task_id"].as_string())
        .where(EventLog.project_id == project_id, EventLog.event_type == REVIEW_UNSTAFFED)
        .scalar_subquery()
    )
    rows = await session.execute(
        select(Task.id)
        .where(Task.project_id == project_id, Task.status == "completed", Task.id.in_(unstaffed))
        .order_by(Task.updated.asc(), Task.id.asc())
    )
    return [task_id for (task_id,) in rows.all()]


async def _after_run(project_id: str, run_id: str) -> None:
    try:
        async with async_session_factory() as session:
            run = await session.get(Run, run_id)
            task_id = run.task_id if run is not None else None
            waiting = await _waiting_for_a_reviewer(session, project_id)
    except Exception:  # noqa: BLE001
        logger.warning("could not read run %s to staff its task's review", run_id, exc_info=True)
        return
    if task_id:
        await staff_review(project_id, task_id, ending_run_id=run_id)
    for other in waiting:
        if other != task_id:
            await staff_review(project_id, other, ending_run_id=run_id)


_pending: "set[asyncio.Task[None]]" = set()


def after_run(project_id: str, run_id: str) -> None:
    """At a run's end, after its snapshot commit: review the completed task it was bound to, and
    ask again for completed tasks that found no reviewer free -- the run's agent is free now.

    A project with no checks has nothing to decide, so this is where its finished work finds a
    reviewer; with checks it finds them waiting, and their decision asks again. Never raises.
    """
    try:
        job = asyncio.get_running_loop().create_task(_after_run(project_id, run_id))
    except Exception:  # noqa: BLE001
        logger.warning("could not schedule review staffing after run %s", run_id, exc_info=True)
        return
    _pending.add(job)
    job.add_done_callback(_pending.discard)


async def drain() -> None:
    """Wait for every scheduled staffing (tests, and shutdown)."""
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)
