"""Message endpoints — POST/GET/PATCH."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Message, Run
from ...inbound_queue import new_entry, project_limits
from ...schemas.common import SuccessResponse
from ...schemas.messages import MessageCreate, MessageResponse
from ...sse import sse_manager
from ...utils import persist_event, short_id

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    body: MessageCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    msg = Message(
        id=f"msg-{short_id()}",
        project_id=project_id,
        sender=body.sender,
        recipient=body.recipient,
        subject=body.subject,
        content=body.content,
        type=body.type,
        timestamp=datetime.now(timezone.utc),
        task_id=body.task_id,
    )
    hop_budget, _ = await project_limits(session, project_id)
    hop_depth = hop_budget + 1
    if body.run_id:
        source_run = await session.get(Run, body.run_id)
        if (
            source_run is None
            or source_run.project_id != project_id
            or source_run.agent != body.sender
            or source_run.status != "running"
            or source_run.turn_depth is None
        ):
            raise HTTPException(status_code=409, detail="Message run identity is invalid or stale")
        hop_depth = source_run.turn_depth + 1

    entry = new_entry(
        project_id=project_id,
        agent=body.recipient,
        origin_type="agent",
        origin_agent=body.sender,
        content=body.content,
        hop_depth=hop_depth,
        message_id=msg.id,
    )
    session.add_all([msg, entry])
    await session.commit()
    await session.refresh(msg)
    await sse_manager.broadcast(project_id, "message_created", _msg_dict(msg))
    await persist_event(session, project_id, "message_created", _msg_dict(msg), agent=msg.sender)
    queue_payload = {
        "entry_id": entry.id,
        "agent": entry.agent,
        "origin_type": "agent",
        "origin_agent": body.sender,
        "hop_depth": hop_depth,
    }
    await persist_event(
        session, project_id, "queue_entry_queued", queue_payload, agent=body.recipient
    )
    await sse_manager.broadcast(project_id, "queue_entry_queued", queue_payload)
    if hop_depth > hop_budget:
        suspended = {
            "entry_id": entry.id,
            "agent": entry.agent,
            "hop_depth": hop_depth,
            "hop_budget": hop_budget,
        }
        await persist_event(
            session,
            project_id,
            "queue_chain_suspended",
            suspended,
            agent=body.recipient,
            severity="warn",
        )
        await sse_manager.broadcast(project_id, "queue_chain_suspended", suspended)

    from ...turn_scheduler import schedule_agent

    await schedule_agent(project_id, body.recipient)
    return msg


@router.get("", response_model=List[MessageResponse])
async def list_messages(
    agent: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    history: bool = Query(False),
    sort: str = Query("asc"),
    conversation: Optional[str] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    q = select(Message).where(Message.project_id == project_id)
    if not history:
        q = q.where(Message.read == False)  # noqa: E712
    if agent:
        q = q.where(Message.recipient == agent)
    if conversation:
        parts = conversation.split(":", 1)
        if len(parts) == 2:
            a, b = parts[0], parts[1]
            q = q.where(
                or_(
                    and_(Message.sender == a, Message.recipient == b),
                    and_(Message.sender == b, Message.recipient == a),
                )
            )
    order_col = Message.timestamp.desc() if sort == "desc" else Message.timestamp.asc()
    q = q.order_by(order_col).offset(offset).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.patch("/{message_id}/read", response_model=SuccessResponse)
async def mark_read(
    message_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    msg = await session.get(Message, message_id)
    if msg is None or msg.project_id != project_id:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.read = True
    msg.read_at = datetime.now(timezone.utc)
    await session.commit()
    await sse_manager.broadcast(project_id, "message_read", {"id": message_id})
    await persist_event(session, project_id, "message_read", {"id": message_id})
    return SuccessResponse(message="Message marked as read")


def _msg_dict(msg: Message) -> dict:
    return {
        "id": msg.id,
        "from": msg.sender,
        "to": msg.recipient,
        "subject": msg.subject,
        "content": msg.content,
        "type": msg.type,
        "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
        "task_id": msg.task_id,
        "read": msg.read,
    }
