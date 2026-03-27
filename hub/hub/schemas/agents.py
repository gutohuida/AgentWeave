"""Agent monitor schemas."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class AgentSummary(BaseModel):
    name: str
    status: str
    latest_status_msg: Optional[str]
    last_seen: Optional[datetime]
    message_count: int
    active_task_count: int
    role: Optional[str] = None  # "principal" | "delegate" | "collaborator"
    yolo: bool = False

    model_config = {"from_attributes": True}


class AgentTimelineEvent(BaseModel):
    id: str
    event_type: str
    timestamp: datetime
    summary: str
    data: Dict[str, Any]

    model_config = {"from_attributes": True}


class AgentHeartbeatCreate(BaseModel):
    status: str = "active"
    message: Optional[str] = None


class AgentOutputCreate(BaseModel):
    content: str
    session_id: Optional[str] = None


class AgentOutputResponse(BaseModel):
    id: str
    agent: str
    session_id: Optional[str]
    content: str
    timestamp: datetime

    model_config = {"from_attributes": True}
