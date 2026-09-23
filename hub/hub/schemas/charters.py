"""Charter schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .common import RequestModel, VisibleName


class CharterCreate(RequestModel):
    name: VisibleName
    content: str


class CharterUpdate(RequestModel):
    name: Optional[VisibleName] = None
    content: Optional[str] = None


class CharterResponse(BaseModel):
    id: str = Field(max_length=64)
    project_id: str = Field(max_length=64)
    name: str = Field(max_length=256)
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
