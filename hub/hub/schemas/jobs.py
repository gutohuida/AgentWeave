"""Job schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from .common import RequestModel


class JobCreate(RequestModel):
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
    # Whether this loop's approved work has to be demonstrated by accepted evidence before approval
    # writes it to the project's main branch (design D2/D3). NULL is "the product's current
    # default", resolved at the point of use — never a stored copy of today's answer.
    #
    # A loop field that does **not** opt a job in (design D4): `_loop_opts_in` stays purpose /
    # stop time / queue-emptiness, because a job created by this field alone would be a loop with
    # no stop condition. Supplying it on a job that is not becoming a loop is a 400, not a silent
    # drop — the drop is invisible until an approval writes, or fails to write, to the operator's
    # main branch weeks later.
    work_needs_evidence: Optional[bool] = None

    @field_validator("session_mode")
    @classmethod
    def validate_session_mode(cls, v: str) -> str:
        if v not in ("new", "resume"):
            raise ValueError("session_mode must be 'new' or 'resume'")
        return v


class JobUpdate(RequestModel):
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
    # Accepted by the schema only so the route can **refuse** it with a sentence saying what to do
    # instead (design D3). Declaring it here rather than letting the request 422 on an unexpected
    # field is deliberate: a 422 says the field is unknown, which is false and offers no remedy.
    work_needs_evidence: Optional[bool] = None

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
    # How many firings this record stands for (`loop-notices-and-reacts` design D6). Always 1 on a
    # record of a firing that happened; more only on a stall record, where each subsequent refusal
    # for the same stall counts here instead of appending another row. Defaults to 1 rather than 0
    # so a row written before the column existed reads as the one firing it represents.
    tick_count: int = 1

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
    # What approving this loop's tasks does to the project's main branch (design D2). On the shape
    # every loop route already returns, because the operator cannot see a fact that decides what
    # their main branch receives unless it is there. NULL is returned as-is, never resolved to the
    # current default — the same serialization `control` below already states.
    work_needs_evidence: Optional[bool] = None
    stop_reason: Optional[str] = None
    stopped_at: Optional[datetime] = None
    # D17: the two axes B1 added — what happened ("completed"/"stopped", or None while running)
    # and housekeeping (when the operator archived it, or None if still listed by default).
    ending_state: Optional[str] = None
    archived_at: Optional[datetime] = None
    queue: Dict[str, int] = Field(default_factory=dict)  # status -> count
    # `loop-becomes-a-flow` task 1.5: a list, because a flow may staff several tasks at once
    # (group 5) and every caller's shape should change once rather than again later. Group 1
    # changes no behaviour, so this holds zero or one member and the UI renders it exactly as it
    # rendered the scalar. Empty list, never null — "nothing current" and "several current" then
    # have the same type, and a caller can iterate without a null check.
    #: Every task this loop is currently working, in queue order (design D15). `agent` is the
    #: selection's agent, or a blocked task's assignee, and is absent when neither is known —
    #: never blank, so a reader is not shown an empty attribution.
    current_tasks: List[Dict[str, str]] = Field(
        # {"id", "title", "status", "agent"?, "agent_capacity"?}
        # `agent_capacity` says what the name means — "working" (a run is genuinely in flight),
        # "held" (this agent owns it and nothing is running: a review that ended without a verdict,
        # or whose turn failed), "next" (who the next firing would give it to) or "assigned" (the
        # row's own assignee, the blocked case). It exists because the board rendered all of them
        # identically, so a completed task showed its prospective reviewer as though that agent
        # were working it (F26).
        # `held` was split out of `working` for F63: the scheduler records an `under_review` task
        # as in-flight whether or not anybody is running it, so "the loop cannot staff this" and
        # "someone is mid-turn on this" had been sharing one word and one label.
        default_factory=list
    )
    # Why this loop's next firing would be refused, or None if it would proceed
    # (`loop-notices-and-reacts` 5.5). Taken from `decide_firing` — the same computation that
    # decides it — rather than inferred from the queue counts, so the board cannot say one thing
    # while the firing does another. Names what is being waited on, not merely that something is:
    # a stalled loop must read as *waiting*, not as dead.
    stall_reason: Optional[str] = None
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


class LoopControlUpdate(RequestModel):
    """Delegate a loop's control to its creator agent, or take it back to the operator
    (design D10, task A1.2). Only these two values exist — see `Loop.control`'s own comment."""

    control: str = Field(max_length=32)

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
