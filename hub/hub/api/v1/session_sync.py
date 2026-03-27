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
from ...db.models import ProjectSession
from ...sse import sse_manager

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
