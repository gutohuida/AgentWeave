"""Task schemas."""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

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

    model_config = {"extra": "forbid"}

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
