"""Agent monitor schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentSummary(BaseModel):
    name: str = Field(max_length=64)
    status: str = Field(max_length=64)
    latest_status_msg: Optional[str] = Field(default=None, max_length=10000)
    last_seen: Optional[datetime] = None
    message_count: int
    active_task_count: int
    role: Optional[str] = Field(default=None, max_length=64)  # "principal" | "delegate" | "collaborator"
    yolo: bool = False
    runner: str = Field(default="native", max_length=64)  # "native" | "claude_proxy" | "kimi" | "manual"
    display_model: Optional[str] = Field(default=None, max_length=128)  # e.g. "Claude", "Kimi", "Minimax" — derived from runner
    dev_role: Optional[str] = Field(default=None, max_length=64)  # e.g. "tech_lead", "backend_dev" (primary role)
    dev_role_label: Optional[str] = Field(default=None, max_length=128)  # e.g. "Tech Lead", "Backend Developer"
    dev_roles: Optional[List[str]] = None  # All role IDs (new multi-role support)
    dev_role_labels: Optional[List[str]] = None  # Labels for all roles
    context_usage: Optional[Dict[str, Any]] = (
        None  # {percent, warning, model, threshold_warning, updated_at}
    )
    session_started_at: Optional[datetime] = None  # When the current session started
    pilot: bool = False  # Pilot mode: manual control, disables auto-execution
    registered_session_id: Optional[str] = Field(default=None, max_length=128)  # Registered --resume session ID for pilot agents
    self_registered: bool = False  # True if agent joined via self-registration
    liveness: Optional[str] = Field(default=None, max_length=64)  # "online" | "offline" for self-registered agents
    runner_options: Optional[Dict[str, Any]] = (
        None  # Runner-specific options (e.g., memory for Codex)
    )

    model_config = {"from_attributes": True}


class AgentTimelineEvent(BaseModel):
    id: str = Field(max_length=128)
    event_type: str = Field(max_length=64)
    timestamp: datetime
    summary: str = Field(max_length=10000)
    data: Dict[str, Any]

    model_config = {"from_attributes": True}


class AgentHeartbeatCreate(BaseModel):
    status: str = Field(default="active", max_length=64)
    message: Optional[str] = Field(default=None, max_length=10000)


class AgentOutputCreate(BaseModel):
    content: str = Field(max_length=10000)
    session_id: Optional[str] = Field(default=None, max_length=128)


class AgentOutputResponse(BaseModel):
    id: str = Field(max_length=128)
    agent: str = Field(max_length=64)
    session_id: Optional[str] = Field(default=None, max_length=128)
    content: str = Field(max_length=10000)
    timestamp: datetime

    model_config = {"from_attributes": True}
