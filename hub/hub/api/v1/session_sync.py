"""Project-scoped session sync endpoints.

Historically the CLI pushed its local `session.json` here on every save, and the
watchdog re-pushed it on startup as a safety net — this endpoint's roster reconciliation
(`sync_session` below) still implements that contract: the `agents` payload is treated as
the complete, authoritative roster, and any existing `Agent` row omitted from it is
deleted (its worktree released, never discarding unmerged work silently).

Both of those callers are gone as of the `2026-08-03-single-runtime` change: the CLI's
push path (`Session.save()`) and the watchdog itself have no callers/no longer exist in
`src/agentweave`. Today this endpoint is reached only by direct API calls — chiefly the
test suite, which uses it to seed an agent roster for fixtures — and it still performs a
full roster *replace*, not a merge, on every call. An operator-facing roster mutation goes
through `operator-agent-creation` instead (`POST /agents`), which only ever adds.

Calling this endpoint directly against a project with agents you want to keep will delete
any agent whose name is missing from the payload, exactly as it did for a CLI push.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import project_workspace, worktrees
from ...agent_colors import next_color_index
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Agent, ProjectSession
from ...sse import sse_manager
from ...utils import persist_event, short_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/session", tags=["session"])


class SessionSyncRequest(BaseModel):
    data: Dict[str, Any]


@router.post("/sync")
async def sync_session(
    body: SessionSyncRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Upsert a project's agent roster from a full, authoritative payload.

    Idempotent — safe to call repeatedly. See the module docstring: the CLI/watchdog
    callers this contract was built for no longer exist; this is reached today only by
    direct API calls, chiefly the test suite seeding fixtures. `agents` here fully replaces
    the existing roster — any agent omitted from it is deleted.
    """
    project_id, _ = project

    session_result = await session.execute(
        select(ProjectSession).where(ProjectSession.project_id == project_id)
    )
    row = session_result.scalars().first()

    if row:
        row.data = body.data
        row.synced_at = datetime.now(timezone.utc)
    else:
        row = ProjectSession(
            project_id=project_id,
            data=body.data,
            synced_at=datetime.now(timezone.utc),
        )
        session.add(row)

    # Ensure an Agent row exists for every synced agent (drives the "registered"
    # flag in GET /agents/agent-context — a declared agent is "registered" once
    # the Hub knows about it, independent of self-registration) and remove rows
    # for agents no longer in the session.
    agents_data = body.data.get("agents", {})
    for agent_name in agents_data:
        try:
            worktrees.validate_agent_name(agent_name)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    current_agent_names = set(agents_data.keys())
    all_agents_result = await session.execute(select(Agent).where(Agent.project_id == project_id))
    existing_agents = {row.name: row for row in all_agents_result.scalars().all()}

    # Computed once and incremented locally (not re-queried per agent): several new
    # agents can be added in the same sync, and none of them are flushed yet, so a
    # per-iteration query would see the same max and hand out duplicate indices.
    next_index = await next_color_index(session, project_id)
    for agent_name in agents_data:
        if agent_name not in existing_agents:
            session.add(
                Agent(
                    id=f"agent-{short_id()}",
                    project_id=project_id,
                    name=agent_name,
                    color_index=next_index,
                )
            )
            next_index += 1

    removed_agent_names = [
        agent_name
        for agent_name, agent_row in existing_agents.items()
        if agent_name not in current_agent_names
    ]
    for agent_name in removed_agent_names:
        await session.delete(existing_agents[agent_name])

    await session.commit()

    # Task 5.4: an agent no longer in the synced roster is "removed from the project" —
    # release its isolated worktree (if any), never discarding unmerged work silently.
    #
    # Task 6.10, decided rather than inherited: this releases the departing agent's **own**
    # checkout and deliberately leaves the checkouts of the tasks it was working. A task's
    # terminal status is the only thing that releases a task checkout (design D5). A roster edit
    # says nothing about a task — its status is unchanged, and another agent may be assigned to
    # continue it — so releasing here would take a working tree away from a live task for an
    # unrelated reason. The work would survive on the branch either way; the point is that a
    # roster edit must not act on the task lifecycle. Asserted by
    # `test_removing_an_agent_leaves_the_checkouts_of_its_tasks_alone`.
    # Best-effort and after the DB commit above: a git failure here must not roll back
    # the roster sync itself, which is the thing this endpoint actually exists for.
    #
    # Best-effort here too: an unavailable project workspace must not fail the roster
    # sync itself, so this is silently skipped rather than raised — there is nothing to
    # release if the directory the worktrees would live in cannot even be resolved.
    try:
        repo_root = (await project_workspace.resolve_project_workspace(session, project_id)).root
    except project_workspace.ProjectWorkspaceError:
        removed_agent_names = []
    for agent_name in removed_agent_names:
        try:
            release_result = worktrees.release_worktree(repo_root, agent_name)
        except (ValueError, worktrees.GitCommandError):
            logger.warning("Could not release %r's worktree on removal", agent_name, exc_info=True)
            continue
        if not release_result.released:
            continue
        await persist_event(
            session,
            project_id,
            "worktree_released",
            {
                "agent": agent_name,
                "branch": release_result.branch,
                "had_unmerged_work": release_result.has_unmerged_work,
                "unmerged_commits": release_result.unmerged_commits,
            },
            agent=agent_name,
            severity="warn" if release_result.has_unmerged_work else "info",
        )
        await sse_manager.broadcast(
            project_id,
            "worktree_released",
            {
                "agent": agent_name,
                "branch": release_result.branch,
                "had_unmerged_work": release_result.has_unmerged_work,
            },
        )

    # Broadcast so the UI refreshes agent list immediately
    await sse_manager.broadcast(
        project_id,
        "session_synced",
        {"agents": list(body.data.get("agents", {}).keys())},
    )

    return {"ok": True, "agents": sorted(body.data.get("agents", {}).keys())}


@router.get("/sync")
async def get_synced_session(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Return the last synced session configuration for this project."""
    project_id, _ = project

    result = await session.execute(
        select(ProjectSession).where(ProjectSession.project_id == project_id)
    )
    row = result.scalars().first()

    if not row:
        return {"synced": False, "data": None}

    return {"synced": True, "synced_at": row.synced_at.isoformat(), "data": row.data}
