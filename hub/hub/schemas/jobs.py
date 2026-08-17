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
    # Loop opt-in (design D6): a `Loop` row is created iff at least one of these three is
    # supplied non-default. A bare `stop_when_queue_empties=False` from an ordinary caller that
    # never mentions loops does not, by itself, opt the job in.
    purpose: Optional[str] = Field(default=None, max_length=4000)
    stop_at: Optional[datetime] = None
    stop_when_queue_empties: bool = False

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
    # Loop fields (design D6): supplying any of these for a job with no `Loop` row is a 400
    # unless this update is the one that opts the job in for the first time.
    purpose: Optional[str] = Field(default=None, max_length=4000)
    stop_at: Optional[datetime] = None
    stop_when_queue_empties: Optional[bool] = None
    stop_reason: Optional[str] = Field(default=None, max_length=4000)

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


class LoopSummary(BaseModel):
    # The `Loop` row's own id — distinct from the job's id `Task.loop_id`/`GET /tasks?loop_id=`
    # actually scope by (design D2). Without it, a caller cannot build that query string at all.
    id: str
    purpose: str
    stop_at: Optional[datetime] = None
    stop_when_queue_empties: bool
    stop_reason: Optional[str] = None
    stopped_at: Optional[datetime] = None
    queue: Dict[str, int] = Field(default_factory=dict)  # status -> count
    current_task: Optional[Dict[str, str]] = None  # {"id", "title", "status"}
    open_questions: int = 0


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
    loop: Optional[LoopSummary] = None

    model_config = {"from_attributes": True}
