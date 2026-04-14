"""Session sync endpoint — POST /api/v1/session/sync

Accepts the full session.json payload pushed from the CLI or watchdog and
stores it in the database. This lets the Hub (running in Docker with no
host filesystem access) know the complete agent configuration — names,
roles, yolo flags, and any future fields — without needing volume mounts.

The CLI calls this automatically on every Session.save(); the watchdog also
calls it on startup as a safety net.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Agent, ProjectSession
from ...sse import sse_manager
from ...utils import short_id

router = APIRouter(prefix="/session", tags=["session"])


class SessionSyncRequest(BaseModel):
    data: Dict[str, Any]


@router.post("/sync")
async def sync_session(
    body: SessionSyncRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Upsert the session.json configuration for this project.

    Called automatically by the CLI on every session save and by the
    watchdog on startup. Idempotent — safe to call repeatedly.
    """
    project_id, _ = project

    result = await session.execute(
        select(ProjectSession).where(ProjectSession.project_id == project_id)
    )
    row = result.scalars().first()

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

    # Sync pilot flags from session data to the Agent table
    agents_data = body.data.get("agents", {})
    current_agent_names = set(agents_data.keys())

    for agent_name, agent_cfg in agents_data.items():
        pilot_flag = bool(agent_cfg.get("pilot", False))
        agent_result = await session.execute(
            select(Agent).where(Agent.project_id == project_id, Agent.name == agent_name)
        )
        agent_row = agent_result.scalars().first()
        if agent_row:
            agent_row.pilot = pilot_flag
        else:
            session.add(
                Agent(
                    id=f"agent-{short_id()}",
                    project_id=project_id,
                    name=agent_name,
                    pilot=pilot_flag,
                )
            )

    # Remove Agent rows for agents no longer in the session
    all_agents_result = await session.execute(select(Agent).where(Agent.project_id == project_id))
    for agent_row in all_agents_result.scalars().all():
        if agent_row.name not in current_agent_names:
            await session.delete(agent_row)

    await session.commit()

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
):
    """Return the last synced session configuration for this project."""
    project_id, _ = project

    result = await session.execute(
        select(ProjectSession).where(ProjectSession.project_id == project_id)
    )
    row = result.scalars().first()

    if not row:
        return {"synced": False, "data": None}

    return {"synced": True, "synced_at": row.synced_at.isoformat(), "data": row.data}
