"""Task schemas."""

import re
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .common import RequestModel

# Matches generated ids of the form "{prefix}-{hex}", where the prefix is a short word (e.g.
# "task", "msg"). Deliberately does not pin the segment's width: `short_id()` widened from 8 hex
# characters to 12 on 2026-08-24 and ids at both widths are valid forever, because a segment is only
# ever generated and never parsed. Used to validate client-supplied ids so we only accept well-formed
# ones and reject anything that could be used for path traversal or to impersonate other entity
# types.
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
# Older writers name the assignee two other ways. Both models read them and neither
# declares them, so both must also *remove* them — see the validators below.
_ASSIGNEE_ALIASES = ("assigned_to", "assigned_agent")

# Restated from `hub.run_task_binding.POLICIES` for the same reason, and pinned to it by
# `hub/tests/test_run_task_binding.py`.
_DIVERGENCE_POLICIES = {"surface", "retry", "escalate"}


class TaskCreate(RequestModel):
    title: str = Field(max_length=256)
    description: str = Field(default="", max_length=10000)
    status: str = Field(default="pending", max_length=64)
    priority: str = Field(default="medium", max_length=64)
    assignee: Optional[str] = Field(default=None, max_length=64)
    assigner: Optional[str] = Field(default=None, max_length=64)
    requirements: Optional[List[Any]] = None
    # The requirements this task serves, by identifier. Checked, unlike `requirements`: an
    # identifier the project does not have is refused with the identifier named, rather than stored
    # as text that looks like a reference and resolves to nothing.
    requirement_ids: Optional[List[str]] = None
    # Which document's identifiers to resolve against. Identifiers are minted per document, so a
    # bare `FR-8` is ambiguous where two documents declare one; this is how a caller says which.
    spec_document: Optional[str] = Field(default=None, max_length=255)
    # Adds this task directly to a loop's queue (design D1, `2026-08-18-a-loop-writes-its-own-
    # queue`). Gated in `create_task_for_actor`: only the loop's own `AIJob.agent`, or the
    # operator, may supply this — never trusted from the field alone.
    loop_id: Optional[str] = Field(default=None, max_length=64)
    acceptance_criteria: Optional[List[Any]] = None
    deliverables: Optional[List[Any]] = None
    notes: Optional[Any] = None
    # Optional client-supplied id. When present, the Hub uses it instead of
    # generating one — this lets the MCP `create_task` tool return the same
    # id that the Hub stored, so subsequent get_task / update_task calls by
    # the agent find the task. Validated to the same shape as the CLI's
    # generate_id() output and the local Task model.
    id: Optional[str] = Field(default=None, max_length=64)

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
        if isinstance(data, dict):
            if data.get("assignee") is None:
                for key in _ASSIGNEE_ALIASES:
                    if data.get(key):
                        data = {**data, "assignee": data[key]}
                        break
            # Remove the alias keys whichever name won — a rolling upgrade emits the
            # canonical name *and* its alias in the same body, and stripping only when
            # `assignee` was absent handed the survivor to extra='forbid', refusing a
            # body the contract itself accepts.
            data = {k: v for k, v in data.items() if k not in _ASSIGNEE_ALIASES}
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


