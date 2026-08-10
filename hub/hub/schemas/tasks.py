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
    "blocked",
    "completed",
    "under_review",
    "revision_needed",
    "approved",
    "rejected",
]
_PRIORITIES = ["low", "medium", "high", "critical"]

# Restated from `hub.task_transitions.ENTRY_STATUSES`; the two are pinned together by
# `hub/tests/test_task_transitions.py`. Restated rather than imported because this module is a
# leaf that the schemas layer imports widely, and the transition module imports nothing.
_ENTRY_STATUSES = {"pending", "assigned"}

# Restated from `hub.run_task_binding.POLICIES` for the same reason, and pinned to it by
# `hub/tests/test_run_task_binding.py`.
_DIVERGENCE_POLICIES = {"surface", "retry", "escalate"}


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
        # Creation is narrower than update: a task may only *start* at an entry point, or the
        # machine is walkable around by creating a task already `approved`
        # (openspec/changes/2026-08-10-task-transition-machine, design D10).
        if v not in _ENTRY_STATUSES:
            raise ValueError(f"a new task must start at one of {sorted(_ENTRY_STATUSES)}")
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
    divergence_policy: Optional[str] = Field(default=None, max_length=16)
    # Deliberately not `Optional[str] = None means leave alone` for this one: clearing an escalation
    # agent is a thing the operator must be able to do, and `""` is how they say it. Normalised to
    # NULL below so the column never holds an empty name.
    escalation_agent: Optional[str] = Field(default=None, max_length=64)
    # What the task is waiting for, when the operator parks it by hand. Ignored on any other status
    # change — leaving `blocked` always clears it, since a reason that outlives its block describes
    # something that already arrived.
    blocked_reason: Optional[str] = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def blocking_by_hand_must_say_what_for(self) -> "TaskUpdate":
        """A hand-set block names what it is waiting for, or it is not accepted (R5).

        Required rather than optional because an unexplained block is the failure mode the status
        was introduced to fix. A card that says only "blocked" leaves the operator working out what
        they are holding up — which is exactly the position they were in when the task said
        `in_progress` and nothing was happening.

        A runtime block is not affected: it fills the reason from the question text, and does not
        come through this schema.
        """
        if self.status == "blocked" and not (self.blocked_reason or "").strip():
            raise ValueError("blocked_reason is required when setting a task to blocked")
        return self

    @field_validator("blocked_reason")
    @classmethod
    def normalise_blocked_reason(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() or None if isinstance(v, str) else v

    @field_validator("divergence_policy")
    @classmethod
    def validate_divergence_policy(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _DIVERGENCE_POLICIES:
            raise ValueError(f"divergence_policy must be one of {sorted(_DIVERGENCE_POLICIES)}")
        return v

    @field_validator("escalation_agent")
    @classmethod
    def normalise_escalation_agent(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() or None if isinstance(v, str) else v

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
    divergence_policy: str = Field(default="surface", max_length=16)
    escalation_agent: Optional[str] = Field(default=None, max_length=64)
    # Whether a run bound to this task ended without moving it and nothing has since. Computed,
    # not stored: the durable record is the divergence row, and a second copy on the task would be
    # one more thing that can disagree with it.
    has_open_divergence: bool = False
    # What a `blocked` task is waiting for. NULL on every other status. Since a blocked task stays
    # in the in_progress column rather than moving to one of its own (R3), this is most of what
    # tells the operator the card is waiting on them.
    blocked_reason: Optional[str] = Field(default=None, max_length=2000)

    model_config = {"from_attributes": True}
