"""One build read for the build view (`a-build-view-showing-every-task-and-run-of-a-build`).

Answers exactly `BuildRead` of `hub/ui/src/components/builds/buildViewModel.ts`: the build, its
tasks in the document's declared order and then the ones added later, each with its runs, its
send-backs and its requirements' evidence, and the runs of the build that worked no single task.

The run set is `work_tally.tally(build_id=...)`'s (`build_runs`), and a run's role is the one the
tally gave it (`run_roles`), so the totals the view adds up equal `GET /project/builds/{id}/figures`.
Nothing here counts a run, a cost or a send-back by a rule of its own.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import build_needs, work_tally
from .db.models import (
    Build,
    RequirementEvidence,
    Run,
    SpecDocument,
    SpecRequirement,
    Stall,
    Task,
    TaskRequirementLink,
    TaskTransition,
    TurnUsage,
)
from .spec_identity import natural_key

#: `work_tally.ROLES` in the view's words (`RunRole`).
_ROLE = {"building": "build", "reviewing": "review", "mending": "mender", "leading": "lead"}
_SEND_BACKS = ("revision_needed", "rejected")


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _declared_keys(payload: Optional[Dict[str, Any]]) -> List[str]:
    return [
        str(entry["key"])
        for entry in (payload or {}).get("tasks") or []
        if isinstance(entry, dict) and entry.get("key")
    ]


def _ordered(tasks: Iterable[Task], document_id: str, keys: List[str]):
    """Declared tasks in the document's order, then the rest in the order they were made."""
    position = {key: i for i, key in enumerate(keys)}

    def declared(task: Task) -> bool:
        return task.spec_document_id == document_id and task.spec_task_key in position

    mine = sorted(tasks, key=lambda t: (t.created_at, t.id))
    first = sorted((t for t in mine if declared(t)), key=lambda t: position[t.spec_task_key])
    return [(t, True) for t in first] + [(t, False) for t in mine if not declared(t)]


def _cost_state(run: Any, usage: Optional[TurnUsage]) -> str:
    if run.status == "running":
        return "running"
    if usage is None:
        return "unreported"
    return "measured" if usage.api_equivalent_usd_micros is not None else "unpriced"


def _by(transition: TaskTransition) -> Dict[str, Any]:
    if transition.origin == "checks":
        return {"kind": "checks"}
    if transition.actor_kind == "operator" or not transition.actor_agent:
        return {"kind": "operator"}
    return {"kind": "agent", "agent": transition.actor_agent}


