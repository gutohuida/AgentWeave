"""Task schemas."""

import re
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Matches the agentweave CLI's generate_id() output: "{prefix}-{8hex}",
# where the prefix is a short word (e.g. "task", "msg"). Used to validate
# client-supplied ids so we only accept well-formed ones and reject anything
# that could be used for path traversal or to impersonate other entity types.
_TASK_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")

_TASK_STATUSES = [
    "pending",
    "assigned",
    "in_progress",
    "completed",
    "under_review",
    "revision_needed",
    "approved",
    "rejected",
]
_PRIORITIES = ["low", "medium", "high", "critical"]


class TaskCreate(BaseModel):
    title: str = Field(max_length=256)
    description: str = Field(default="", max_length=10000)
    status: str = Field(default="pending", max_length=64)
    priority: str = Field(default="medium", max_length=64)
    assignee: Optional[str] = Field(default=None, max_length=64)
    assigner: Optional[str] = Field(default=None, max_length=64)
    requirements: Optional[List[Any]] = None
    acceptance_criteria: Optional[List[Any]] = None
    deliverables: Optional[List[Any]] = None
    notes: Optional[Any] = None
    # Optional client-supplied id. When present, the Hub uses it instead of
    # generating one — this lets the MCP `create_task` tool return the same
    # id that the Hub stored, so subsequent get_task / update_task calls by
    # the agent find the task. Validated to the same shape as the CLI's
    # generate_id() output and the local Task model.
    id: Optional[str] = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}

    @field_validator("id")
    @classmethod
    def _validate_id_shape(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not _TASK_ID_RE.match(v):
            raise ValueError(
                "id must start with a letter and contain only letters, "
                "digits, underscores, or hyphens (max 64 chars)"
            )
        return v

    @model_validator(mode="before")
    @classmethod
    def normalize_assignee_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("assignee") is None:
            for key in ("assigned_to", "assigned_agent"):
                if data.get(key):
                    data = {**data, "assignee": data[key]}
                    break
            # Remove legacy alias keys so extra='forbid' does not reject them
            data = {k: v for k, v in data.items() if k not in ("assigned_to", "assigned_agent")}
        return data

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in _TASK_STATUSES:
            raise ValueError(f"status must be one of {_TASK_STATUSES}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in _PRIORITIES:
            raise ValueError(f"priority must be one of {_PRIORITIES}")
        return v


class TaskUpdate(BaseModel):
    status: Optional[str] = Field(default=None, max_length=64)
    priority: Optional[str] = Field(default=None, max_length=64)
    assignee: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = Field(default=None, max_length=10000)
    notes: Optional[Any] = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="before")
    @classmethod
    def normalize_assignee_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("assignee") is None:
            for key in ("assigned_to", "assigned_agent"):
                if data.get(key):
                    data = {**data, "assignee": data[key]}
                    break
        return data

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _TASK_STATUSES:
            raise ValueError(f"status must be one of {_TASK_STATUSES}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _PRIORITIES:
            raise ValueError(f"priority must be one of {_PRIORITIES}")
        return v


class TaskResponse(BaseModel):
    id: str = Field(max_length=128)
    project_id: str = Field(max_length=128)
    title: str = Field(max_length=256)
    description: str = Field(max_length=10000)
    status: str = Field(max_length=64)
    priority: str = Field(max_length=64)
    assignee: Optional[str] = Field(default=None, max_length=64)
    assigner: Optional[str] = Field(default=None, max_length=64)
    created_at: datetime
    updated: datetime
    requirements: Optional[Any] = None
    acceptance_criteria: Optional[Any] = None
    deliverables: Optional[Any] = None
    notes: Optional[Any] = None
    assignee_status: Optional[str] = Field(default=None, max_length=64)
    assignee_status_msg: Optional[str] = Field(default=None, max_length=10000)
    assignee_last_seen: Optional[datetime] = None

    model_config = {"from_attributes": True}
