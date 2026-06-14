"""Job schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class JobCreate(BaseModel):
    name: str = Field(max_length=256)
    agent: str = Field(max_length=64)
    message: str = Field(max_length=10000)
    cron: str = Field(max_length=128)
    session_mode: str = Field(default="new", max_length=64)
    enabled: bool = True
    # Source tracking for sync logic
    source: str = Field(default="hub", max_length=64)

    model_config = {"extra": "forbid"}

    @field_validator("session_mode")
    @classmethod
    def validate_session_mode(cls, v: str) -> str:
        if v not in ("new", "resume"):
            raise ValueError("session_mode must be 'new' or 'resume'")
        return v


class JobUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=256)
    message: Optional[str] = Field(default=None, max_length=10000)
    cron: Optional[str] = Field(default=None, max_length=128)
    session_mode: Optional[str] = Field(default=None, max_length=64)
    enabled: Optional[bool] = None

    model_config = {"extra": "forbid"}

    @field_validator("session_mode")
    @classmethod
    def validate_session_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("new", "resume"):
            raise ValueError("session_mode must be 'new' or 'resume'")
        return v


class JobRunResponse(BaseModel):
    id: str = Field(max_length=128)
    job_id: str = Field(max_length=128)
    fired_at: datetime
    status: str = Field(max_length=64)
    trigger: str = Field(max_length=64)
    session_id: Optional[str] = Field(default=None, max_length=128)
    error_summary: Optional[str] = Field(default=None, max_length=500)

    model_config = {"from_attributes": True}


class JobResponse(BaseModel):
    id: str = Field(max_length=128)
    project_id: str = Field(max_length=128)
    name: str = Field(max_length=256)
    agent: str = Field(max_length=64)
    message: str = Field(max_length=10000)
    cron: str = Field(max_length=128)
    session_mode: str = Field(max_length=64)
    enabled: bool
    created_at: datetime
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int
    last_session_id: Optional[str] = Field(default=None, max_length=128)
    source: str = Field(default="hub", max_length=64)  # "local" or "hub"
    history: Optional[List[Dict[str, Any]]] = None  # Included in get_job only

    model_config = {"from_attributes": True}
