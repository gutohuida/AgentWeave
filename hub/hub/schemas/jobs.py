"""Job schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class JobCreate(BaseModel):
    name: str = Field(max_length=256)
    agent: str = Field(max_length=64)
    message: str = Field(max_length=10000)
    cron: str = Field(max_length=128)
    session_mode: str = Field(default="new", max_length=64)
    enabled: bool = True
    # Source tracking for sync logic
    source: str = Field(default="hub", max_length=64)
    # Loop opt-in (design D6): a `Loop` row is created iff at least one of these three is
    # supplied non-default. A bare `stop_when_queue_empties=False` from an ordinary caller that
    # never mentions loops does not, by itself, opt the job in.
    purpose: Optional[str] = Field(default=None, max_length=4000)
    stop_at: Optional[datetime] = None
    stop_when_queue_empties: bool = False
    # The loop's source document (design D1). Nullable — a loop need not declare one. Enforced
    # unique across loops at the route layer (409) and the DB layer (`Loop.spec_document_id`'s own
    # `unique=True`), not just one or the other.
    spec_document_id: Optional[str] = Field(default=None, max_length=64)
    # Seeds the new loop's queue in the same call that creates it (design D2, `create_loop`'s
    # "definition window"). Each entry is the same shape `TaskCreate` accepts — a plain dict
    # rather than a nested model, matching `submit_spec_document`'s own reasoning: a closed
    # object type would silently drop a field a later schema version adds. Ignored (never an
    # implicit loop opt-in) unless the job is already opting into a loop via the fields above.
    initial_tasks: Optional[List[Dict[str, Any]]] = None

    model_config = {"extra": "forbid"}

    @field_validator("session_mode")
    @classmethod
    def validate_session_mode(cls, v: str) -> str:
        if v not in ("new", "resume"):
            raise ValueError("session_mode must be 'new' or 'resume'")
        return v


class JobUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=256)
    message: Optional[str] = Field(default=None, max_length=10000)
    cron: Optional[str] = Field(default=None, max_length=128)
    session_mode: Optional[str] = Field(default=None, max_length=64)
    enabled: Optional[bool] = None
    # Loop fields (design D6): supplying any of these for a job with no `Loop` row is a 400
    # unless this update is the one that opts the job in for the first time.
    purpose: Optional[str] = Field(default=None, max_length=4000)
    stop_at: Optional[datetime] = None
    stop_when_queue_empties: Optional[bool] = None
    stop_reason: Optional[str] = Field(default=None, max_length=4000)
    spec_document_id: Optional[str] = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}

    @field_validator("session_mode")
    @classmethod
    def validate_session_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("new", "resume"):
            raise ValueError("session_mode must be 'new' or 'resume'")
        return v


class JobRunResponse(BaseModel):
    id: str = Field(max_length=128)
    job_id: str = Field(max_length=128)
    fired_at: datetime
    status: str = Field(max_length=64)
    trigger: str = Field(max_length=64)
    session_id: Optional[str] = Field(default=None, max_length=128)
    error_summary: Optional[str] = Field(default=None, max_length=500)

    model_config = {"from_attributes": True}


class LoopSummary(BaseModel):
    # The `Loop` row's own id — distinct from the job's id `Task.loop_id`/`GET /tasks?loop_id=`
    # actually scope by (design D2). Without it, a caller cannot build that query string at all.
    id: str
    # B4.2 (design D20): the label the operator recognises a loop by. Sourced from the loop's own
    # job's name — `LoopSummary` carried no name of its own before this, so a picker (B5) had
    # nothing to show for a loop except its id.
    label: str
    # Who runs each firing of this loop — its job's `agent`. The index listed a label and a purpose
    # but never said whose loop it was, so "what is running right now" could not be answered by
    # agent (operator, 2026-08-19). Sourced from the job in the same query as `label`, not a second
    # fetch. Distinct from `control`, which says who may EXTEND the queue, not who works it.
    agent: str = ""
    purpose: str
    stop_at: Optional[datetime] = None
    stop_when_queue_empties: bool
    stop_reason: Optional[str] = None
    stopped_at: Optional[datetime] = None
    # D17: the two axes B1 added — what happened ("completed"/"stopped", or None while running)
    # and housekeeping (when the operator archived it, or None if still listed by default).
    ending_state: Optional[str] = None
    archived_at: Optional[datetime] = None
    queue: Dict[str, int] = Field(default_factory=dict)  # status -> count
    current_task: Optional[Dict[str, str]] = None  # {"id", "title", "status"}
    open_questions: int = 0
    # Design D10 (task A1.1): who decides whether this queue may be extended. NULL means the
    # current default (the operator) — returned as-is, never resolved to "operator" here, mirroring
    # `Agent.default_permission_mode`'s own serialization (`agents.py:1858`).
    control: Optional[str] = None
    # Design D11 (task A2.4): the pending edit, reported SEPARATELY from the live fields above —
    # "a requirement, not polish" (the task's own words). Only present (non-None) while a
    # `POST /jobs/{job_id}` edit is staged and waiting for the next firing to apply it; only the
    # keys among "purpose"/"stop_at"/"stop_when_queue_empties" that were actually staged appear,
    # alongside "staged_by" and "staged_at".
    pending_edit: Optional[Dict[str, Any]] = None
    # Design D13 (task A4.4): is a firing of this loop's job in progress right now (`JobRun.status
    # == "in_progress"`, task A4.3). The ONE shared answer to "is a firing active for this loop" —
    # every caller of `_batch_loop_summaries` gets it, so the edit-staging response (`POST
    # /jobs/{job_id}`) and the loop panel (`GET /loops`, `GET /loops/{loop_id}`) read the same
    # fact computed the same way, never two independent queries drifting apart.
    firing_active: bool = False


class LoopDetail(LoopSummary):
    """A loop's own record — everything `LoopSummary` carries, plus the parent job id, its firing
    history (design D16's guarantee: still fully readable once archived, B2.6), and its audit
    trail."""

    job_id: str
    history: List[Dict[str, Any]] = Field(default_factory=list)
    # Design D13 (task A4.1/A4.2): this loop's own slice of `event_logs` — control changes, staged
    # and applied edits, and how it stopped — filtered by the indexed `loop_id` column, not derived
    # by re-parsing every event's JSON `data`. Never includes another loop's events (A4.2's own
    # isolation requirement).
    events: List[Dict[str, Any]] = Field(default_factory=list)


class LoopControlUpdate(BaseModel):
    """Delegate a loop's control to its creator agent, or take it back to the operator
    (design D10, task A1.2). Only these two values exist — see `Loop.control`'s own comment."""

    control: str = Field(max_length=32)

    model_config = {"extra": "forbid"}

    @field_validator("control")
    @classmethod
    def validate_control(cls, v: str) -> str:
        if v not in ("operator", "creator"):
            raise ValueError("control must be 'operator' or 'creator'")
        return v


class JobResponse(BaseModel):
    id: str = Field(max_length=128)
    project_id: str = Field(max_length=128)
    name: str = Field(max_length=256)
    agent: str = Field(max_length=64)
    message: str = Field(max_length=10000)
    cron: str = Field(max_length=128)
    session_mode: str = Field(max_length=64)
    enabled: bool
    created_at: datetime
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int
    last_session_id: Optional[str] = Field(default=None, max_length=128)
    source: str = Field(default="hub", max_length=64)  # "local" or "hub"
    # D16: NULL means live and listed by default; set only by `POST /jobs/{id}/archive`.
    archived_at: Optional[datetime] = None
    history: Optional[List[Dict[str, Any]]] = None  # Included in get_job only
    loop: Optional[LoopSummary] = None
    # Set only when creating a loop into a project that cannot produce checkpoints. A loop's
    # continuity between firings *is* its checkpoint (design D5, tasks 7.1-7.3, 9.1), so without
    # one every firing starts blank — and nothing said so until three firings later
    # (human-only check 13.2, 2026-08-19). Advisory, never a refusal: a loop with no memory is a
    # legitimate thing to want, it just should not be a surprise.
    continuity_warning: Optional[str] = None

    model_config = {"from_attributes": True}
