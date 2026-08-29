"""Event log schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from .common import RequestModel


class EventLogResponse(BaseModel):
    id: str = Field(max_length=128)
    project_id: str = Field(max_length=128)
    event_type: str = Field(max_length=64)
    agent: Optional[str] = Field(default=None, max_length=64)
    data: Optional[Any] = None
    severity: str = Field(default="info", max_length=64)
    timestamp: datetime

    model_config = {"from_attributes": True}


class LogEventCreate(RequestModel):
    event_type: str = Field(max_length=64)
    agent: Optional[str] = Field(default="system", max_length=64)
    data: Optional[Any] = None
    severity: str = Field(default="info", max_length=64)