class TaskUpdate(RequestModel):
    status: Optional[str] = Field(default=None, max_length=64)
    priority: Optional[str] = Field(default=None, max_length=64)
    # `None` means *clear it*, not *leave it alone* — the difference is carried by
    # `model_fields_set`, exactly as `escalation_agent` below carries it.
    # `update_task_for_actor` read this field as "unset when None" until F78, which made the
    # remedy `_guard_reviewer_is_not_the_author` names — "clear the assignee to review it
    # yourself" — unreachable, and unreachable *silently*: the PATCH returned 200 with the old
    # holder still in it.
    assignee: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = Field(default=None, max_length=10000)
    notes: Optional[Any] = None
    # Requirements this task serves, added to whatever it already serves. Links are never removed
    # here: what work served a requirement is asked mostly about finished work, so the record has to
    # outlive the editing of the task.
    requirement_ids: Optional[List[str]] = None
    spec_document: Optional[str] = Field(default=None, max_length=255)
    divergence_policy: Optional[str] = Field(default=None, max_length=16)
    # Deliberately not `Optional[str] = None means leave alone` for this one: clearing an escalation
    # agent is a thing the operator must be able to do, and `""` is how they say it. Normalised to
    # NULL below so the column never holds an empty name.
    escalation_agent: Optional[str] = Field(default=None, max_length=64)
    # What the task is waiting for, when the operator parks it by hand. Ignored on any other status
    # change — leaving `blocked` always clears it, since a reason that outlives its block describes
    # something that already arrived.
    blocked_reason: Optional[str] = Field(default=None, max_length=2000)
    # `Task.loop_id` is write-once (design D14, `2026-08-18-a-loop-writes-its-own-queue`): a loop's
    # queue history has to be able to answer what work it was ever given, which reassignment would
    # break. Accepted here only so the service layer (`update_task_for_actor`) has a value to refuse
    # by name rather than by `extra="forbid"` silently swallowing it — see D14 for why this is
    # enforced in code and not a DB constraint (SQLite cannot drop one later).
    loop_id: Optional[str] = Field(default=None, max_length=64)

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

    @field_validator("assignee")
    @classmethod
    def normalise_assignee(cls, v: Optional[str]) -> Optional[str]:
        """`""` and `"  "` are the same claim as `null`: nobody holds this task.

        Without this the column grows a second falsy spelling of "unassigned", which every reader
        happens to survive today only because they all test Python truthiness — while the four
        `Task.assignee.isnot(None)` queries in the Hub would quietly start counting it as a holder.
        """
        return v.strip() or None if isinstance(v, str) else v

    @model_validator(mode="before")
    @classmethod
    def normalize_assignee_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("assignee") is None:
                for key in _ASSIGNEE_ALIASES:
                    if data.get(key):
                        data = {**data, "assignee": data[key]}
                        break
            # This model never removed them at all, so *every* alias body it read was
            # then refused by extra='forbid' — the alias was accepted in principle and
            # rejected in fact. Same line as its sibling above.
            data = {k: v for k, v in data.items() if k not in _ASSIGNEE_ALIASES}
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


class TaskDependencyRef(BaseModel):
    """A prerequisite or dependent named on `TaskResponse` — enough to render an edge without a
    second fetch: `id` to link to it, `title` and `status` to show what it is and whether it has
    cleared (`task-dependencies` design D3, task 7.1). `spec_document_id` is what lets a board
    draw a prerequisite outside its own document as an off-board reference naming that document
    (task 8.7) rather than a bare title with nowhere to point."""

    id: str = Field(max_length=64)
    title: str = Field(max_length=256)
    status: str = Field(max_length=32)
    spec_document_id: Optional[str] = Field(default=None, max_length=128)

    model_config = {"from_attributes": True}


