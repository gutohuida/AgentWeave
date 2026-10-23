"""Stalls, and what the mender may do about them (`a-stalled-project-wakes-a-doctor-that-unblocks-it`).

Two routers. `stalls_router` is the operator's: the project's stalls, and ending one by hand.
`mender_router` is reachable only by a run of the Hub's own `mender` agent (`stalls.is_mender`):
the unblock actions it takes **without review** -- merging its resolution of an approved task's
conflict, retrying a merge, withdrawing refused input, handing a task back --
and ending its stall. Nothing here rejects or deletes a task, touches a working tree, or changes a
setting: those are the hardcore moves the mender must ask the operator about, and the absence of a
route for them is the guarantee its brief describes.
"""

from __future__ import annotations

import asyncio
from typing import Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import stalls
from ...agent_auth import AgentActor, get_agent_actor
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Agent, Project, Stall, Task
from ...sse import sse_manager
from ...task_transition_service import TransitionRefusedError
from ...task_transitions import run_actor
from ...utils import persist_event

stalls_router = APIRouter(prefix="/stalls", tags=["stalls"])
mender_router = APIRouter(prefix="/agent-actions/mender", tags=["mender"])


# --- the operator's view -------------------------------------------------------------------------


@stalls_router.get("")
async def list_project_stalls(
    open: bool = False,  # noqa: A002 -- the query parameter's name
    limit: int = Query(default=50, ge=1, le=200),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Newest first. `open=true` keeps the ones nobody has ended."""
    return {"stalls": await stalls.list_stalls(session, project[0], open_only=open, limit=limit)}


class OperatorEnd(BaseModel):
    outcome: Literal["resolved", "gave_up"] = "resolved"
    detail: str = Field(default="", max_length=4000)

    model_config = {"extra": "forbid"}


@stalls_router.post("/{stall_id}/end")
async def end_project_stall(
    stall_id: str,
    body: OperatorEnd,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    stall = await session.get(Stall, stall_id)
    if stall is None or stall.project_id != project[0]:
        raise HTTPException(status_code=404, detail=f"No stall '{stall_id}' in this project")
    await stalls.end(session, stall, body.outcome, body.detail or "Ended by the operator.")
    return stalls.view(stall)


# --- the mender's actions ------------------------------------------------------------------------


async def get_mender_actor(
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
) -> AgentActor:
    agent = (
        await session.execute(
            select(Agent).where(Agent.project_id == actor.project_id, Agent.name == actor.agent)
        )
    ).scalar_one_or_none()
    if not stalls.is_mender(agent):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Hub's mender may use these actions.",
        )
    return actor


async def _task(session: AsyncSession, actor: AgentActor, task_id: str) -> Task:
    task = await session.get(Task, task_id)
    if task is None or task.project_id != actor.project_id:
        raise HTTPException(status_code=404, detail=f"No task '{task_id}' in this project")
    return task


@mender_router.get("/stalls")
async def mender_stalls(
    actor: AgentActor = Depends(get_mender_actor),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return {"stalls": await stalls.list_stalls(session, actor.project_id, open_only=True)}


class MenderEnd(BaseModel):
    outcome: Literal["fixed", "gave_up"]
    summary: str = Field(min_length=1, max_length=4000)

    model_config = {"extra": "forbid"}


@mender_router.post("/stalls/{stall_id}/end")
async def mender_end_stall(
    stall_id: str,
    body: MenderEnd,
    actor: AgentActor = Depends(get_mender_actor),
    session: AsyncSession = Depends(get_session),
) -> dict:
    stall = await session.get(Stall, stall_id)
    if stall is None or stall.project_id != actor.project_id:
        raise HTTPException(status_code=404, detail=f"No stall '{stall_id}' in this project")
    await stalls.end(session, stall, body.outcome, body.summary)
    return stalls.view(stall)


class Landing(BaseModel):
    commit: Optional[str] = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}


@mender_router.post("/tasks/{task_id}/branch")
async def mender_land_task(
    task_id: str,
    body: Landing,
    actor: AgentActor = Depends(get_mender_actor),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Land an approved task's work with no review: the mender's resolution, or a plain retry.

    With *commit*, the Hub merges that commit in place of what approval would merge, provided it
    contains all of that work (`task_transition_service.land_resolution`); where the project has
    checks they run first on the commit merged onto the main branch, and a failure refuses with
    their results for the mender to take to the operator. Without, it retries the merge.
    """
    from ... import project_checks, project_workspace
    from ...task_transition_service import (
        ResolutionRefusedError,
        land_resolution,
        retry_integration,
    )

    task = await _task(session, actor, task_id)
    if task.status != "approved":
        raise HTTPException(
            status_code=409,
            detail=f"{task.id} is {task.status}, not approved: only approved work is merged.",
        )
    who = run_actor(actor.run_id, actor.agent)
    if body.commit:
        root = (await project_workspace.resolve_project_workspace(session, actor.project_id)).root
        resolved = await asyncio.to_thread(
            _git, root, "rev-parse", "--verify", f"{body.commit}^{{commit}}"
        )
        if resolved.returncode != 0:
            raise HTTPException(status_code=409, detail=f"'{body.commit}' is not a commit here.")
        commit = resolved.stdout.strip()
        project = await session.get(Project, actor.project_id)
        if project_checks.configured_checks(project):
            results = await asyncio.to_thread(
                _run_checks, root, task.id, commit, project, project_checks
            )
            if any(project_checks.failed(result) for result in results):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "refused": "The project's checks failed on your fix, so nothing merged. "
                        "Ask the operator.",
                        "checks": results,
                    },
                )
        try:
            results = await land_resolution(session, task, who, commit)
        except ResolutionRefusedError as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    else:
        results = await retry_integration(session, task, who)
    await session.commit()
    payload = {"task_id": task.id, "agent": actor.agent, "commit": body.commit}
    await persist_event(session, actor.project_id, "mender_landed", payload, agent=actor.agent)
    await sse_manager.broadcast(actor.project_id, "task_integration_retried", payload)
    return {
        "task_id": task.id,
        "results": [
            {"outcome": r.outcome, "reason": r.reason, "commit_sha": r.commit_sha} for r in results
        ],
    }


