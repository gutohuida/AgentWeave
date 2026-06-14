"""Agent trigger endpoint — POST /api/v1/agent/trigger

This endpoint creates a message/task that the host-side watchdog will pick up
and execute. This allows the Hub to run in Docker without needing the AI CLIs
installed - the CLIs run on the host machine via the watchdog.

Flow:
1. UI calls /api/v1/agent/trigger
2. Hub creates a message in the database (like a "virtual" incoming message)
3. Watchdog (running on host) polls for messages, sees the new one
4. Watchdog executes the CLI on the host machine
5. Output streams back to Hub via HTTP transport
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Agent, AgentHeartbeat, Message
from ...sse import sse_manager
from ...utils import persist_event, short_id

router = APIRouter(prefix="/agent", tags=["agent-trigger"])


class TriggerAgentRequest(BaseModel):
    agent: str = Field(
        ..., max_length=64, description="Target agent name (e.g., 'claude', 'kimi')"
    )
    message: str = Field(
        ..., max_length=10000, description="Message/prompt to send to the agent"
    )
    session_mode: str = Field(
        default="new",
        max_length=64,
        description="Session mode: 'new' for new session, 'resume' for existing session",
    )
    session_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Session ID to resume (required when session_mode='resume')",
    )
    work_dir: Optional[str] = Field(
        default=None,
        max_length=4096,
        description="Working directory for the agent (defaults to project root)",
    )


class TriggerAgentResponse(BaseModel):
    success: bool
    message: str
    agent: str
    message_id: str
    session_id: Optional[str] = None
    execution_confidence: str = "unknown"
    watchdog_status: Optional[str] = None


@router.post("/trigger", response_model=TriggerAgentResponse)
async def trigger_agent(
    body: TriggerAgentRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Trigger an agent to run with a message.

    This creates a message in the database that the host-side watchdog
    will pick up and execute on the host machine (where the CLIs are installed).

    If the agent is in pilot mode, the message is created but no execution
    will occur — the pilot agent must manually check their inbox.

    Examples:
    - New session: `{"agent": "claude", "message": "Hello", "session_mode": "new"}`
    - Resume session: `{"agent": "claude", "message": "Continue", "session_mode": "resume", "session_id": "sess-abc"}`
    """
    from sqlalchemy import select

    project_id, _ = project

    # Validate session_mode
    if body.session_mode not in ("new", "resume"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_mode must be 'new' or 'resume'",
        )

    # Validate work_dir
    if body.work_dir:
        if ".." in body.work_dir or "~" in body.work_dir or any(
            ord(c) < 32 for c in body.work_dir
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid work_dir",
            )

    # Check if agent is in pilot mode and inspect recent heartbeat state.
    agent_result = await session.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == body.agent)
    )
    agent_row = agent_result.scalars().first()
    is_pilot = agent_row.pilot if agent_row else False
    agent_config = agent_row.config if agent_row and isinstance(agent_row.config, dict) else {}
    is_manual = agent_config.get("runner") == "manual"

    hb_result = await session.execute(
        select(AgentHeartbeat)
        .where(AgentHeartbeat.project_id == project_id, AgentHeartbeat.agent == body.agent)
        .order_by(AgentHeartbeat.timestamp.desc())
        .limit(1)
    )
    latest_hb = hb_result.scalars().first()
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(seconds=120)
    if latest_hb is None:
        execution_confidence = "queued_no_watchdog_heartbeat"
        watchdog_status = "missing"
    else:
        hb_ts = latest_hb.timestamp
        if hb_ts.tzinfo is None:
            hb_ts = hb_ts.replace(tzinfo=timezone.utc)

    if latest_hb is not None and hb_ts < stale_cutoff:
        execution_confidence = "queued_watchdog_stale"
        watchdog_status = "stale"
    elif latest_hb is not None:
        execution_confidence = "queued_watchdog_healthy"
        watchdog_status = latest_hb.status

    if is_pilot or is_manual:
        execution_confidence = "queued_manual"
        watchdog_status = "manual"

    # Build message content with session info.
    # The watchdog parses these tags to determine session handling:
    #   [Session: <id>]  → resume the specified session
    #   [NewSession]     → explicitly start a new session
    #   (no tag)         → fall back to the agent's last saved session
    content_parts = [body.message]
    if body.session_mode == "resume" and body.session_id:
        content_parts.append(f"\n\n[Session: {body.session_id}]")
    elif body.session_mode == "new":
        content_parts.append("\n\n[NewSession]")

    # Create a message that looks like it's from "user" to the agent
    # The watchdog will detect this and trigger the agent
    msg_id = f"msg-{short_id()}"
    msg = Message(
        id=msg_id,
        project_id=project_id,
        sender="user",  # Indicates this is from the human user via Hub
        recipient=body.agent,
        subject="Direct message from Hub",
        content="\n".join(content_parts),
        type="message",  # Use standard message type (direct_trigger caused validation issues)
        timestamp=datetime.now(timezone.utc),
        read=False,  # Mark as unread so watchdog picks it up
        session_id=body.session_id if body.session_mode == "resume" else None,
    )

    session.add(msg)
    await session.commit()
    await session.refresh(msg)

    # Broadcast to SSE so UI updates immediately
    await sse_manager.broadcast(
        project_id,
        "message_created",
        {
            "id": msg.id,
            "from": msg.sender,
            "to": msg.recipient,
            "subject": msg.subject,
            "type": "direct_trigger",  # Tell UI this is a direct trigger
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
        },
    )

    await persist_event(
        session,
        project_id,
        "agent_triggered",
        {
            "agent": body.agent,
            "session_mode": body.session_mode,
            "session_id": body.session_id,
            "message_id": msg_id,
            "execution_confidence": execution_confidence,
            "watchdog_status": watchdog_status,
        },
        agent=body.agent,
    )
    await persist_event(
        session,
        project_id,
        "agent_trigger_confidence",
        {
            "agent": body.agent,
            "message_id": msg_id,
            "execution_confidence": execution_confidence,
            "watchdog_status": watchdog_status,
        },
        agent=body.agent,
        severity="warn" if execution_confidence != "queued_watchdog_healthy" else "info",
    )

    if is_pilot or is_manual:
        if is_pilot:
            manual_reason = "the agent is in pilot mode and requires manual control"
        else:
            manual_reason = "the agent runner is set to manual"
        return TriggerAgentResponse(
            success=True,
            message=f"Message created for {body.agent}, but {manual_reason}. The message will appear in their inbox.",
            agent=body.agent,
            message_id=msg_id,
            session_id=body.session_id,
            execution_confidence=execution_confidence,
            watchdog_status=watchdog_status,
        )

    if execution_confidence == "queued_watchdog_stale":
        message = (
            f"Message queued for {body.agent}, but the latest watchdog heartbeat is stale. "
            "Start or restart the host watchdog if it does not execute shortly."
        )
    elif execution_confidence == "queued_no_watchdog_heartbeat":
        message = (
            f"Message queued for {body.agent}, but no watchdog heartbeat has been seen. "
            "Run agentweave start on the host to enable automatic execution."
        )
    else:
        message = (
            f"Message queued for {body.agent}. "
            "The watchdog on your host will execute it shortly."
        )

    return TriggerAgentResponse(
        success=True,
        message=message,
        agent=body.agent,
        message_id=msg_id,
        session_id=body.session_id,
        execution_confidence=execution_confidence,
        watchdog_status=watchdog_status,
    )