class TaskIntegrationSummary(BaseModel):
    """What the most recent approval of this task did to the repository — merged, or skipped why.

    A trimmed echo of one row from `GET /tasks/{id}/integrations`, which existed already but told
    nobody unless they asked it directly. "Approving is what merges it" was true and silent: the
    approve response itself gave no sign whether a merge happened, was skipped (no main branch
    configured, a dirty checkout, nothing to merge), or is not applicable because the task never
    reached `approved`.
    """

    outcome: str = Field(max_length=16)
    reason: str = Field(default="", max_length=2000)
    commit_sha: Optional[str] = Field(default=None, max_length=64)
    target_branch: Optional[str] = Field(default=None, max_length=255)
    created_at: datetime

    model_config = {"from_attributes": True}


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
    # What the caller submitted, kept verbatim. Answers about traceability come from
    # `requirement_links`, never from here — this is the original, so a mis-parse is re-derivable.
    requirements: Optional[Any] = None
    # The requirements this task actually serves: `identifier`, `requirement_id`, `document_id`,
    # `state`, `anchor`, `key`, and — read from the document rather than stored — `statement` and
    # `modal`. `statement` is null where the document no longer words the requirement, which is
    # what a retired one is. `has_rejected_evidence`, `rejected_evidence_count` and
    # `latest_rejection_reason` cover a gap `state` cannot: evidence rejected at the requirement's
    # current digest reads identically to a requirement nobody has attempted, because
    # `requirement_coverage` has no precedence level for "tried and rejected".
    requirement_links: List[Any] = Field(default_factory=list)
    # The read side of `TaskCreate`/`TaskUpdate.requirement_ids`, which were accepted and reported
    # nowhere — so a caller could not confirm what was recorded, and anyone diagnosing why work did
    # not merge saw a task that appeared tied to nothing while the links governing the merge
    # existed. Identifiers, in the form they are submitted in, so what is read back can be sent
    # again; derived from `requirement_links` and never stored.
    requirement_ids: List[str] = Field(default_factory=list)
    # References that named no requirement this project has, with their original text. Visible
    # rather than dropped, because a task that quietly lost a reference it used to have is the
    # failure the migration exists to prevent.
    unresolved_requirements: List[Any] = Field(default_factory=list)
    # `contract`-rigor requirements this task serves that were not verified at the moment this
    # response answers an approval — identifier, state, remedy, the same shape a `gate` refusal
    # names its blockers with. Empty on every response but the one that just approved a task under a
    # document that reports rather than refuses; never persisted, because it describes this moment,
    # not a record (`2026-08-13-a-gate-that-only-evidence-opens`, task 5.5).
    approval_report: List[Any] = Field(default_factory=list)
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
    # What a run bound to this task is waiting on the operator to answer, right now — in the same
    # words `blocked_reason` uses on a task that parked.
    #
    # The ordinary case is now the status: the agent-facing question routes park the asking run's
    # task at ask time (F14). This covers the two waits the status cannot — a task that could not
    # park (`under_review`, `pending`, `assigned`), and a batch whose first answer released the task
    # while the run waits on the rest. Computed per request, never stored — the question row is the
    # record.
    awaiting_answer_reason: Optional[str] = Field(default=None, max_length=2000)
    # Which document this work is against, and — for a task the document itself declared — which of
    # its declared units this is. Written since migration `0071` and exposed nowhere, so nothing
    # above the database layer could tell a declared task from a hand-made one, or get from a task
    # to the specification it implements.
    spec_document_id: Optional[str] = Field(default=None, max_length=64)
    spec_task_key: Optional[str] = Field(default=None, max_length=128)
    # Which loop's queue this task belongs to. `TaskCreate` has accepted `loop_id` since the column
    # existed and the response never carried it back, so `POST /tasks {"loop_id": …}` answered 201
    # with `loop_id: null` while the loop's own summary already counted the task in its queue. The
    # write worked; only the reply denied it, and a caller had no way to confirm from the create
    # call that the task had joined the loop.
    loop_id: Optional[str] = Field(default=None, max_length=64)
    # The most recent attempt to integrate this task's approved work, or null where none has ever
    # been made (every non-`approved` task, and one whose approval predates this field existing on
    # older rows the migration never touched). The full history stays at
    # `GET /tasks/{id}/integrations`; this is only ever the newest row of it.
    latest_integration: Optional[TaskIntegrationSummary] = None
    # `TaskDependency` read from both ends (`task-dependencies` design D3, task 7.1). Never stored
    # here — derived per request from the join table, the same way `requirement_links` is derived
    # from `task_requirement_links` rather than kept as a second copy.
    prerequisites: List[TaskDependencyRef] = Field(default_factory=list)
    dependents: List[TaskDependencyRef] = Field(default_factory=list)
    # One of `"gated"` (a prerequisite is not yet approved), `"gated_on_rejected"` (a prerequisite
    # was rejected and will not clear on its own), `"running_on_regressed"` (this task is already
    # `in_progress` but a prerequisite no longer reads `approved` — flagged, not stopped, per design
    # D8), or `None` when nothing about this task's dependencies is worth surfacing. Derived per
    # request, not stored (task 7.2) — a stored readiness column is a denormalised join that goes
    # stale the moment a prerequisite's status changes under it (design D1).
    dependency_state: Optional[str] = Field(default=None, max_length=32)

    model_config = {"from_attributes": True}
