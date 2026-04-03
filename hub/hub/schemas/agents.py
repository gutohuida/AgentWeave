"""Agent monitor schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

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
    runner: str = "native"  # "native" | "claude_proxy" | "manual"
    dev_role: Optional[str] = None  # e.g. "tech_lead", "backend_dev" (primary role)
    dev_role_label: Optional[str] = None  # e.g. "Tech Lead", "Backend Developer"
    dev_roles: Optional[List[str]] = None  # All role IDs (new multi-role support)
    dev_role_labels: Optional[List[str]] = None  # Labels for all roles
    context_usage: Optional[Dict[str, Any]] = (
        None  # {percent, warning, model, threshold_warning, updated_at}
    )

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
