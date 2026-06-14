"""Message schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_MESSAGE_TYPES = ["message", "delegation", "review", "discussion", "direct_trigger"]


class MessageCreate(BaseModel):
    # JSON uses "from"/"to"; Python model uses sender/recipient
    sender: str = Field(alias="from", max_length=64)
    recipient: str = Field(alias="to", max_length=64)
    subject: Optional[str] = Field(default=None, max_length=256)
    content: str = Field(max_length=10000)
    type: str = Field(default="message", max_length=64)
    task_id: Optional[str] = Field(default=None, max_length=128)

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        # Reference the module-level variable dynamically
        import hub.schemas.messages as _mod

        if v not in _mod._MESSAGE_TYPES:
            raise ValueError(f"type must be one of {_mod._MESSAGE_TYPES}")
        return v


class MessageResponse(BaseModel):
    id: str = Field(max_length=128)
    project_id: str = Field(max_length=128)
    sender: str = Field(serialization_alias="from", max_length=64)
    recipient: str = Field(serialization_alias="to", max_length=64)
    subject: Optional[str] = Field(default=None, max_length=256)
    content: str = Field(max_length=10000)
    type: str = Field(max_length=64)
    timestamp: datetime
    read: bool
    read_at: Optional[datetime] = None
    task_id: Optional[str] = Field(default=None, max_length=128)

    model_config = {"populate_by_name": True, "from_attributes": True}
