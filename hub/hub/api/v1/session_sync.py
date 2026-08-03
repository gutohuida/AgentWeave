"""Session sync endpoint — POST /api/v1/session/sync

Accepts the full session.json payload pushed from the CLI or watchdog and
stores it in the database. This lets the Hub (running in Docker with no
host filesystem access) know the complete agent configuration — names,
runner metadata, yolo flags, and any future fields — without needing volume mounts.

The CLI calls this automatically on every Session.save(); the watchdog also
calls it on startup as a safety net.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import worktrees
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
    """Upsert the session.json configuration for this project.

    Called automatically by the CLI on every session save and by the
    watchdog on startup. Idempotent — safe to call repeatedly.
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
    # Best-effort and after the DB commit above: a git failure here must not roll back
    # the roster sync itself, which is the thing this endpoint actually exists for.
    repo_root = Path.cwd()
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