def _git(root, *args):
    import subprocess

    from ...subprocess_windows import no_console_kwargs

    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        timeout=60,
        **no_console_kwargs(),
    )


def _run_checks(root, task_id, commit, project, project_checks) -> list:
    main = project_checks.main_tip(root, project.main_branch) if project.main_branch else None
    merged, why = project_checks.build_merged_commit(root, main, [commit]) if main else (commit, "")
    if merged is None:
        return [{"name": "merge", "exit_code": 1, "timed_out": False, "output": why}]
    path = project_checks._checkout(root, f"mender-{task_id}", merged)
    try:
        return [
            project_checks.run_one(check, path)
            for check in project_checks.configured_checks(project)
        ]
    finally:
        project_checks._remove_checkout(root, path)


@mender_router.post("/queue/{entry_id}/withdraw")
async def mender_withdraw_input(
    entry_id: str,
    actor: AgentActor = Depends(get_mender_actor),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Withdraw input waiting in another agent's queue, so the next firing briefs it again."""
    from ...inbound_queue import not_queued_reason, withdraw_entry

    entry = await withdraw_entry(
        session, actor.project_id, entry_id, reason="withdrawn by the mender"
    )
    if entry is None:
        refusal_status, refusal = await not_queued_reason(
            session, actor.project_id, entry_id, "withdraw"
        )
        raise HTTPException(status_code=refusal_status, detail=refusal)
    payload = {"entry_id": entry.id, "agent": entry.agent, "by": actor.agent}
    await persist_event(
        session, actor.project_id, "queue_entry_withdrawn", payload, agent=entry.agent
    )
    await sse_manager.broadcast(actor.project_id, "queue_entry_withdrawn", payload)
    if entry.job_id is not None:
        from ...scheduler import close_firings_left_without_input

        if await close_firings_left_without_input(session, actor.project_id, entry.job_id):
            await session.commit()
    return {"entry_id": entry.id, "agent": entry.agent, "state": entry.state}


class TaskReset(BaseModel):
    status: Literal["assigned", "pending"]
    assignee: Optional[str] = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}


@mender_router.post("/tasks/{task_id}/reset")
async def mender_reset_task(
    task_id: str,
    body: TaskReset,
    actor: AgentActor = Depends(get_mender_actor),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Hand a stuck task back: to the queue (`pending`) or to an agent (`assigned`).

    Only the edges the transition map gives any run; a task the operator must move answers 409.
    """
    from ...task_transition_service import apply_transition

    task = await _task(session, actor, task_id)
    if body.assignee is not None:
        named = (
            await session.execute(
                select(Agent).where(
                    Agent.project_id == actor.project_id,
                    Agent.name == body.assignee,
                    Agent.lifecycle == "open",
                )
            )
        ).scalar_one_or_none()
        if named is None or stalls.is_mender(named):
            raise HTTPException(
                status_code=400, detail=f"'{body.assignee}' is not an open agent here."
            )
    try:
        if task.status == "in_progress" and body.status == "pending":
            await apply_transition(session, task, "assigned", run_actor(actor.run_id, actor.agent))
        if task.status != body.status:
            await apply_transition(session, task, body.status, run_actor(actor.run_id, actor.agent))
    except TransitionRefusedError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    task.assignee = body.assignee if body.status == "assigned" else None
    await session.commit()
    return {"task_id": task.id, "status": task.status, "assignee": task.assignee}