@router.get("/sessions/{agent}")
async def get_agent_sessions(
    agent: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Get unique session IDs for an agent from AgentOutput table.

    Returns sessions that the agent has generated output for, ordered by recency.
    Each session includes last_active (most recent output) and started_at (first output).
    """
    from sqlalchemy import select, func
    from ...db.models import AgentOutput

    project_id, _ = project

    # Group by session_id to get first and last output timestamps per session
    q = (
        select(
            AgentOutput.session_id,
            func.max(AgentOutput.timestamp).label("last_active"),
            func.min(AgentOutput.timestamp).label("started_at"),
        )
        .where(
            AgentOutput.project_id == project_id,
            AgentOutput.agent == agent,
            AgentOutput.session_id.isnot(None),
        )
        .group_by(AgentOutput.session_id)
        .order_by(func.max(AgentOutput.timestamp).desc())
    )
    result = await session.execute(q)
    rows = result.all()

    sessions = [
        {
            "id": row.session_id,
            "type": "agent",
            "path": f".agentweave/agents/{agent}-session.json",
            "last_active": row.last_active.isoformat() if row.last_active else None,
            "started_at": row.started_at.isoformat() if row.started_at else None,
        }
        for row in rows
        if row.session_id
    ]

    return {"sessions": sessions}


# NOTE: The trigger logic uses the message system.
# The watchdog on the host will poll for messages and execute the appropriate CLI command.
