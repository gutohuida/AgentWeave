"""Event log schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class EventLogResponse(BaseModel):
    id: str
    project_id: str
    event_type: str
    agent: Optional[str]
    data: Optional[Any]
    severity: str = "info"
    timestamp: datetime

    model_config = {"from_attributes": True}


class LogEventCreate(BaseModel):
    event_type: str
    agent: Optional[str] = "system"
    data: Optional[Any] = None
    severity: str = "info"
