"""Job schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator


class JobCreate(BaseModel):
    name: str
    agent: str
    message: str
    cron: str
    session_mode: str = "new"
    enabled: bool = True
    # Allow id to be passed from CLI format
    id: Optional[str] = None
    # Source tracking for sync logic
    source: str = "hub"

    @field_validator("session_mode")
    @classmethod
    def validate_session_mode(cls, v: str) -> str:
        if v not in ("new", "resume"):
            raise ValueError("session_mode must be 'new' or 'resume'")
        return v


class JobUpdate(BaseModel):
    name: Optional[str] = None
    message: Optional[str] = None
    cron: Optional[str] = None
    session_mode: Optional[str] = None
    enabled: Optional[bool] = None

    @field_validator("session_mode")
    @classmethod
    def validate_session_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("new", "resume"):
            raise ValueError("session_mode must be 'new' or 'resume'")
        return v


class JobRunResponse(BaseModel):
    id: str
    job_id: str
    fired_at: datetime
    status: str
    trigger: str
    session_id: Optional[str] = None

    model_config = {"from_attributes": True}


class JobResponse(BaseModel):
    id: str
    project_id: str
    name: str
    agent: str
    message: str
    cron: str
    session_mode: str
    enabled: bool
    created_at: datetime
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int
    last_session_id: Optional[str] = None
    source: str = "hub"  # "local" or "hub"
    history: Optional[List[Dict[str, Any]]] = None  # Included in get_job only

    model_config = {"from_attributes": True}
