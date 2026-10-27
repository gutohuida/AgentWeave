"""A build: how an approved document is built, by whom, within what
(`a-build-has-a-driver-a-level-and-its-people`, slice D of "Flows that do not stall").

The operator chooses, when they press Build, a **driver** that hands out the work (the Hub's flow,
a lead agent, or nobody: by hand), a **level** (Fast: the builder or the lead approves; Reviewed:
anyone but the builder; Gated: as today, evidence accepted per requirement), the **builders** the
work may go to, a **reviewer pool**, a **lead**, a **budget cap**, a **window** and where the work
**lands**. This module owns that record and the level policy (design D1). It decides no move:
`task_transition_service.decide_move` stays the one decision and reads the level from here, and
`requirement_gate` keeps the evidence decision, reading the level's rule (`rigor_for_level`) where
it reads a document's rigor for a task outside any build.

A task outside any build (`build_id` null) records no level and is governed exactly as before, so
nothing built before this change, and no task created by hand, behaves differently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_rigor
from .db.models import AIJob, Build, InboundQueueEntry, Loop, Run, Task, TurnUsage
from .task_transitions import CLAIMABLE_STATUSES, TERMINAL_STATUSES
from .utils import short_id

logger = logging.getLogger(__name__)

# --- the choices ---------------------------------------------------------------------------------

DRIVER_FLOW = "flow"
DRIVER_LEAD = "lead"
DRIVER_HAND = "hand"
DRIVERS: Tuple[str, ...] = (DRIVER_FLOW, DRIVER_LEAD, DRIVER_HAND)

FAST = "fast"
REVIEWED = "reviewed"
GATED = "gated"
LEVELS: Tuple[str, ...] = (FAST, REVIEWED, GATED)

LANDING_MAIN = "main"
LANDING_NOWHERE = "nowhere"
LANDINGS: Tuple[str, ...] = (LANDING_MAIN, LANDING_NOWHERE)

RUNNING = "running"
STOPPED = "stopped"
FINISHED = "finished"

#: The integration record's reason for a task of a build that lands nowhere (`landing`).
LANDS_NOWHERE = "the build lands nowhere, so its approved work is not merged into any branch"

#: The evidence rule each level implies (design D1): Fast as `sketch` (silent), Reviewed as
#: `contract` (reported, never refused), Gated as `gate` (refused until accepted).
_RIGOR = {FAST: spec_rigor.SKETCH, REVIEWED: spec_rigor.CONTRACT, GATED: spec_rigor.GATE}
#: A build that names no level is built at the level nearest its document's rigor.
_LEVEL_FOR_RIGOR = {
    spec_rigor.SKETCH: REVIEWED,
    spec_rigor.CONTRACT: REVIEWED,
    spec_rigor.GATE: GATED,
}

MICROS = 1_000_000


def now() -> datetime:
    """The clock a build's window is judged against (a seam: tests freeze it)."""
    return datetime.now(timezone.utc)


def rigor_for_level(level: Optional[str]) -> Optional[str]:
    """The evidence rule *level* implies, or None for a task outside any build."""
    return _RIGOR.get(level or "")


def level_for_rigor(rigor: Optional[str]) -> str:
    return _LEVEL_FOR_RIGOR.get(rigor or spec_rigor.SKETCH, REVIEWED)


def allows_automatic_override(level: Optional[str]) -> bool:
    """Whether slice M's automatic check override may land work at *level* (design D5).

    True at Fast and Reviewed (still subject to M's project setting), never at Gated: the operator
    picks Gated to judge every landing, so a Hub judgement that a failure is not the task's does
    not land it there. A task outside any build (None) is not held back by a level.
    """
    return level != GATED


def usd(micros: Optional[int]) -> Optional[float]:
    return None if micros is None else round(micros / MICROS, 6)


def micros_of(dollars: Optional[float]) -> Optional[int]:
    return None if dollars is None else int(round(float(dollars) * MICROS))


# --- reads ---------------------------------------------------------------------------------------


async def running_build(session: AsyncSession, document_id: str) -> Optional[Build]:
    return (
        (
            await session.execute(
                select(Build).where(Build.document_id == document_id, Build.state == RUNNING)
            )
        )
        .scalars()
        .first()
    )