async def build_read(
    session: AsyncSession,
    project_id: str,
    build: Build,
    document: Optional[SpecDocument],
    payload: Optional[Dict[str, Any]],
    now: Optional[datetime] = None,
    *,
    stages: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """*stages*: each task's `stage` and `check_state` by id, as the task list derives them
    (`api.v1.tasks.stage_reads`); a task missing from it reads both as null."""
    stages = stages or {}
    now = now or datetime.now(timezone.utc)
    whole = await work_tally.tally(session, project_id, build_id=build.id, now=now)
    roles: Dict[str, str] = whole["run_roles"]
    run_ids = list(whole["build_runs"].get(build.id, []))

    task_rows = list(
        (await session.execute(select(Task).where(Task.build_id == build.id))).scalars().all()
    )
    task_ids = [t.id for t in task_rows]

    runs = (
        {
            r.id: r
            for r in (await session.execute(select(Run).where(Run.id.in_(run_ids)))).scalars().all()
        }
        if run_ids
        else {}
    )
    usages = (
        {
            u.run_id: u
            for u in (await session.execute(select(TurnUsage).where(TurnUsage.run_id.in_(run_ids))))
            .scalars()
            .all()
        }
        if run_ids
        else {}
    )
    conversations = {r.conversation_id for r in runs.values() if r.conversation_id}
    stall_where = Stall.project_id == project_id
    if task_ids and conversations:
        stall_where = stall_where & (
            Stall.task_id.in_(task_ids) | Stall.conversation_id.in_(list(conversations))
        )
    elif task_ids:
        stall_where = stall_where & Stall.task_id.in_(task_ids)
    elif conversations:
        stall_where = stall_where & Stall.conversation_id.in_(list(conversations))
    else:
        stall_where = None
    stalls = (
        list(
            (await session.execute(select(Stall).where(stall_where).order_by(Stall.first_seen_at)))
            .scalars()
            .all()
        )
        if stall_where is not None
        else []
    )
    stall_of: Dict[str, Stall] = {}
    for stall in stalls:
        if stall.conversation_id:
            stall_of.setdefault(stall.conversation_id, stall)

    transitions = (
        list(
            (
                await session.execute(
                    select(TaskTransition)
                    .where(TaskTransition.task_id.in_(task_ids))
                    .order_by(TaskTransition.sequence)
                )
            )
            .scalars()
            .all()
        )
        if task_ids
        else []
    )
    moves_of_run: Dict[str, List[Dict[str, Any]]] = {}
    for tr in transitions:
        if tr.run_id:
            moves_of_run.setdefault(tr.run_id, []).append(
                {"from": tr.from_status, "to": tr.to_status}
            )

    # ── runs ──
    def run_read(run: Any) -> Dict[str, Any]:
        usage = usages.get(run.id)
        state = _cost_state(run, usage)
        stall = stall_of.get(run.conversation_id) if run.conversation_id else None
        role = _ROLE.get(roles.get(run.id, "other"))
        if role is None:
            role = "mender" if stall is not None else "lead"
        measured = usage is not None and usage.status == "measured"
        return {
            "id": run.id,
            "role": role,
            "agent": run.agent,
            "model": usage.model if usage else None,
            "conversation_id": run.conversation_id,
            "started_at": _iso(run.started_at),
            "ended_at": _iso(run.ended_at),
            "status": run.status,
            "cost_state": state,
            "cost_usd_micros": usage.api_equivalent_usd_micros if state == "measured" else None,
            "tokens": (
                {
                    "input": usage.input_tokens,
                    "output": usage.output_tokens,
                    "cache_read": usage.cache_read_tokens,
                    "cache_write": usage.cache_write_tokens,
                }
                if measured
                else None
            ),
            "moves": moves_of_run.get(run.id, []),
            "mend": (
                {
                    "cause": stall.cause,
                    "outcome": None if stall.outcome == "open" else stall.outcome,
                    "detail": stall.outcome_detail or stall.reason or None,
                }
                if stall is not None and role == "mender"
                else None
            ),
        }

    on_task: Dict[str, List[Dict[str, Any]]] = {tid: [] for tid in task_ids}
    on_build: List[Dict[str, Any]] = []
    for run in sorted(runs.values(), key=lambda r: (r.started_at, r.id)):
        stall = stall_of.get(run.conversation_id) if run.conversation_id else None
        owner = run.task_id if run.task_id in on_task else None
        if owner is None and stall is not None and stall.task_id in on_task:
            owner = stall.task_id
        (on_task[owner] if owner else on_build).append(run_read(run))

    # ── requirements and their evidence ──
    link_rows = (
        (
            await session.execute(
                select(TaskRequirementLink.task_id, SpecRequirement.id, SpecRequirement.identifier)
                .join(SpecRequirement, SpecRequirement.id == TaskRequirementLink.requirement_id)
                .where(TaskRequirementLink.task_id.in_(task_ids))
            )
        ).all()
        if task_ids
        else []
    )
    latest: Dict[tuple, str] = {}
    if task_ids:
        pieces = (
            await session.execute(
                select(
                    RequirementEvidence.task_id,
                    RequirementEvidence.requirement_id,
                    RequirementEvidence.review_state,
                )
                .where(RequirementEvidence.task_id.in_(task_ids))
                .order_by(RequirementEvidence.produced_at, RequirementEvidence.id)
            )
        ).all()
        for task_id, requirement_id, state in pieces:
            latest[(task_id, requirement_id)] = state
    requirements: Dict[str, List[Dict[str, str]]] = {tid: [] for tid in task_ids}
    for task_id, requirement_id, identifier in sorted(
        link_rows, key=lambda r: natural_key(r.identifier)
    ):
        requirements[task_id].append(
            {"identifier": identifier, "evidence": latest.get((task_id, requirement_id), "missing")}
        )

    # ── send-backs ──
    send_backs: Dict[str, List[Dict[str, Any]]] = {tid: [] for tid in task_ids}
    for tr in transitions:
        if tr.to_status in _SEND_BACKS:
            send_backs[tr.task_id].append(
                {
                    "sequence": tr.sequence,
                    "at": _iso(tr.created_at),
                    "to": tr.to_status,
                    "by": _by(tr),
                    "run_id": tr.run_id,
                    "reason_class": tr.reason_class,
                    "reason": tr.reason or "",
                    "note": tr.note or "",
                }
            )
    last_change: Dict[str, datetime] = {}
    for tr in transitions:
        last_change[tr.task_id] = tr.created_at

    # ── what waits on the operator: the one definition the build list reads too ──
    needs = (await build_needs.needs_of_builds(session, project_id, [build]))[build.id]

    tasks_read = []
    for task, declared in _ordered(task_rows, build.document_id, _declared_keys(payload)):
        tasks_read.append(
            {
                "id": task.id,
                "ref": task.readable_id,
                "title": task.title,
                "status": task.status,
                "stage": stages.get(task.id, {}).get("stage"),
                "check_state": stages.get(task.id, {}).get("check_state"),
                "declared": declared,
                "builder": task.builder or task.assignee,
                "checker": _checker(build, task),
                "last_change_at": _iso(last_change.get(task.id) or task.updated),
                "needs_operator": needs.tasks.get(task.id),
                "requirements": requirements[task.id],
                "runs": on_task[task.id],
                "send_backs": send_backs[task.id],
            }
        )

    return {
        "build": {
            "id": build.id,
            "document_id": build.document_id,
            "document_title": (document.title or document.path) if document else build.document_id,
            "document_path": document.path if document else None,
            "state": build.state,
            "level": build.level,
            "created_at": _iso(build.created_at),
            "stopped_at": _iso(build.stopped_at),
            "stop_reason": build.stop_reason,
            "needs_operator": needs.build,
            "attention_dismissed": build_needs.attention_dismissed(build, needs),
        },
        "tasks": tasks_read,
        "build_runs": on_build,
        "as_of": _iso(now),
    }


def _checker(build: Build, task: Task) -> Optional[str]:
    from .builds import checker_of

    named = checker_of(build, task)
    return (named[0] if named else None) or task.checker
