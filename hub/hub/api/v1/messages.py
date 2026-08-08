"""Message endpoints — POST/GET/PATCH."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import project_workspace
from ...auth import get_project
from ...conversations import name_conversation, new_conversation, peer_bound_conversation
from ...db.engine import get_session
from ...db.models import Agent, Conversation, Message, Run
from ...inbound_queue import new_entry, project_limits
from ...schemas.common import SuccessResponse
from ...schemas.messages import MessageCreate, MessageResponse
from ...sse import sse_manager
from ...utils import persist_event, short_id

router = APIRouter(prefix="/messages", tags=["messages"])


async def create_message_for_actor(
    body: MessageCreate,
    *,
    project_id: str,
    sender: str,
    run_id: Optional[str],
    session: AsyncSession,
) -> Message:
    msg = Message(
        id=f"msg-{short_id()}",
        project_id=project_id,
        sender=sender,
        recipient=body.recipient,
        subject=body.subject,
        content=body.content,
        type=body.type,
        timestamp=datetime.now(timezone.utc),
        task_id=body.task_id,
        created_by_run_id=run_id,
    )
    hop_budget, _ = await project_limits(session, project_id)
    hop_depth = hop_budget + 1
    source_conversation_id = None
    if run_id:
        source_run = await session.get(Run, run_id)
        if (
            source_run is None
            or source_run.project_id != project_id
            or source_run.agent != sender
            or source_run.status != "running"
            or source_run.turn_depth is None
        ):
            raise HTTPException(status_code=409, detail="Message run identity is invalid or stale")
        hop_depth = source_run.turn_depth + 1
        # Recorded association, not inferred: the sender's timeline places this
        # outbound entry by the run it was actually sent from (task 8.3).
        msg.session_id = source_run.session_id
        msg.conversation_id = source_run.conversation_id
        source_conversation_id = source_run.conversation_id

    recipient_row = (
        await session.execute(
            select(Agent).where(Agent.project_id == project_id, Agent.name == body.recipient)
        )
    ).scalars().first()
    recipient_exists = recipient_row.id if recipient_row is not None else None
    if recipient_exists is None:
        # Recorded on the SENDER's timeline — task 5.3: the Hub, not just the agent's own
        # tool-call error text, must make this visible to the operator. Without this,
        # send_message to a nonexistent recipient used to succeed silently (201, a real
        # message_id): the Message/InboundQueueEntry got created and queued, addressed to
        # a name no agent would ever poll.
        await persist_event(
            session,
            project_id,
            "agent_action_rejected",
            {
                "endpoint": "POST /messages",
                "reason": "unknown_recipient",
                "recipient": body.recipient,
            },
            agent=sender,
            severity="warn",
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown recipient '{body.recipient}': no agent by that name is "
                "registered in this project"
            ),
        )

    if recipient_row.lifecycle == "archived":
        # The archived-*agent* case, distinct from the archived-*conversation* case below: there
        # is no conversation to name, and opening a new one would not help — nothing runs an
        # archived agent, so the entry would sit queued forever. Same three-part contract, since
        # the reason it exists is the same one: the sender should not have to reconstruct its own
        # message from a context it has already moved past.
        await persist_event(
            session,
            project_id,
            "agent_action_rejected",
            {
                "endpoint": "POST /messages",
                "reason": "archived_agent",
                "recipient": body.recipient,
            },
            agent=sender,
            severity="warn",
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"Agent '{body.recipient}' is archived and cannot receive messages. Ask the "
                "operator to unarchive it, or send to a different agent. Your message was not "
                f"sent. Its content was:\n\n{body.content}"
            ),
        )

    if body.conversation_id:
        recipient_conversation = await session.get(Conversation, body.conversation_id)
        if (
            recipient_conversation is None
            or recipient_conversation.project_id != project_id
            or recipient_conversation.agent != body.recipient
        ):
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Unknown conversation '{body.conversation_id}': no conversation by that "
                    f"id belongs to '{body.recipient}' in this project"
                ),
            )
        if recipient_conversation.lifecycle == "archived":
            # Three parts, and the third is the point: an agent whose send is refused should not
            # have to reconstruct its own message from a context it has already moved past.
            await persist_event(
                session,
                project_id,
                "agent_action_rejected",
                {
                    "endpoint": "POST /messages",
                    "reason": "archived_conversation",
                    "recipient": body.recipient,
                    "conversation_id": body.conversation_id,
                },
                agent=sender,
                severity="warn",
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Conversation '{body.conversation_id}' is archived and cannot receive "
                    f"messages. Send to a new conversation with '{body.recipient}' instead, by "
                    "omitting conversation_id. Your message was not sent. Its content was:\n\n"
                    f"{body.content}"
                ),
            )
    else:
        # The normal path — a sender does not know the recipient's thread ids, so omitting the
        # id is what agents actually do. It used to resolve to whatever thread the recipient
        # touched most recently: three `codex-1 → haiku-1` messages, one exchange by any human
        # reading, landed in three unrelated `haiku-1` threads. Delivery is bound instead, so the
        # same line of work reaches the same thread every time.
        recipient_conversation = await peer_bound_conversation(
            session,
            project_id=project_id,
            recipient=body.recipient,
            sender_conversation_id=source_conversation_id,
            sender=sender,
        )
        if recipient_conversation is None:
            # Also the archive case, and deliberately not a refusal. A sender that *named* an
            # archived conversation is refused above, because it chose one; a binding whose
            # thread the operator archived is not the sender's doing, so it gets a successor
            # bound to the same sender rather than an error about a decision it did not make.
            recipient_conversation = new_conversation(
                project_id=project_id, agent=body.recipient, origin="peer"
            )
            recipient_conversation.bound_sender_conversation_id = source_conversation_id
            recipient_conversation.bound_sender_agent = None if source_conversation_id else sender
            session.add(recipient_conversation)

    entry = new_entry(
        project_id=project_id,
        agent=body.recipient,
        origin_type="agent",
        origin_agent=sender,
        content=body.content,
        hop_depth=hop_depth,
        message_id=msg.id,
        conversation_id=recipient_conversation.id,
    )
    name_conversation(recipient_conversation, body.content)
    session.add_all([msg, entry])
    await session.commit()
    await session.refresh(msg)
    await sse_manager.broadcast(project_id, "message_created", _msg_dict(msg))
    await persist_event(session, project_id, "message_created", _msg_dict(msg), agent=msg.sender)
    queue_payload = {
        "entry_id": entry.id,
        "agent": entry.agent,
        "origin_type": "agent",
        "origin_agent": sender,
        "hop_depth": hop_depth,
        "conversation_id": recipient_conversation.id,
        "source_conversation_id": source_conversation_id,
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


@router.post("", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    body: MessageCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    try:
        await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        project_workspace.raise_workspace_http_error(exc)

    return await create_message_for_actor(
        body,
        project_id=project_id,
        sender=body.sender,
        run_id=body.run_id,
        session=session,
    )


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