async def builds_of(session: AsyncSession, document_id: str) -> List[Build]:
    """Every build of a document, newest first."""
    return list(
        (
            await session.execute(
                select(Build)
                .where(Build.document_id == document_id)
                .order_by(Build.created_at.desc(), Build.id.desc())
            )
        )
        .scalars()
        .all()
    )


async def build_of_loop(session: AsyncSession, loop_id: Optional[str]) -> Optional[Build]:
    if not loop_id:
        return None
    return (await session.execute(select(Build).where(Build.loop_id == loop_id))).scalars().first()


async def build_of_task(session: AsyncSession, task: Task) -> Optional[Build]:
    if not task.build_id:
        return None
    return await session.get(Build, task.build_id)


async def spend(session: AsyncSession, build: Build) -> Tuple[int, int]:
    """`(micros, unpriced)`: the API-equivalent cost of the build's runs, and how many of its turns
    carry no figure (counted as zero, design D7). Runs bound to the build's tasks, and runs in the
    lead's build conversation."""
    task_ids = select(Task.id).where(Task.build_id == build.id)
    bound = Run.task_id.in_(task_ids)
    where = bound
    if build.lead_conversation_id:
        where = bound | (Run.conversation_id == build.lead_conversation_id)
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(TurnUsage.api_equivalent_usd_micros), 0),
                func.count(TurnUsage.id) - func.count(TurnUsage.api_equivalent_usd_micros),
            )
            .select_from(TurnUsage)
            .join(Run, Run.id == TurnUsage.run_id)
            .where(Run.project_id == build.project_id, where)
        )
    ).one()
    return int(row[0] or 0), int(row[1] or 0)


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


async def view(session: AsyncSession, build: Build) -> Dict[str, Any]:
    """The build as the document read and the app show it."""
    spent, unpriced = await spend(session, build)
    return {
        "id": build.id,
        "state": build.state,
        "driver": build.driver,
        "level": build.level,
        "builders": list(build.builders or []),
        "reviewers": list(build.reviewers or []),
        "lead": build.lead,
        "budget_cap_usd": usd(build.budget_cap_usd_micros),
        "spent_usd": usd(spent),
        "unpriced_turns": unpriced,
        "window_start": _iso(build.window_start),
        "window_end": _iso(build.window_end),
        "landing": build.landing,
        "loop_id": build.loop_id,
        "stop_reason": build.stop_reason,
        "created_at": _iso(build.created_at),
        "stopped_at": _iso(build.stopped_at),
    }


# --- starting ------------------------------------------------------------------------------------


@dataclass
class Settings:
    """What the operator chose, resolved against the recommendation (`spec.py`'s Build route)."""

    driver: str
    level: str
    builders: List[str]
    reviewers: List[str]
    lead: Optional[str]
    budget_cap_usd_micros: Optional[int]
    window_start: Optional[datetime]
    window_end: Optional[datetime]
    landing: str
    task_builders: Dict[str, str]


def new_build(project_id: str, document_id: str, settings: Settings) -> Build:
    return Build(
        id=f"build-{short_id()}",
        project_id=project_id,
        document_id=document_id,
        state=RUNNING,
        driver=settings.driver,
        level=settings.level,
        builders=list(settings.builders),
        reviewers=list(settings.reviewers),
        lead=settings.lead,
        budget_cap_usd_micros=settings.budget_cap_usd_micros,
        window_start=settings.window_start,
        window_end=settings.window_end,
        landing=settings.landing,
        created_at=datetime.now(timezone.utc),
    )


async def open_agents(session: AsyncSession, project_id: str) -> set:
    from .db.models import Agent

    return set(
        (
            await session.execute(
                select(Agent.name).where(
                    Agent.project_id == project_id, Agent.lifecycle != "archived"
                )
            )
        )
        .scalars()
        .all()
    )


