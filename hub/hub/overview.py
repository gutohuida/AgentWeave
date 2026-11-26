"""The project's Overview, assembled in one read (`overview-at-a-glance-with-dashboard-and-
briefing-tabs`, design D1).

Both Overview tabs, Dashboard and Briefing, show what this returns, so a figure on one cannot
contradict the same figure on the other, and ranking, main health and 'since' are pinned by Hub
tests rather than computed in the browser. It reads the readers that already exist (questions,
stalls, permission requests, the known-failing list, check and main notices, next-slice offers,
reopening warnings, `builds.project_rows`, the turns' usage, the integration and transition
records) and changes none of them. Nothing here writes: refetching it never moves the visit record.

The visit, the note and its state are read from `overview_note_job` (task `visits-and-note`):
the visit is moved only by `POST /overview/visit`, the note only by the overview-note job.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import builds as builds_module
from .db.models import (
    Conversation,
    KnownFailingTest,
    LandingBatch,
    MainCheckRun,
    MainNotice,
    PermissionRequest,
    Project,
    Question,
    Run,
    Stall,
    Task,
    TaskCheckRun,
    TaskIntegration,
    TaskTransition,
    TurnUsage,
)

logger = logging.getLogger(__name__)

# --- needs: kinds and their rank (algorithm 'needs-rank') ----------------------------------------

MAIN = "main"
MERGE = "merge"
STALL = "stall"
QUESTION = "question"
REVIEW = "review"
PERMISSION = "permission"
CHECK = "check"
OFFER = "offer"
REOPENING = "reopening"
MAIN_MOVED = "main_moved"

RANK = {
    MAIN: 1,
    MERGE: 2,
    STALL: 3,
    QUESTION: 4,
    REVIEW: 5,
    PERMISSION: 5,
    CHECK: 6,
    OFFER: 6,
    REOPENING: 6,
    MAIN_MOVED: 6,
}

# --- main states (algorithm 'main-state') --------------------------------------------------------

GREEN = "green"
FAILING = "failing"
HELD = "held"
UNKNOWN = "unknown"

# --- finished outcomes ---------------------------------------------------------------------------

LANDED = "landed"
SENT_BACK = "sent_back"
FAILED = "failed"
STOPPED = "stopped"

#: Run statuses that ended a turn without finishing it: the operator stopped it, or the Hub did.
_STOPPED_RUNS = ("stopped", "interrupted")
#: Who reviews a task the operator holds: a task under review held by nobody, or by these names.
_OPERATOR_HOLDERS = (None, "", "user", "operator")
#: A stall raised because approved work did not reach main (`task_integration`'s causes).
_INTEGRATION_CAUSE = "integration_"
#: The most finished items the timeline is given.
FINISHED_LIMIT = 200
MAX_DAYS = 31


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _utc(value: datetime) -> datetime:
    """*value* in UTC, for a SQL bound. `UTCDateTime` relabels values on the way out only, and
    SQLite compares the bound's wall-clock digits with the stored UTC ones, so a local-offset
    bound (the client's day start, D6) would be off by its offset."""
    return (_aware(value) or value).astimezone(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    moment = _aware(value)
    return moment.isoformat() if moment is not None else None


def _one_line(text: Optional[str], limit: int = 160) -> str:
    line = " ".join((text or "").split())
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def _target(
    kind: str,
    target_id: Optional[str],
    *,
    conversation_id: Optional[str] = None,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    return {"type": kind, "id": target_id, "conversation_id": conversation_id, "path": path}


def _need(
    need_id: str,
    kind: str,
    *,
    agent: Optional[str],
    title: str,
    waiting_since: Optional[datetime],
    action: str,
    target: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "id": need_id,
        "kind": kind,
        "rank": RANK[kind],
        "agent": agent or None,
        "title": title,
        "waiting_since": _aware(waiting_since),
        "action": action,
        "target": target,
    }


def rank_needs(needs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """By rank, then oldest waiting first; an item with no known start ends its rank."""
    far = datetime.max.replace(tzinfo=timezone.utc)
    return sorted(needs, key=lambda n: (n["rank"], n["waiting_since"] or far, n["id"]))


def parse_day_start(value: Optional[str], now: datetime) -> datetime:
    """The operator's local midnight as the client sent it (ISO with an offset, D6); without one,
    midnight UTC today. A naive time is read as UTC. Raises `ValueError` on anything else."""
    if not value:
        return now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


# --- the read ------------------------------------------------------------------------------------


async def overview(
    session: AsyncSession,
    project_id: str,
    *,
    day_start: datetime,
    days: int = 7,
    workspace: Any = None,
    previous_visit_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Everything both Overview tabs show, per the contract in the design.

    *day_start* is the operator's local midnight today; spend is bucketed into *days* local days
    ending with today. Finished work is listed from the earlier of *day_start* and
    *previous_visit_at* (the visit before the current one), read from the visit record unless the
    caller passes it."""
    from . import overview_note_job

    moment = _aware(now) or datetime.now(timezone.utc)
    day_start = _aware(day_start) or moment
    days = max(1, min(int(days), MAX_DAYS))
    visit = await overview_note_job.visit_view(session, project_id)
    if previous_visit_at is None and visit is not None and visit["previous_at"]:
        previous_visit_at = datetime.fromisoformat(visit["previous_at"])
    previous = _aware(previous_visit_at)
    since = min(day_start, previous) if previous is not None else day_start

    project = await session.get(Project, project_id)
    main = await main_state(session, project_id, branch=project.main_branch if project else None)
    rows = await builds_module.project_rows(session, project_id, workspace)
    needs = await gather_needs(session, project_id, workspace=workspace, main=main)
    out: Dict[str, Any] = {
        "generated_at": moment.isoformat(),
        "visit": visit,
        "needs": [_need_view(n) for n in rank_needs(needs)],
        "running": await running(session, project_id),
        "finished": await finished(session, project_id, since=since),
        "spend": await spend(session, project, day_start=day_start, days=days),
        "main": main,
        "builds": [_build_view(row) for row in rows if row["state"] == builds_module.RUNNING],
        "note": overview_note_job.note_view(
            await overview_note_job.latest_note(session, project_id)
        ),
        "note_writing": overview_note_job.is_writing(project_id),
        "note_last_attempt": await overview_note_job.last_attempt(session, project_id),
    }
    return out


def _need_view(need: Dict[str, Any]) -> Dict[str, Any]:
    return {**need, "waiting_since": _iso(need["waiting_since"])}


def _build_view(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "build_id": row["id"],
        "document_path": row["document_path"],
        "title": row["document_title"],
        "tasks_done": row["tasks_done"],
        "tasks_total": row["tasks_total"],
        "stage_words": row["stage_words"],
        "needs_operator": bool(row["needs_operator"]) or bool(row["open_questions"]),
    }


# --- needs ---------------------------------------------------------------------------------------


async def _entered(session: AsyncSession, tasks: Sequence[Task]) -> Dict[str, datetime]:
    """When each of *tasks* last entered the status it holds now."""
    ids = [t.id for t in tasks]
    if not ids:
        return {}
    status_of = {t.id: t.status for t in tasks}
    found: Dict[str, datetime] = {}
    for task_id, to_status, at in await session.execute(
        select(TaskTransition.task_id, TaskTransition.to_status, TaskTransition.created_at)
        .where(TaskTransition.task_id.in_(ids))
        .order_by(TaskTransition.sequence)
    ):
        if status_of.get(task_id) == to_status:
            found[task_id] = at
    return found


async def gather_needs(
    session: AsyncSession, project_id: str, *, workspace: Any, main: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Every item waiting on the operator in the project, unranked (FR-3)."""
    from . import landing_queue, main_watch, project_checks, slice_drafting

    needs: List[Dict[str, Any]] = []
    tasks: Dict[str, Task] = {}

    async def task_of(task_id: Optional[str]) -> Optional[Task]:
        if not task_id:
            return None
        if task_id not in tasks:
            row = await session.get(Task, task_id)
            if row is None or row.project_id != project_id:
                return None
            tasks[task_id] = row
        return tasks[task_id]

    # Main trouble (rank 1): one item while main is failing or a landing is held.
    if main["state"] in (FAILING, HELD):
        needs.append(
            _need(
                "main",
                MAIN,
                agent=None,
                title=main["detail"],
                waiting_since=main.pop("_since", None),
                action="Open checks",
                target=_target("check", None),
            )
        )
    main.pop("_since", None)

    # Stalls: approved work that did not land is a merge (rank 2), the rest stalls (rank 3).
    merged_tasks: set = set()
    for stall in (
        await session.execute(
            select(Stall)
            .where(Stall.project_id == project_id, Stall.ended_at.is_(None))
            .order_by(Stall.first_seen_at, Stall.id)
        )
    ).scalars():
        task = await task_of(stall.task_id)
        if stall.cause.startswith(_INTEGRATION_CAUSE) and task is not None:
            merged_tasks.add(task.id)
            needs.append(
                _need(
                    f"merge-{task.id}",
                    MERGE,
                    agent=task.builder or task.assignee,
                    title=f"“{task.title}” was approved but did not land",
                    waiting_since=stall.first_seen_at,
                    action="Try again",
                    target=_target("task", task.id),
                )
            )
            continue
        if task is not None:
            target = _target("task", task.id)
        elif stall.conversation_id:
            target = _target("thread", stall.id, conversation_id=stall.conversation_id)
        else:
            target = _target("setting", "stalls")
        needs.append(
            _need(
                f"stall-{stall.id}",
                STALL,
                agent=(task.assignee if task is not None else None),
                title=_one_line(stall.reason) or stall.cause.replace("_", " "),
                waiting_since=stall.first_seen_at,
                action="Open",
                target=target,
            )
        )
    # A landing that ended without landing, with no stall raised for it (rank 2).
    for task_id, (state, _reason) in (
        await landing_queue.unlanded(session, Task.project_id == project_id)
    ).items():
        if state != landing_queue.NOT_LANDED or task_id in merged_tasks:
            continue
        task = await task_of(task_id)
        if task is None:
            continue
        needs.append(
            _need(
                f"merge-{task.id}",
                MERGE,
                agent=task.builder or task.assignee,
                title=f"“{task.title}” was approved but did not land",
                waiting_since=task.updated,
                action="Try again",
                target=_target("task", task.id),
            )
        )

    # Questions (rank 4): every outstanding one.
    for question in (
        await session.execute(
            select(Question)
            .where(
                Question.project_id == project_id,
                Question.answered.is_(False),
                Question.declined.is_(False),
            )
            .order_by(Question.created_at, Question.batch_index)
        )
    ).scalars():
        needs.append(
            _need(
                f"question-{question.id}",
                QUESTION,
                agent=question.from_agent,
                title=_one_line(question.question),
                waiting_since=question.created_at,
                action="Answer",
                target=_target("thread", question.id, conversation_id=question.conversation_id),
            )
        )

    # Reviews (rank 5): finished work the operator holds, or that the Hub could not staff.
    reviews = list(
        (
            await session.execute(
                select(Task).where(
                    Task.project_id == project_id,
                    Task.status.in_(("completed", "under_review")),
                )
            )
        ).scalars()
    )
    unstaffed = await _unstaffed(session, project_id, [t.id for t in reviews])
    entered = await _entered(session, reviews)
    for task in reviews:
        since = entered.get(task.id)
        why = unstaffed.get(task.id)
        operator_holds = task.status == "under_review" and task.assignee in _OPERATOR_HOLDERS
        not_staffed = (
            task.status == "completed"
            and why is not None
            and (since is None or _aware(why) >= _aware(since))
        )
        if not (operator_holds or not_staffed):
            continue
        needs.append(
            _need(
                f"review-{task.id}",
                REVIEW,
                agent=task.builder
                or (None if task.assignee in _OPERATOR_HOLDERS else task.assignee),
                title=task.title,
                waiting_since=since or task.updated,
                action="Review",
                target=_target("task", task.id),
            )
        )

    # Permission requests (rank 5): pending and not dismissed.
    for request in (
        await session.execute(
            select(PermissionRequest).where(
                PermissionRequest.project_id == project_id,
                PermissionRequest.status == "pending",
                PermissionRequest.dismissed.is_(False),
            )
        )
    ).scalars():
        needs.append(
            _need(
                f"permission-{request.id}",
                PERMISSION,
                agent=request.agent,
                title=f"{request.agent} asks to use {request.tool_name}",
                waiting_since=request.created_at,
                action="Allow or deny",
                target=_target("permission", request.id, conversation_id=request.conversation_id),
            )
        )

    # Checks that could not run (rank 6).
    for notice in await project_checks.could_not_run_notices(session, project_id):
        needs.append(
            _need(
                f"check-{notice['check']}",
                CHECK,
                agent=None,
                title=f"{notice['check']} could not run",
                waiting_since=datetime.fromisoformat(notice["at"]),
                action="Open checks",
                target=_target("check", notice["check"]),
            )
        )

    # Next-slice offers (rank 6). They carry no time of their own.
    if workspace is not None:
        try:
            offers = await slice_drafting.list_offers(session, workspace, project_id)
        except Exception:  # noqa: BLE001 -- an unreadable roadmap costs its offers, not the read
            logger.warning("could not read next-slice offers for %s", project_id, exc_info=True)
            offers = []
        for offer in offers:
            nxt = offer.get("next_slice") or {}
            needs.append(
                _need(
                    f"offer-{offer['roadmap']}#{nxt.get('key')}",
                    OFFER,
                    agent=offer.get("agent"),
                    title=f"Draft the next slice: {nxt.get('title') or nxt.get('key')}",
                    waiting_since=None,
                    action="Draft",
                    target=_target(
                        "spec",
                        offer.get("document_id"),
                        conversation_id=offer.get("conversation_id"),
                        path=offer["roadmap"],
                    ),
                )
            )

    # Reopening warnings (rank 6).
    for warning in await builds_module.reopening_warnings(session, project_id):
        needs.append(
            _need(
                f"reopening-{warning['build_id']}",
                REOPENING,
                agent=None,
                title=f"{warning['title']} was reopened after it finished",
                waiting_since=(
                    datetime.fromisoformat(warning["reopened_at"])
                    if isinstance(warning.get("reopened_at"), str)
                    else warning.get("reopened_at")
                ),
                action="Open the build",
                target=_target("build", warning["build_id"], path=warning.get("path")),
            )
        )

    # Main moved outside the Hub (rank 6): a need, never a failing main (FR-4).
    for notice in (
        await session.execute(
            select(MainNotice).where(
                MainNotice.project_id == project_id, MainNotice.seen_at.is_(None)
            )
        )
    ).scalars():
        view = main_watch.view(notice)
        needs.append(
            _need(
                f"main_moved-{notice.id}",
                MAIN_MOVED,
                agent=None,
                title=(
                    f"The history of {notice.branch} was rewritten outside the Hub"
                    if view["rewrite"]
                    else f"{notice.branch} moved outside the Hub"
                ),
                waiting_since=notice.created_at,
                action="Mark seen",
                target=_target("setting", notice.id),
            )
        )
    return needs


async def _unstaffed(
    session: AsyncSession, project_id: str, task_ids: Sequence[str]
) -> Dict[str, datetime]:
    """When the Hub last could not staff each task's review (`review_unstaffed`)."""
    from .db.models import EventLog
    from .review_on_completion import REVIEW_UNSTAFFED

    if not task_ids:
        return {}
    found: Dict[str, datetime] = {}
    for data, at in await session.execute(
        select(EventLog.data, EventLog.timestamp)
        .where(
            EventLog.project_id == project_id,
            EventLog.event_type == REVIEW_UNSTAFFED,
            EventLog.data["task_id"].as_string().in_(list(task_ids)),
        )
        .order_by(EventLog.timestamp)
    ):
        if isinstance(data, dict) and data.get("task_id"):
            found[data["task_id"]] = at
    return found


# --- main ----------------------------------------------------------------------------------------


async def _list_checked(session: AsyncSession, project_id: str) -> bool:
    """Whether anything has ever reported against the known-failing list: an entry on it, or a
    finished check run of any kind (a task's, a landing batch's, or one on main)."""
    if await session.scalar(
        select(KnownFailingTest.id).where(KnownFailingTest.project_id == project_id).limit(1)
    ):
        return True
    for model in (TaskCheckRun, MainCheckRun):
        if await session.scalar(
            select(model.id)
            .where(model.project_id == project_id, model.state != "running")
            .limit(1)
        ):
            return True
    return bool(
        await session.scalar(
            select(LandingBatch.id)
            .where(LandingBatch.project_id == project_id, LandingBatch.ended_at.is_not(None))
            .limit(1)
        )
    )


async def main_state(
    session: AsyncSession, project_id: str, *, branch: Optional[str]
) -> Dict[str, Any]:
    """The main tile (FR-4, algorithm 'main-state'). Carries `_since`, the oldest cause's time,
    for the main need; `gather_needs` removes it."""
    from . import known_failing, landing_queue, project_checks

    name = branch or "main"
    held = [
        task_id
        for task_id, (state, _) in (
            await landing_queue.unlanded(session, Task.project_id == project_id)
        ).items()
        if state == landing_queue.HELD
    ]
    held_count = len(held)
    if not await _list_checked(session, project_id):
        return {
            "state": UNKNOWN,
            "branch": branch,
            "held_landings": held_count,
            "fails_on_main": None,
            "flaky": None,
            "detail": f"{name}'s health is unknown: no check has reported on it yet",
        }
    entries = await known_failing.entries(session, project_id)
    failing = [e for e in entries if e.kind == known_failing.FAILS_ON_MAIN]
    flaky = [e for e in entries if e.kind == known_failing.FLAKY]
    notices = await project_checks.could_not_run_notices(session, project_id)
    since: List[datetime] = [m for m in (_aware(e.first_seen) for e in failing) if m is not None]
    since += [datetime.fromisoformat(n["at"]) for n in notices]
    if failing or notices:
        parts = []
        if failing:
            parts.append(
                "1 test fails on it" if len(failing) == 1 else f"{len(failing)} tests fail on it"
            )
        if notices:
            parts.append(
                "1 check could not run"
                if len(notices) == 1
                else f"{len(notices)} checks could not run"
            )
        state, detail = FAILING, f"{name} is failing: " + " and ".join(parts)
    elif held_count:
        state = HELD
        detail = "1 landing is held" if held_count == 1 else f"{held_count} landings are held"
        since += [
            m
            for m in (
                _aware(t.updated)
                for t in (await session.execute(select(Task).where(Task.id.in_(held)))).scalars()
            )
            if m is not None
        ]
    else:
        state, detail = GREEN, f"{name} is green"
    if flaky:
        detail += f" ({len(flaky)} flaky)"
    return {
        "state": state,
        "branch": branch,
        "held_landings": held_count,
        "fails_on_main": len(failing),
        "flaky": len(flaky),
        "detail": detail,
        "_since": min(since) if since else None,
    }


# --- running -------------------------------------------------------------------------------------


async def running(session: AsyncSession, project_id: str) -> List[Dict[str, Any]]:
    """Each turn running now, longest-running first, timed from its run's start (FR-6, D7)."""
    rows = (
        await session.execute(
            select(Run, Task.title, Conversation.title)
            .outerjoin(Task, Task.id == Run.task_id)
            .outerjoin(Conversation, Conversation.id == Run.conversation_id)
            .where(Run.project_id == project_id, Run.status == "running")
            .order_by(Run.started_at, Run.id)
        )
    ).all()
    # A turn on a task carries that task's stage and check state, from the task list's own
    # derivation (`task-stages-in-the-build-view-and-dependency-map` FR-11); null otherwise.
    from .api.v1.tasks import task_stage_reads

    stage_of = await task_stage_reads(
        session, project_id, [run.task_id for run, _, _ in rows if run.task_id]
    )
    return [
        {
            "run_id": run.id,
            "agent": run.agent,
            "conversation_id": run.conversation_id,
            "task_id": run.task_id,
            "what": task_title or conversation_title or "A conversation",
            "started_at": _iso(run.started_at),
            "stage": stage_of.get(run.task_id or "", {}).get("stage"),
            "check_state": stage_of.get(run.task_id or "", {}).get("check_state"),
        }
        for run, task_title, conversation_title in rows
    ]


# --- finished ------------------------------------------------------------------------------------


def _cost_columns() -> Tuple[Any, ...]:
    measured = TurnUsage.status == "measured"
    return (
        func.sum(TurnUsage.api_equivalent_usd_micros),
        func.sum(case((measured, TurnUsage.total_tokens), else_=None)),
        func.sum(TurnUsage.premium_requests),
    )


def _cost(row: Optional[Tuple[Any, Any, Any]]) -> Dict[str, Any]:
    micros, tokens, credits = row or (None, None, None)
    return {
        "usd": round(micros / builds_module.MICROS, 4) if micros is not None else None,
        "tokens": int(tokens) if tokens is not None else None,
        "credits": float(credits) if credits is not None else None,
    }


async def finished(
    session: AsyncSession, project_id: str, *, since: datetime
) -> List[Dict[str, Any]]:
    """What ended since *since*, newest first (FR-7): tasks that landed, were sent back or were
    closed (stopped), and turns that failed or were stopped. A task's cost is every turn bound to
    it; a turn's, its own. Unknown is null, never zero."""
    since = _utc(since)
    items: List[Tuple[datetime, Dict[str, Any]]] = []
    titles: Dict[str, Tuple[str, Optional[str]]] = {}

    def add(at: datetime, item: Dict[str, Any]) -> None:
        items.append((_aware(at) or at, item))

    for row, task in (
        await session.execute(
            select(TaskIntegration, Task)
            .join(Task, Task.id == TaskIntegration.task_id)
            .where(
                TaskIntegration.project_id == project_id,
                TaskIntegration.outcome == "merged",
                TaskIntegration.created_at >= since,
            )
        )
    ).all():
        add(row.created_at, _task_item(f"landed-{row.id}", task, LANDED, row.created_at))
    for row, task in (
        await session.execute(
            select(TaskTransition, Task)
            .join(Task, Task.id == TaskTransition.task_id)
            .where(
                TaskTransition.project_id == project_id,
                TaskTransition.to_status.in_(("revision_needed", "rejected")),
                TaskTransition.created_at >= since,
            )
        )
    ).all():
        outcome = SENT_BACK if row.to_status == "revision_needed" else STOPPED
        add(row.created_at, _task_item(f"{outcome}-{row.id}", task, outcome, row.created_at))
    for run, task_title, conversation_title in (
        await session.execute(
            select(Run, Task.title, Conversation.title)
            .outerjoin(Task, Task.id == Run.task_id)
            .outerjoin(Conversation, Conversation.id == Run.conversation_id)
            .where(
                Run.project_id == project_id,
                Run.status.in_((FAILED, *_STOPPED_RUNS)),
                Run.ended_at.is_not(None),
                Run.ended_at >= since,
            )
        )
    ).all():
        titles[run.id] = (task_title or conversation_title or f"{run.agent}'s turn", run.task_id)
        add(
            run.ended_at,
            {
                "id": f"run-{run.id}",
                "task_id": run.task_id,
                "run_id": run.id,
                "agent": run.agent,
                "title": titles[run.id][0],
                "outcome": FAILED if run.status == FAILED else STOPPED,
                "at": _iso(run.ended_at),
            },
        )
    items.sort(key=lambda pair: (pair[0], pair[1]["id"]), reverse=True)
    chosen = [item for _, item in items[:FINISHED_LIMIT]]

    task_ids = {i["task_id"] for i in chosen if i["task_id"] and not i["run_id"]}
    run_ids = {i["run_id"] for i in chosen if i["run_id"]}
    by_task: Dict[str, Dict[str, Any]] = {}
    by_run: Dict[str, Dict[str, Any]] = {}
    if task_ids:
        for task_id, *figures in await session.execute(
            select(Run.task_id, *_cost_columns())
            .join(Run, Run.id == TurnUsage.run_id)
            .where(TurnUsage.project_id == project_id, Run.task_id.in_(task_ids))
            .group_by(Run.task_id)
        ):
            by_task[task_id] = _cost(tuple(figures))  # type: ignore[arg-type]
    if run_ids:
        for run_id, *figures in await session.execute(
            select(TurnUsage.run_id, *_cost_columns())
            .where(TurnUsage.project_id == project_id, TurnUsage.run_id.in_(run_ids))
            .group_by(TurnUsage.run_id)
        ):
            by_run[run_id] = _cost(tuple(figures))  # type: ignore[arg-type]
    for item in chosen:
        figures = by_run.get(item["run_id"]) if item["run_id"] else by_task.get(item["task_id"])
        item.update(figures or _cost(None))
    return chosen


def _task_item(item_id: str, task: Task, outcome: str, at: datetime) -> Dict[str, Any]:
    return {
        "id": item_id,
        "task_id": task.id,
        "run_id": None,
        "agent": task.builder or task.assignee,
        "title": task.title,
        "outcome": outcome,
        "at": _iso(at),
    }


# --- spend ---------------------------------------------------------------------------------------


async def spend(
    session: AsyncSession, project: Optional[Project], *, day_start: datetime, days: int
) -> Dict[str, Any]:
    """Spend per local day, oldest first, in three units (FR-5, D6): `usd` null where no turn that
    day was priced, `credits` (Copilot's premium requests) null where none reported one, `tokens`
    the measured turns' tokens, and `unpriced_turns` the turns with neither a price nor credits --
    a day with only those is unknown, never $0. With a token budget, its limit and what is used."""
    from . import usage_accounting

    if project is None:
        return {"days": [], "token_budget": None}
    first = day_start - timedelta(days=days - 1)
    end = day_start + timedelta(days=1)
    buckets: List[Dict[str, Any]] = [
        {
            "day": (day_start - timedelta(days=days - 1 - i)).date().isoformat(),
            "_usd": None,
            "tokens": 0,
            "_credits": None,
            "unpriced_turns": 0,
        }
        for i in range(days)
    ]
    for observed_at, micros, status, tokens, credits in await session.execute(
        select(
            TurnUsage.observed_at,
            TurnUsage.api_equivalent_usd_micros,
            TurnUsage.status,
            TurnUsage.total_tokens,
            TurnUsage.premium_requests,
        ).where(
            TurnUsage.project_id == project.id,
            TurnUsage.observed_at >= _utc(first),
            TurnUsage.observed_at < _utc(end),
        )
    ):
        at = _aware(observed_at)
        if at is None:
            continue
        index = int((at - first) // timedelta(days=1))
        if not 0 <= index < days:
            continue
        bucket = buckets[index]
        if micros is not None:
            bucket["_usd"] = (bucket["_usd"] or 0) + micros
        if credits is not None:
            bucket["_credits"] = (bucket["_credits"] or 0.0) + credits
        if status == "measured" and tokens is not None:
            bucket["tokens"] += tokens
        if micros is None and credits is None:
            bucket["unpriced_turns"] += 1
    out_days = [
        {
            "day": b["day"],
            "usd": round(b["_usd"] / builds_module.MICROS, 4) if b["_usd"] is not None else None,
            "tokens": b["tokens"],
            "credits": round(b["_credits"], 4) if b["_credits"] is not None else None,
            "unpriced_turns": b["unpriced_turns"],
        }
        for b in buckets
    ]
    budget = None
    if project.token_budget is not None:
        used = await usage_accounting.used_tokens(session, project.id)
        budget = {"limit": project.token_budget, "used": used or 0}
    return {"days": out_days, "token_budget": budget}
