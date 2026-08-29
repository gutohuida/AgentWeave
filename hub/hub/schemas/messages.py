"""Message schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .common import RequestModel

_MESSAGE_TYPES = ["message", "delegation", "review", "discussion", "direct_trigger"]


class MessageCreate(RequestModel):
    # JSON uses "from"/"to"; Python model uses sender/recipient
    sender: str = Field(alias="from", max_length=64)
    recipient: str = Field(alias="to", max_length=64)
    subject: Optional[str] = Field(default=None, max_length=256)
    content: str = Field(max_length=10000)
    type: str = Field(default="message", max_length=64)
    task_id: Optional[str] = Field(default=None, max_length=128)
    run_id: Optional[str] = Field(default=None, max_length=64)
    # Which of the recipient's conversations to send into. Unset means the recipient's most
    # recent open one, opening a new one if there is none — the behaviour that predates this
    # field. Naming an archived conversation is refused rather than redirected: where a message
    # lands is the sender's decision, not something the Hub quietly makes for it.
    conversation_id: Optional[str] = Field(default=None, max_length=64)
    # D4: an explicit request for a fresh thread, bypassing the sender's usual binding. The new
    # conversation becomes the bound one for later messages with no extra state, since the
    # existing "newest binding wins" forward lookup already prefers it. Refused in combination
    # with conversation_id — naming a thread and asking for a new one are contradictory.
    start_new_thread: bool = Field(default=False)

    model_config = {"populate_by_name": True}

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
