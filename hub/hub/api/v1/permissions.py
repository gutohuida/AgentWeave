"""Operator-facing permission requests — list what is waiting, and answer it.

The agent-facing halves (open, poll) live in `agent_actions.py` under the run's own credential.
These are the operator's side of the same rows.
"""

from datetime import datetime, timezone
from typing import List, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import PermissionRequest
from ...sse import sse_manager
from ...utils import persist_event

router = APIRouter(prefix="/permission-requests", tags=["permission-requests"])


class PermissionDecision(BaseModel):
    allow: bool
    # Free-text is deliberately absent: the answer an agent receives is the decision, and a
    # message the operator types here would be a second channel nothing reads.
    model_config = {"extra": "forbid"}


class PermissionRequestResponse(BaseModel):
    id: str
    agent: str
    run_id: str | None
    tool_name: str
    tool_use_id: str
    tool_input: dict
    status: str
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None

    model_config = {"from_attributes": True}


@router.get("", response_model=List[PermissionRequestResponse])
async def list_permission_requests(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
    pending_only: bool = True,
):
    """List permission requests, newest first. Pending-only by default — that is what the
    operator can still act on."""
    project_id, _ = project
    query = select(PermissionRequest).where(PermissionRequest.project_id == project_id)
    if pending_only:
        query = query.where(PermissionRequest.status == "pending")
    query = query.order_by(PermissionRequest.created_at.desc()).limit(100)
    return list((await session.execute(query)).scalars().all())


@router.post("/{request_id}/decide", response_model=PermissionRequestResponse)
async def decide_permission_request(
    request_id: str,
    body: PermissionDecision,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Answer one pending request.

    Deciding an already-decided request is refused rather than silently re-answered: the run
    has taken the first answer and moved on, so a second one would change nothing while
    appearing to.
    """
    project_id, _ = project
    row = (
        await session.execute(
            select(PermissionRequest).where(
                PermissionRequest.id == request_id,
                PermissionRequest.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such permission request")
    if row.status != "pending":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"this request was already {row.status}; the run has moved on",
        )

    row.status = "allowed" if body.allow else "denied"
    row.decided_at = datetime.now(timezone.utc)
    row.decided_by = "operator"
    await session.commit()
    await session.refresh(row)

    if not body.allow:
        await persist_event(
            session,
            project_id=project_id,
            event_type="permission_denied",
            agent=row.agent,
            data={
                "tool_name": row.tool_name,
                "tool_use_id": row.tool_use_id,
                "reason": "the operator refused this action",
                "run_id": row.run_id,
            },
            severity="warn",
        )
    await sse_manager.broadcast(
        project_id,
        "permission_decided",
        {"id": row.id, "agent": row.agent, "status": row.status},
    )
    return row