async def cover_tasks(
    session: AsyncSession,
    build: Build,
    tasks: Iterable[Task],
    declared: Dict[str, Optional[str]],
    chosen: Dict[str, str],
) -> List[Dict[str, str]]:
    """Mark *tasks* as the build's, at its level, and apply each one's builder (FR-2, FR-3).

    *declared* is each task key's builder in the document; *chosen* the operator's choice in the
    Build dialog, which wins (an empty string clears it). A builder that is an open agent becomes
    the assignee of a task nobody holds yet; one that is not is kept on the task and returned as
    unresolved, and the task is left for the driver to hand out. Approval assigns nobody (slice C:
    approval is a plan), so this is the first place a builder is applied.
    """
    agents = await open_agents(session, build.project_id)
    unresolved: List[Dict[str, str]] = []
    for task in tasks:
        task.build_id = build.id
        task.level = build.level
        key = task.spec_task_key or ""
        builder = chosen[key] if key in chosen else declared.get(key)
        builder = (builder or "").strip() or None
        task.builder = builder
        if builder is None:
            continue
        if builder not in agents:
            unresolved.append({"task": key, "builder": builder})
            continue
        if task.assignee is None and task.status in ("pending", "assigned"):
            task.assignee = builder
    return unresolved


async def join_running_build(session: AsyncSession, task: Task) -> None:
    """A task a document declares while a build of it runs joins that build (FR-2): re-approving a
    reopened document whose build still runs, or the operator accepting an amendment that adds a
    task (`spec_amendments.accept_proposal`), adds it to that build's flow (`spec_tasks`), and so to
    the build, at its level, with its declared builder applied as `cover_tasks` applies one."""
    if task.build_id or not task.spec_document_id:
        return
    build = await running_build(session, task.spec_document_id)
    if build is None:
        return
    task.build_id = build.id
    task.level = build.level
    if (
        task.builder
        and task.assignee is None
        and task.status in ("pending", "assigned")
        and task.builder in await open_agents(session, build.project_id)
    ):
        task.assignee = task.builder


