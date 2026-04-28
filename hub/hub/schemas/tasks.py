"""Task schemas."""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, field_validator, model_validator

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
    title: str
    description: str = ""
    status: str = "pending"
    priority: str = "medium"
    assignee: Optional[str] = None
    assigner: Optional[str] = None
    requirements: Optional[List[Any]] = None
    acceptance_criteria: Optional[List[Any]] = None
    deliverables: Optional[List[Any]] = None
    notes: Optional[Any] = None
    # Allow id/created_at to be passed from CLI format
    id: Optional[str] = None
    created_at: Optional[str] = None

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
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[Any] = None

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
    id: str
    project_id: str
    title: str
    description: str
    status: str
    priority: str
    assignee: Optional[str]
    assigner: Optional[str]
    created_at: datetime
    updated: datetime
    requirements: Optional[Any]
    acceptance_criteria: Optional[Any]
    deliverables: Optional[Any]
    notes: Optional[Any]
    assignee_status: Optional[str] = None
    assignee_status_msg: Optional[str] = None
    assignee_last_seen: Optional[datetime] = None

    model_config = {"from_attributes": True}