async def retire_previous_loops(session: AsyncSession, document_id: str, by_build: str) -> None:
    """Free the document for a new build's loop: a loop an earlier, no longer running build owned
    is ended (if it was not) and archived. A loop no build owns is left as it is."""
    from .loop_ending import end_loop

    now = datetime.now(timezone.utc)
    previous = (
        (
            await session.execute(
                select(Build).where(
                    Build.document_id == document_id,
                    Build.state != RUNNING,
                    Build.loop_id.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for build in previous:
        loop = await session.get(Loop, build.loop_id)
        if loop is None or loop.archived_at is not None:
            continue
        job = await session.get(AIJob, loop.job_id)
        if job is not None:
            end_loop(job, loop, reason=f"replaced by build {by_build}", when=now, completed=False)
        loop.archived_at = now


# --- who may move what (inputs to `decide_move`) -------------------------------------------------


async def builder_of(session: AsyncSession, task: Task) -> Optional[str]:
    """The agent that built *task*: the one recorded as completing it, else its assignee."""
    from .task_transition_service import agent_that_completed

    return await agent_that_completed(session, task.id) or task.assignee


async def fast_approval_refusal(session: AsyncSession, task: Task, actor) -> Optional[str]:
    """Why *actor* may not take *task* from `completed` straight to `approved`, or None when it may.

    The edge exists only at Fast (design D4), and only for the task's builder, its build's lead and
    the operator. A task at another level, or outside any build, is refused naming that, so the
    refusal tells an agent where approval goes instead.
    """
    level = task.level if task.build_id else None
    if level != FAST:
        where = f"at level {level}" if level else "outside any build"
        return (
            f"Cannot move task {task.id} from 'completed' to 'approved': it is built {where}, "
            "where completed work is approved only after review. Take it into review "
            "(under_review) first; only a Fast build's builder or lead approves from completed."
        )
    if actor.is_operator:
        return None
    builder = await builder_of(session, task)
    build = await build_of_task(session, task)
    lead = build.lead if build is not None else None
    if actor.agent and actor.agent in {builder, lead}:
        return None
    return (
        f"Cannot move task {task.id} from 'completed' to 'approved': at Fast only its builder "
        f"({builder or 'nobody recorded'}), its build's lead ({lead or 'none'}) or the operator "
        "approves it from completed. Any other agent reviews it: take it into review first."
    )


# --- budget and window (FR-10) -------------------------------------------------------------------


@dataclass(frozen=True)
class HandOut:
    """May a flow or lead firing hand out a new turn now?"""

    allowed: bool
    #: Set when the build must stop (cap reached, window closed): the reason it records.
    stop_reason: Optional[str] = None
    #: Set when it must only wait (the window has not opened yet).
    wait_reason: Optional[str] = None


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def may_hand_out(
    session: AsyncSession, build: Build, at: Optional[datetime] = None
) -> HandOut:
    """Asked first by every flow and lead firing (design D7). Turns already running are never
    touched; this only says whether a new one may be handed out."""
    at = at or now()
    start, end = _aware(build.window_start), _aware(build.window_end)
    if start is not None and at < start:
        return HandOut(
            allowed=False, wait_reason=f"the build's window opens at {start.isoformat()}"
        )
    if end is not None and at >= end:
        return HandOut(
            allowed=False,
            stop_reason=f"the build's window closed at {end.isoformat()}; extend it to resume",
        )
    if build.budget_cap_usd_micros is not None:
        spent, unpriced = await spend(session, build)
        if spent >= build.budget_cap_usd_micros:
            unpriced_note = f" ({unpriced} unpriced turns counted as $0)" if unpriced else ""
            return HandOut(
                allowed=False,
                stop_reason=(
                    f"the build has spent ${spent / MICROS:.2f} of its ${usd(build.budget_cap_usd_micros):.2f} "
                    f"cap{unpriced_note}; raise the cap to resume"
                ),
            )
    return HandOut(allowed=True)


#: The reason an operator's own Stop records: raising the cap or moving the window does not resume
#: a build the operator stopped.
STOPPED_BY_OPERATOR = "stopped by the operator"


async def stop(session: AsyncSession, build: Build, reason: str) -> Optional[AIJob]:
    """Stop *build*: no new turn is handed out, running ones finish. Its loop's job is paused (not
    ended), so raising the cap or extending the window resumes it. Returns the paused job, which
    the caller takes out of the live scheduler after its commit."""
    build.state = STOPPED
    build.stop_reason = reason
    build.stopped_at = now()
    if not build.loop_id:
        return None
    loop = await session.get(Loop, build.loop_id)
    if loop is None or loop.ending_state is not None:
        return None
    job = await session.get(AIJob, loop.job_id)
    if job is None:
        return None
    job.enabled = False
    loop.stop_reason = f"build {build.id} stopped: {reason}"
    return job


async def resume(session: AsyncSession, build: Build) -> Optional[AIJob]:
    """Run a stopped build again (Raise cap, a later window): its loop's job is re-enabled.
    Returns that job, which the caller hands back to the scheduler after its commit."""
    build.state = RUNNING
    build.stop_reason = None
    build.stopped_at = None
    if not build.loop_id:
        return None
    loop = await session.get(Loop, build.loop_id)
    if loop is None or loop.ending_state is not None or loop.archived_at is not None:
        return None
    job = await session.get(AIJob, loop.job_id)
    if job is None or job.archived_at is not None:
        return None
    job.enabled = True
    loop.stop_reason = None
    return job


async def notify_stopped(session: AsyncSession, build: Build, reason: str) -> None:
    """Tell the operator a build stopped (not a stall: nothing is wrong with the work)."""
    from .sse import sse_manager
    from .utils import persist_event

    payload = {"build_id": build.id, "document_id": build.document_id, "reason": reason}
    try:
        await persist_event(
            session, build.project_id, "build_stopped", payload, agent=None, severity="warn"
        )
        await sse_manager.broadcast(build.project_id, "build_stopped", payload)
    except Exception:  # noqa: BLE001 -- the stop stands whether or not it was announced
        logger.warning("could not announce that build %s stopped", build.id, exc_info=True)


async def finish_if_done(session: AsyncSession, task: Task) -> None:
    """A build whose every task is approved or rejected has finished."""
    if not task.build_id:
        return
    build = await session.get(Build, task.build_id)
    if build is None or build.state != RUNNING:
        return
    open_count = (
        await session.execute(
            select(func.count())
            .select_from(Task)
            .where(
                Task.build_id == build.id,
                Task.id != task.id,
                Task.status.not_in(tuple(TERMINAL_STATUSES)),
            )
        )
    ).scalar_one()
    if open_count == 0:
        build.state = FINISHED
        build.stopped_at = datetime.now(timezone.utc)
        await end_loop_of(session, build)


async def end_loop_of(session: AsyncSession, build: Build) -> Optional[AIJob]:
    """End a finished build's loop as a drained queue ends one: `completed`, its job disabled.
    Without this the build's firing (which runs before the loop's own stop check) would tick a
    finished build's loop forever. Returns the job, for the live scheduler to drop; a loop that
    has already ended is left as it is."""
    from .loop_ending import QUEUE_DRAINED_REASON, end_loop

    if not build.loop_id:
        return None
    loop = await session.get(Loop, build.loop_id)
    if loop is None:
        return None
    job = await session.get(AIJob, loop.job_id)
    if job is None:
        return None
    end_loop(job, loop, reason=QUEUE_DRAINED_REASON, when=now(), completed=True)
    return job


# --- the lead (FR-5) -----------------------------------------------------------------------------


async def unread_brief(session: AsyncSession, build: Build) -> bool:
    """Whether the lead's previous brief is still waiting to be read."""
    if not build.lead_conversation_id:
        return False
    found = (
        await session.execute(
            select(InboundQueueEntry.id).where(
                InboundQueueEntry.conversation_id == build.lead_conversation_id,
                InboundQueueEntry.state == "queued",
            )
        )
    ).first()
    return found is not None


async def compose_brief(session: AsyncSession, build: Build, title: str) -> str:
    """What the lead is told: the open tasks and who holds them, the free builders, the level, the
    spend and the window."""
    from .scheduler import _agents_that_are_free

    tasks = (
        (
            await session.execute(
                select(Task).where(Task.build_id == build.id).order_by(Task.created_at, Task.id)
            )
        )
        .scalars()
        .all()
    )
    free = set(await _agents_that_are_free(session, build.project_id))
    builders = list(build.builders or [])
    reviewers = list(build.reviewers or [])
    spent, unpriced = await spend(session, build)
    cap = usd(build.budget_cap_usd_micros)
    lines = [
        f'You lead the build {build.id} of "{title}", at level {build.level}.',
        "Hand each task to a builder, and each completed task to a reviewer, with "
        "hand_out_task(task_id, agent, review). You approve only under the level's rules.",
        "",
        "Open tasks:",
    ]
    open_tasks = [t for t in tasks if t.status not in TERMINAL_STATUSES]
    for task in open_tasks:
        holder = task.assignee or "nobody"
        declared = f", declared builder {task.builder}" if task.builder else ""
        lines.append(f"- {task.id} [{task.status}] {task.title} (held by {holder}{declared})")
    if not open_tasks:
        lines.append("- none")
    pool = builders or sorted(free)
    lines += [
        "",
        f"Builders: {', '.join(builders) or 'any agent'}; free now: "
        f"{', '.join(name for name in pool if name in free) or 'none'}.",
        f"Reviewers: {', '.join(reviewers) or 'any agent but the builder'}.",
        f"Spend: ${spent / MICROS:.2f}"
        + (f" of ${cap:.2f}" if cap is not None else " (no cap)")
        + (f", {unpriced} unpriced turns" if unpriced else "")
        + ".",
        f"Window: {_iso(build.window_start) or 'now'} to {_iso(build.window_end) or 'open-ended'}.",
    ]
    return "\n".join(lines)


async def queue_brief(
    session: AsyncSession, build: Build, title: str, job_id: str
) -> Optional[str]:
    """Queue one brief to the lead's build conversation, unless the previous one is unread.
    Returns the entry id, or None when nothing was queued. The caller commits and then schedules
    the lead (`turn_scheduler.schedule_accepted`)."""
    from .conversations import name_conversation, new_conversation
    from .db.models import Conversation
    from .inbound_queue import new_entry

    if not build.lead or await unread_brief(session, build):
        return None
    conversation = None
    if build.lead_conversation_id:
        conversation = await session.get(Conversation, build.lead_conversation_id)
        if conversation is not None and conversation.lifecycle != "open":
            conversation = None
    if conversation is None:
        conversation = new_conversation(project_id=build.project_id, agent=build.lead, origin="job")
        name_conversation(conversation, f"Lead: {title}")
        session.add(conversation)
        await session.flush()
        build.lead_conversation_id = conversation.id
    entry = new_entry(
        project_id=build.project_id,
        agent=build.lead,
        origin_type="job",
        content=await compose_brief(session, build, title),
        hop_depth=0,
        job_id=job_id,
        conversation_id=conversation.id,
    )
    session.add(entry)
    return entry.id


class HandOutRefused(Exception):  # noqa: N818 -- "refused" is the outcome, not a fault
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


async def hand_out(
    session: AsyncSession, *, caller: str, project_id: str, task_id: str, agent: str, review: bool
) -> Tuple[Task, Build, str]:
    """The lead hands *task_id* to *agent*: to build it, or (*review*) to review it (FR-5, D6).

    Answered only for the lead of the task's running build (403 otherwise), and only for an agent
    in the build's pools (an empty pool means any open agent). Assigns the builder, and queues the
    chosen agent's turn bound to the task the way the operator's trigger does (`task_id` /
    `review_task_id`). Returns the task, its build and the queued entry's id; the caller commits
    and schedules the agent. Raises `HandOutRefused`.
    """
    from .api.v1.agent_trigger import review_dispatch_refusal
    from .conversations import inherit_runtime_overrides, name_conversation, new_conversation
    from .inbound_queue import new_entry

    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise HandOutRefused(f"There is no task {task_id!r} in this project.", 404)
    build = await build_of_task(session, task)
    if build is None or build.state != RUNNING or build.driver != DRIVER_LEAD:
        raise HandOutRefused(
            f"Task {task_id} is not in a running lead-driven build, so nobody hands it out.", 403
        )
    if caller != build.lead:
        raise HandOutRefused(
            f"Only the lead of build {build.id} ({build.lead}) hands out its tasks; "
            f"{caller} is not its lead.",
            403,
        )
    pool = list(build.reviewers if review else build.builders) or None
    if pool is not None and agent not in pool:
        which = "reviewer pool" if review else "builders"
        raise HandOutRefused(
            f"{agent} is not among build {build.id}'s {which} ({', '.join(pool)}).", 409
        )
    if agent not in await open_agents(session, project_id):
        raise HandOutRefused(f"{agent} is not an open agent of this project.", 409)
    if review:
        # The dispatch's own read-only refusals, the checks wait and the commit to review, asked
        # now so the lead is answered instead of a turn that never starts (as the mender's
        # hand-off does, `mender._hand_to_review`).
        from . import project_checks
        from .task_integration import review_target

        refusal = await review_dispatch_refusal(session, task, reviewer=agent)
        if refusal is not None:
            raise HandOutRefused(str(refusal[1]), refusal[0])
        wait = await project_checks.review_wait(session, task)
        if wait is not None:
            if wait.needs_a_run:
                project_checks.schedule(task.project_id, task.id)
            raise HandOutRefused(
                f"{task.id} cannot be handed to a reviewer yet: {wait.reason}.", 409
            )
        target = await review_target(session, task)
        if not target.resolved:
            raise HandOutRefused(str(target.refusal), 409)
    else:
        if task.status not in CLAIMABLE_STATUSES:
            raise HandOutRefused(
                f"Task {task_id} is {task.status}; only work not yet finished is handed to a "
                "builder. Hand a completed task out for review instead.",
                409,
            )
        if task.status == "in_progress" and task.assignee and task.assignee != agent:
            raise HandOutRefused(
                f"Task {task_id} is in progress with {task.assignee}; it is not handed to another "
                "agent mid-work.",
                409,
            )
        if task.status in ("pending", "assigned"):
            from .dependency_gate import evaluate as evaluate_dependencies

            gate = await evaluate_dependencies(session, task)
            if gate.refuses:
                raise HandOutRefused(
                    f"Task {task_id} waits for its prerequisites: {gate.to_dict()}", 409
                )
        task.assignee = agent
    loop = await session.get(Loop, build.loop_id) if build.loop_id else None
    conversation = new_conversation(project_id=project_id, agent=agent, origin="job")
    kind = "Review" if review else "Build"
    name_conversation(conversation, f"{kind}: {task.title}"[:120])
    session.add(conversation)
    await inherit_runtime_overrides(session, conversation)
    await session.flush()
    content = f"The lead ({caller}) hands you task {task.id}, {task.title!r}, to " + (
        "review: judge the finished work and move it on." if review else "build."
    )
    entry = new_entry(
        project_id=project_id,
        agent=agent,
        origin_type="job",
        content=content,
        hop_depth=0,
        job_id=(loop.job_id if loop is not None else None),
        conversation_id=conversation.id,
        task_id=None if review else task.id,
        review_task_id=task.id if review else None,
    )
    session.add(entry)
    return task, build, entry.id


def lead_pools(build: Build) -> Tuple[Sequence[str], Sequence[str]]:
    return list(build.builders or []), list(build.reviewers or [])
