"""Agent trigger endpoint — POST /api/v1/agent/trigger

Spawns the target agent's CLI directly and returns a real run identifier immediately.
Claude Code uses a pseudo-terminal (`pty_runner.PtySession`); Codex's non-interactive
``exec --json`` uses a hidden pipe process (`pty_runner.PipeSession`). Output streams live
over the existing SSE channel (`agent_output`, `context_warning`) through the same recording
path a self-reporting agent already uses (`output_recording.py`).

This replaces the message-tag protocol (Decision 2): no synthetic `Message` row, no
`[Session: ...]` / `[NewSession]` text tags, no `execution_confidence` guess about whether
some other process might eventually pick the request up. Session identity is a typed field
on the run record (`Run.session_id`), never text embedded in a message body.

Only claude/claude_proxy/native and codex are wired to an actual spawn path today —
`runner_commands.py`'s scope. Kimi, OpenCode, and Copilot are refused with a stated 501 rather than
silently mishandled. There is no fallback runtime for them. Extending the Hub adapter list to cover
every runner is future work.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ... import (
    bound_address,
    instance_identity,
    project_workspace,
    requirement_evidence,
    review_turn,
    run_liveness,
    task_workspace,
    worktrees,
)
from ...agent_auth import hash_run_token, mint_run_token
from ...auth import get_project
from ...checkpoint_handover import consider_handover_from_run_end
from ...codex_appserver import (
    TRANSPORT_SENTINELS,
    AppServerError,
    TurnOutcome,
    readable_exit_code,
    uses_app_server,
)
from ...codex_appserver import approval_label as codex_approval_label
from ...codex_appserver import run_turn as codex_run_turn
from ...conversation_titles import maybe_generate_title
from ...conversations import (
    conversation_for_provider_session,
    conversation_id_for_run,
    get_conversation_by_id,
    get_open_conversation,
    name_conversation,
    new_conversation,
)
from ...db.engine import async_session_factory, get_session
from ...db.models import Agent, Conversation, PermissionRequest, Project, Run, Runner, Task
from ...inbound_queue import (
    abandoned_for_run,
    deliver_entries_with_run,
    new_entry,
    return_run_entries,
    withdraw_refused_entry,
)
from ...launchability import (
    access_path_notice,
    auto_snapshot_notice,
    get_agent_config,
    probe_agent,
    resolve_access_path,
    resolve_agent_env,
    spec_turn_notice,
)
from ...model_catalog import (
    FULL_ACCESS_PERMISSION_MODE,
    PERMISSION_MODE_CONTROL,
    WORKSPACE_PERMISSION_MODE,
    render_control_config,
    validate_overrides,
)
from ...output_recording import record_agent_output, record_context_usage
from ...permission_requests import expire_pending_for_run
from ...pty_runner import (
    STRUCTURED_OUTPUT_DIMENSIONS,
    PipeSession,
    PtySession,
    strip_ansi_escapes,
    terminate_process_tree,
)
from ...run_divergence import evaluate_run_end, record_response_run
from ...run_task_binding import (
    TaskBindingError,
    bind_run_to_task,
    decided_task_refusal,
    rebind_conversation,
    resolve_bound_task,
    resolve_task_for_project,
    spec_document_for_task,
    tasks_held_by_a_running_turn,
)
from ...runner_commands import (
    OPERATOR_POSTURE,
    SUPPORTED_RUNNERS,
    UnsupportedRunnerError,
    build_command,
    catalog_provider_for_runner,
)
from ...runner_events import AccountingSample
from ...runner_parsing import (
    parse_claude_line,
    parse_codex_line,
    read_codex_rollout_accounting,
)
from ...scheduler import (
    REVIEWABLE_LOOP_TASK_STATUSES,
    WITH_REVIEWER_LOOP_TASK_STATUSES,
    enter_selected_task,
    finalize_job_run_for_conversation,
)
from ...schemas.common import RequestModel
from ...spec_manifest import SpecPathError, validate_spec_path
from ...sse import sse_manager
from ...task_transition_service import TransitionRefusedError
from ...usage_accounting import record_turn_usage
from ...utils import persist_event, short_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent-trigger"])

# A running background task with no other strong reference can be garbage-collected by
# asyncio mid-execution (a well-documented footgun) — this set keeps each run's task alive
# until it finishes, regardless of the triggering request's own lifecycle.
_background_runs: set = set()

# The two live-run registries moved to `run_liveness` (design D3, open question 2): the gate that
# refuses approval while a turn is live has to read them, and `requirement_gate` importing a route
# module would invert the layering. This module is still the only writer; the reads below are
# unchanged apart from the name.
# run_ids whose stop was requested via the endpoint below. `_execute_run`'s own completion
# handling reads this once the process exits to tell "stopped deliberately" (final status
# "stopped") apart from "crashed/exited non-zero on its own" (final status "failed") — the
# exit code alone can't distinguish the two once a forced terminate is involved. The
# app-server path also polls this set directly (`run_turn`'s `should_interrupt`), since it has
# no process handle to terminate from the outside.
_stop_requested: set = set()

# How long a Codex approval waits for the operator, and how often it re-reads the decision.
# Codex holds its JSON-RPC request open throughout; unlike Claude's tool call there is no
# provider-side ceiling measured here, so this matches the Claude approver's budget rather than
# inventing a longer one.
CODEX_OPERATOR_DECISION_TIMEOUT = 120
CODEX_OPERATOR_POLL_SECONDS = 2


class TriggerAgentRequest(RequestModel):
    agent: str = Field(..., max_length=64, description="Target agent name (e.g., 'claude')")
    message: str = Field(..., max_length=10000, description="Prompt to send to the agent")
    conversation_id: Optional[str] = Field(default=None, max_length=64)
    session_mode: Optional[str] = Field(
        default=None, max_length=64, description="Deprecated legacy field"
    )
    session_id: Optional[str] = Field(
        default=None, max_length=128, description="Required when session_mode='resume'"
    )
    work_dir: Optional[str] = Field(
        default=None,
        max_length=4096,
        description="Project-relative working directory for the agent process (read-only "
        "agents only; refused for a writing agent, which always gets its isolated worktree)",
    )
    overrides: Optional[Dict[str, str]] = Field(
        default=None,
        description="Runtime control overrides (e.g. {'model': 'claude-opus-5', "
        "'effort': 'high'}), validated against the model catalog and persisted onto the "
        "conversation before it is scheduled.",
    )
    spec_document: Optional[str] = Field(
        default=None,
        max_length=512,
        description="The specification document the operator has open, when the message comes "
        "from the specification workspace. Carried into the canonical turn context, never into "
        "the stored message.",
    )
    task_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="The task this run is being started for. Binds the run and moves the task to "
        "in_progress when that move is legal. Operator-supplied: an agent cannot bind its own run, "
        "because a run that never binds is never checked at its boundary.",
    )
    review_task_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Start this turn as a review of the named task's finished work. The agent's "
        "workspace becomes a detached checkout of the commit that task's most recent evidence "
        "names, and its own working checkout is outside the turn's boundary. Refused when the "
        "task has no evidence naming a commit, because then there is nothing to review.",
    )

    @field_validator("spec_document")
    @classmethod
    def _validate_spec_document(cls, v: Optional[str]) -> Optional[str]:
        # Same validator the sync endpoint uses, so one definition of a legal specification path
        # serves both the write and the read. An empty string is "no document open", not a path.
        if v is None or v == "":
            return None
        try:
            return validate_spec_path(v)
        except SpecPathError as exc:
            raise ValueError(str(exc)) from exc


class TriggerAgentResponse(BaseModel):
    success: bool
    message: str
    agent: str
    run_id: Optional[str] = None
    status: str
    conversation_id: str
    provider_session_id: Optional[str] = None
    session_id: Optional[str] = None
    queue_entry_id: Optional[str] = None
    waiting_reason: Optional[str] = None


class TriggerAgentError(Exception):
    """Raised by `trigger_agent_directly` on any pre-flight rejection.

    Deliberately not `HTTPException` — this function has no FastAPI-request coupling so
    task 3.10's scheduled-job caller (`scheduler.py`) can call it directly. The `/trigger`
    route below catches this and converts it back to an `HTTPException` for HTTP callers.
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        workspace_unavailable: bool = False,
        directory_state: Optional[str] = None,
        transient: bool = False,
        request_level: bool = False,
        agent_wide: bool = False,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.workspace_unavailable = workspace_unavailable
        self.directory_state = directory_state
        #: Does this refusal describe a condition that **clears on its own**?
        #:
        #: `schedule_agent` sorts refusals into two buckets, and the terminal one counts a delivery
        #: attempt and withdraws the entry at the third — its own comment gives the reason, that a
        #: refusal raised here "repeats identically forever". That is true of an archived agent or
        #: a review target with no commit, and false of a collision with another turn, which ends
        #: when that turn does. Classifying the second as the first drops the operator's input
        #: after three ticks of an ordinary flow (design D8).
        #:
        #: The classification is asked directly rather than derived from each cause, so a third
        #: transient refusal does not mean editing `schedule_agent` again. `workspace_unavailable`
        #: was the first of them and keeps its own name because it *also* selects an operator
        #: event; it implies this flag rather than duplicating it.
        self.transient = transient or workspace_unavailable
        #: Is this refusal about **what was asked**, rather than about the environment the agent
        #: would have run in?
        #:
        #: A second, independent question from `transient`, and deliberately not its negation.
        #: `transient` asks whether the condition clears on its own, which decides whether a
        #: delivery attempt is counted. This one asks whether waiting could ever help, which
        #: decides whether the caller who submitted the input is told *no* instead of *queued*.
        #:
        #: The non-transient population splits, and the split is the whole point (design D10 of
        #: `2026-08-28-a-refused-request-says-so`). *No runner is bound*, *the runner's CLI is not
        #: on PATH*, *the worktree could not be prepared* are all about the environment: the
        #: product queues that input on purpose so that performing the repair delivers it, which
        #: is what F96 exists to guarantee. Refusing those would delete input the Hub has promised
        #: to keep. *This task is already under review*, *the reviewer is its own author*,
        #: *there is no such agent* are about the request: no repair to the environment makes the
        #: answer different, so the operator should be told now rather than acknowledged and left
        #: waiting for something that will never happen (F108).
        #:
        #: Defaults to `False`, so an unmarked raise site keeps behaving exactly as it did. The
        #: behaviour change is the set of sites that opt in, and nothing else — a raise site added
        #: later stays queued-and-stated until somebody decides otherwise, which is the safe
        #: direction for a flag whose other value discards the operator's input.
        self.request_level = request_level
        #: Does this refusal stop the agent running **at all**, rather than blocking this input in
        #: particular?
        #:
        #: A third question, and independent of both flags above — not a combination of them.
        #: `transient` decides whether the condition clears on its own; `request_level` decides
        #: whether the caller is told *no*; this one decides whether **giving up on the input at
        #: the head of the queue would let anything else run**.
        #:
        #: That is the only question the delivery-attempt counter should be asking (design D3a of
        #: `2026-08-28-a-delivery-attempt-means-a-delivery`). F56 added counting to the refusal
        #: path because "a refusal raised here repeats identically forever, and every entry queued
        #: behind it starves along with it" — true wherever the refused entry is *in the way*, and
        #: false where the refusal stops the agent entirely, because then there is nothing behind
        #: it that dropping it would release. Measured live 2026-08-28 (F114): three messages to an
        #: agent with no runner bound destroyed the first, and two clicks of the Continue button
        #: destroyed it faster, because each one counted an attempt for a delivery nobody made.
        #:
        #: **Marked conservatively, and the two axes really do cross.** `:479` (no such agent) is
        #: request-level *and* agent-wide; `:756` (the isolated worktree could not be prepared) is
        #: environment-level *and* entry-specific, because the workspace it failed to prepare is
        #: the **task's** rather than the agent's. Only refusals that are certainly agent-wide are
        #: marked, so an unmarked site keeps counting exactly as it does today and no starvation
        #: can be reintroduced by getting this wrong.
        self.agent_wide = agent_wide
        super().__init__(detail)


async def _spec_phase_for(
    session, project_id: str, spec_document: Optional[str]
) -> Tuple[Optional[str], bool]:
    """The open document's (phase, is_unwritten), or (None, False) when there is no row for it.

    Failure is silent by design: a turn must not be refused because the phase could not be read.
    The canonical context carries the same statement, so losing the prompt notice degrades to the
    behaviour that existed before it.

    `is_unwritten` is F51's signal: `POST /documents` ("start exploration") writes an initial
    save with `requirements: []`, so `content_digest` is already set by the time an agent's turn
    reads it — that column cannot tell "just created" apart from "genuinely written". What does
    is `requirement_digests`, which is `{}` until a submission carries at least one requirement,
    exactly the state "start exploration" leaves its own document in, and exactly when the open
    document IS the write target rather than incidental context.
    """
    if not spec_document:
        return None, False
    try:
        from ... import spec_lifecycle

        row = await spec_lifecycle.get_document(session, project_id, spec_document)
        if row is None:
            return None, False
        return row.phase, not row.requirement_digests
    except Exception:  # noqa: BLE001 - a missing phase must never cost the turn
        return None, False


async def _review_task_from_entries(
    session: AsyncSession, queue_entry_ids: Optional[List[str]]
) -> Optional[str]:
    """Which task, if any, the queued entries starting this turn ask to have reviewed.

    Refuses rather than picks when two entries in one batch name different tasks. A turn has one
    workspace (design D4), so "review both" is not a thing this can mean, and choosing one silently
    would put the reviewer on one commit while its context named the other.

    Also refuses a batch mixing a review entry with a work entry (design D3, finding F66). The
    scheduler's own narrowing of `selected` (`turn_scheduler.py`) already keeps this from
    happening for anything it assembles, so a mixed batch reaching here can only be one a caller
    hand-built by naming `queue_entry_ids` directly — this is defence in depth, not the primary
    mechanism.
    """
    if not queue_entry_ids:
        return None
    from sqlalchemy import select

    from ...db.models import InboundQueueEntry

    result = await session.execute(
        select(InboundQueueEntry.review_task_id, InboundQueueEntry.task_id).where(
            InboundQueueEntry.id.in_(queue_entry_ids),
        )
    )
    rows = result.all()
    named = {review_task_id for review_task_id, _ in rows if review_task_id}
    if not named:
        return None
    if len(named) > 1:
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            "this turn batches requests to review more than one task "
            f"({', '.join(sorted(named))}); a review turn has one workspace and one subject",
            request_level=True,
        )
    review_task_id = named.pop()
    # A "work entry" here means one asserting `task_id` with no `review_task_id` beside it — the
    # same distinction `turn_scheduler._entry_kind` makes. An entry naming neither (a plain message
    # riding along) has no kind to conflict with a review and is not counted (the existing
    # `test_entries_agreeing_on_one_review_task_resolve_to_it` pins exactly this).
    work_task_ids = sorted(
        {task_id for review_task_id_col, task_id in rows if review_task_id_col is None and task_id}
    )
    if work_task_ids:
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            f"this turn batches a request to review {review_task_id} together with work on "
            f"{', '.join(work_task_ids)}; a turn admits entries of one kind only",
            request_level=True,
        )
    return review_task_id


async def review_dispatch_refusal(
    session: AsyncSession, task: "Task", *, reviewer: str
) -> "Optional[Tuple[int, str]]":
    """Why *reviewer* may not be dispatched to review *task*, or `None`.

    The read-only half of what `enter_selected_task` would refuse, so the operator's route can
    answer immediately instead of queueing an entry whose turn will never start. Stated here once
    and called from both places rather than written twice: the dispatch is still the authority --
    the flow path never passes through the route -- and this must not drift from it.

    Design D8, D9 and D5, in the order they become knowable.
    """
    # Imported here, not at module scope: this module is imported back by `task_transitions`'s
    # neighbours, and the service imports nothing from the API layer.
    from ...task_transition_service import agent_that_completed

    if task.status not in (REVIEWABLE_LOOP_TASK_STATUSES + WITH_REVIEWER_LOOP_TASK_STATUSES):
        return (
            status.HTTP_409_CONFLICT,
            f"Task {task.id} is {task.status!r}, which is not a status a review starts from. "
            f"A review begins from work that is awaiting one. Staffing a reviewer onto this task "
            f"would take it from whoever holds it and move it nowhere.",
        )
    if (
        task.status in WITH_REVIEWER_LOOP_TASK_STATUSES
        and task.assignee
        and task.assignee != reviewer
    ):
        return (
            status.HTTP_409_CONFLICT,
            f"Task {task.id} is already under review by {task.assignee!r}. Reassign the task if "
            f"{reviewer!r} should take it over, or let the review in flight finish.",
        )
    completing_agent = await agent_that_completed(session, task.id)
    if completing_agent is not None and completing_agent == reviewer:
        return (
            status.HTTP_403_FORBIDDEN,
            f"Cannot review task {task.id} as {reviewer!r}: that is the agent recorded as "
            f"completing it, so the review would claim its own author is reviewing it. Dispatch a "
            f"different reviewer, or clear the assignee to review it yourself.",
        )
    return None


# Bounds and default of a question wait, restated from `mcp_server.py`.
#
# Restated rather than imported, in the direction that is possible: `mcp_server` is spawned
# standalone and may import only stdlib and fastmcp, so it cannot import from here and already
# restates `MIN_WAITING_SECONDS`/`MAX_WAITING_SECONDS` under a comment ending "A test asserts the
# two agree". `test_question_wait_resolution.py` is that test for these.
QUESTION_WAIT_ENV = "AW_QUESTION_TIMEOUT"
QUESTION_WAIT_DEFAULT = 240
QUESTION_WAIT_MIN = 10
QUESTION_WAIT_MAX = 600


def _parse_question_wait(raw: Optional[str]) -> int:
    """`mcp_server._configured_wait`'s rules, Hub-side.

    Anything absent, unparseable or out of range falls back to the default rather than raising —
    the tool will take exactly that fallback, and the Hub's recorded deadline has to describe the
    wait the tool actually performs, not the one the setting intended.
    """
    if not raw:
        return QUESTION_WAIT_DEFAULT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return QUESTION_WAIT_DEFAULT
    return value if QUESTION_WAIT_MIN <= value <= QUESTION_WAIT_MAX else QUESTION_WAIT_DEFAULT


def effective_question_wait(agent_row: Optional[Agent]) -> int:
    """How long *agent_row*'s next run will wait for an answer, in seconds.

    **The Hub owns every input to this, which is why the ask carries nothing** (design D3). Rounds
    1 and 2 of this change had the ask send `wait_seconds` on the agent-facing schema, on the
    stated ground that the Hub could not compute the deadline. It can, and the alternative was not
    merely more expensive but wrong: `wait_seconds` would arrive over the run's own credential, so
    the refusal in `POST /questions/wait-ended` — the thing that keeps an expiry a report of a fact
    rather than a lever — would have compared the report against a number the reporting party
    chose.

    Resolved in the order the spawn below writes the environment, so the two cannot disagree:

    1. the agent's own resolved `env_vars`, which `resolve_agent_env` merges over the Hub's
       environment;
    2. the Hub's own environment, which is what an unconfigured run inherits;
    3. `Agent.question_timeout_seconds`, which this function's caller writes **last** and which
       therefore overrides both;

    then `_configured_wait`'s parse, because the tool applies it to whatever ends up there.
    """
    raw: Optional[str] = None
    env_vars = ((agent_row.config if agent_row is not None else None) or {}).get("env_vars") or {}
    if QUESTION_WAIT_ENV in env_vars:
        raw = str(env_vars[QUESTION_WAIT_ENV])
    else:
        raw = os.environ.get(QUESTION_WAIT_ENV)
    if agent_row is not None and agent_row.question_timeout_seconds is not None:
        raw = str(agent_row.question_timeout_seconds)
    return _parse_question_wait(raw)


async def trigger_agent_directly(
    *,
    project_id: str,
    agent: str,
    message: str,
    conversation_id: str,
    work_dir: Optional[str] = None,
    session: AsyncSession,
    queue_entry_ids: Optional[List[str]] = None,
    turn_depth: Optional[int] = None,
    initiator: str = "operator",
    spec_document: Optional[str] = None,
    task_id: Optional[str] = None,
    divergence_source_run_id: Optional[str] = None,
    review_task_id: Optional[str] = None,
) -> TriggerAgentResponse:
    """Validate and spawn *agent* directly, returning its run identifier.

    The core of what `POST /agent/trigger` does (see that route below), factored out so a
    scheduled job (`scheduler.py`, task 3.10) goes through the exact same direct-execution
    path a manual trigger does — no synthetic `Message` for the watchdog to later detect and
    re-trigger, which is the same class of indirection Decision 2 already removed from the
    manual-trigger path in task 3.5. Raises `TriggerAgentError` on any rejection.
    """
    from sqlalchemy import select

    try:
        worktrees.validate_agent_name(agent)
    except ValueError as exc:
        raise TriggerAgentError(status.HTTP_400_BAD_REQUEST, str(exc), request_level=True) from exc

    conversation = await get_open_conversation(
        session,
        project_id=project_id,
        agent=agent,
        conversation_id=conversation_id,
    )
    if conversation is None:
        raise TriggerAgentError(status.HTTP_409_CONFLICT, "Conversation is unavailable")

    agent_row_result = await session.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == agent)
    )
    agent_row = agent_row_result.scalars().first()
    if agent_row is None:
        # Says the agent is absent, not that it lacks a runner (F33). The old wording sent the
        # operator to configure a roster entry that was never there — measured 2026-08-25, where a
        # job for a mistyped agent reported "has no runner bound" every five minutes. The
        # `runner_id is None` branch below is the case that message actually describes.
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            f"{agent} is not an agent in this project, so there is nothing to trigger. "
            f"Create it in the Hub UI, or correct the name — if a scheduled job names it, that "
            f"job will keep failing until the name is fixed.",
            request_level=True,
        )
    if agent_row.runner_id is None:
        config = await get_agent_config(project_id, agent, session)
        probe = probe_agent(agent, config)
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            probe["reason"] or f"{agent} is not currently launchable.",
            agent_wide=True,
        )
    if agent_row.lifecycle == "archived":
        # `agent-configuration`'s spec states "nothing runs an archived agent" as the reason a
        # blocked send need not open a new conversation as a workaround — that sentence is only
        # true if this is enforced here, the one choke point both a manual trigger and a queued
        # delivery (`turn_scheduler.py`) go through. Without it, an archived agent that was
        # queued or triggered directly before archiving (or by a caller that names it explicitly)
        # would still spawn a real run and inherit whatever authority its name carries — the
        # D15 gap `2026-08-19-a-loop-writes-its-own-queue`'s A5.3 documented as surviving the
        # literal name-reuse scenario a unique index already blocks.
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            f"{agent} is archived and cannot be triggered. Unarchive it first.",
            request_level=True,
        )
    runner_row = await session.get(Runner, agent_row.runner_id)
    if runner_row is None:
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            f"{agent}'s bound runner no longer exists.",
            agent_wide=True,
        )

    config = await get_agent_config(project_id, agent, session)
    # The bound Runner record is now the sole source of which CLI/model to launch —
    # legacy config-dict runner/model keys (from session-synced or self-registered
    # config) are superseded, not merged. See
    # openspec/changes/runner-agent-charter-separation/specs/runner-registry/spec.md.
    config["runner"] = runner_row.cli
    config["model"] = runner_row.model
    probe = probe_agent(agent, config)
    runner = probe["runner"]

    # Checked before launchability: whether we know how to spawn this runner at all is a
    # more fundamental, permanent gate than whether its CLI happens to be on PATH right
    # now, and keeps the response deterministic regardless of what's installed on the Hub
    # host (an unimplemented runner is still unimplemented even if its CLI is present).
    if runner not in SUPPORTED_RUNNERS:
        raise TriggerAgentError(
            status.HTTP_501_NOT_IMPLEMENTED,
            f"Direct spawn for runner {runner!r} is not implemented yet "
            f"(supported: {', '.join(SUPPORTED_RUNNERS)}). "
            "This runner has no Hub-owned execution adapter.",
            request_level=True,
        )

    if not probe["runnable"]:
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            probe["reason"] or f"{agent} is not currently launchable.",
            agent_wide=True,
        )

    existing = await session.execute(
        select(Run.id)
        .where(Run.project_id == project_id, Run.agent == agent, Run.status == "running")
        .limit(1)
    )
    if existing.scalar() is not None:
        raise TriggerAgentError(status.HTTP_409_CONFLICT, f"{agent} already has a run in progress.")

    # Resolution order (design.md): conversation.runtime_overrides -> runner.model / runner
    # defaults -> catalog control defaults. Overrides were already validated against the
    # catalog when the operator set them (`trigger_agent`'s /trigger handler), so they are
    # trusted here rather than re-validated per turn.
    conversation_overrides = dict(conversation.runtime_overrides or {})
    model = conversation_overrides.get("model") or config.get("model")
    control_overrides = {k: v for k, v in conversation_overrides.items() if k != "model"}
    # The agent's default posture sits between the conversation's own choice and the built-in
    # fallback. It has to be applied here rather than only in the composer, because a run
    # triggered by a peer message or a scheduled job has no composer to state one — and those are
    # exactly the runs where "what may this agent do unattended" is the question being asked.
    if agent_row.default_permission_mode and PERMISSION_MODE_CONTROL not in control_overrides:
        control_overrides[PERMISSION_MODE_CONTROL] = agent_row.default_permission_mode
    try:
        workspace_root = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            f"Project workspace is unavailable: {exc}",
            workspace_unavailable=True,
            directory_state=exc.directory_state,
        ) from exc
    repo_root = workspace_root.root

    # Which task this turn is about, answered before *anything* is provisioned for it (D2) —
    # before the review checkout, before the worktree, and before the turn context is rendered.
    #
    # Two problems, one answer. A builder triggered on a task could not find the document it was
    # implementing: the read tool documents its argument as "the path, as given in your turn
    # context", and a task-triggered context gave no path and no document id. Observed twice in one
    # run, in two conversations — the second time it blocked recording evidence entirely, and the
    # agents worked around it by messaging each other for the path. And a turn naming a task the
    # project does not have used to be refused only *after* its worktree was on disk, so a mistyped
    # id left a checkout and a branch behind for an agent that never ran.
    #
    # Below `resolve_project_workspace`, deliberately: an unavailable project directory is the more
    # actionable of two simultaneous truths, so it keeps its 409 and its `directory_state`. Above
    # every `work_dir` and review-turn refusal, equally deliberately: the task id is the more
    # specific statement, and it is what decides which workspace the turn would have had at all.
    # `hub/tests/test_task_resolved_before_workspace.py` pins all four of those answers.
    #
    # Reads only. The staging that acts on this stays where it is, below, before delivery.
    binding = await resolve_bound_task(
        session,
        project_id=project_id,
        conversation=conversation,
        queue_entry_ids=queue_entry_ids,
        task_id=task_id,
    )
    yolo = bool(config.get("yolo"))
    resume_session_id = conversation.provider_session_id
    session_mode = "resume" if resume_session_id else "new"
    env = resolve_agent_env(runner, config)

    # Task 5.1/5.2: a writing agent gets its own git worktree, isolated from every other
    # agent's (Decision 7). A custom work_dir cannot override that isolation. Read-only
    # agents may retain the existing project-relative work_dir behavior.
    #
    # Only where there *is* isolation to override. A project directory that is not a git
    # repository has none, so refusing there would be a guard with no subject.
    project_is_repo = worktrees.is_git_repo(repo_root)
    # A review turn's workspace is decided before anything else, because it replaces the ordinary
    # resolution rather than adjusting it (design D4: exactly one workspace per review turn).
    #
    # Read off the queue entries when the caller did not name one, exactly as `task_id` is: the
    # scheduler starts this turn from a later call than the one that queued the request, so an
    # argument alone would be gone by the time the turn exists.
    if not review_task_id:
        review_task_id = await _review_task_from_entries(session, queue_entry_ids)
    review_context = None
    if review_task_id:
        if work_dir:
            raise TriggerAgentError(
                status.HTTP_400_BAD_REQUEST,
                "work_dir cannot be combined with a review turn: a review turn's workspace is the "
                "checkout of the commit under review.",
                request_level=True,
            )
        # **Staffing the review, and every refusal it can raise, before the checkout exists.**
        #
        # Finding F76: this path provisioned the reviewer's detached checkout and staffed nothing,
        # so the reviewer did the work and then met four correct refusals with no exit between
        # them -- it could not move the task (still assigned to its author), record evidence, or
        # report. The flow path has staffed since F45; the same statement is called here, so one
        # operation stops having two behaviours.
        #
        # Before `prepare_review_turn`, not after (design D10): `run-task-binding` requires that a
        # request which is going to be refused leaves no workspace behind. Free to do here because
        # `apply_transition` neither commits nor flushes -- the staffing joins this dispatch's
        # transaction as pending state, so a refusal below (including `ReviewTurnRefused` from the
        # provisioning that now follows) abandons it and the task is never left staffed for a
        # review that did not happen.
        try:
            review_task = await resolve_task_for_project(session, review_task_id, project_id)
        except TaskBindingError as exc:
            raise TriggerAgentError(status.HTTP_409_CONFLICT, str(exc), request_level=True) from exc

        # Design D8, and the reason this guard is here rather than inside `enter_selected_task`:
        # that function writes the assignee *before* its status branch, and the branch has no
        # `else`. So staffing a task that is neither awaiting review nor already in review would
        # reassign it and travel no transition -- taking live work from the agent doing it and
        # moving it nowhere. The flow path cannot reach that (its ladder only selects reviewable
        # tasks), so a guard inside the shared function would sit where it could never fire. The
        # operator names a task id directly, and the only other check on this route asks whether
        # evidence names a commit, which is true of tasks that are still `in_progress`.
        if review_task.status not in (
            REVIEWABLE_LOOP_TASK_STATUSES + WITH_REVIEWER_LOOP_TASK_STATUSES
        ):
            raise TriggerAgentError(
                status.HTTP_409_CONFLICT,
                f"Task {review_task.id} is {review_task.status!r}, which is not a status a review "
                f"starts from. A review begins from work that is awaiting one. Staffing a reviewer "
                f"onto this task would take it from whoever holds it and move it nowhere.",
                request_level=True,
            )
        # Design D9. The `under_review` branch below is idempotent in its *status* but not in its
        # assignee, which is written unconditionally -- so dispatching a review for a task already
        # held by someone else would replace the holder and travel no transition, leaving a
        # handover this task's append-only history could not explain. Cannot fire on the flow path:
        # a flow writes its reviewer into `assignee` and commits before the turn is scheduled, so
        # the holder already is the dispatched reviewer by the time this runs.
        if (
            review_task.status in WITH_REVIEWER_LOOP_TASK_STATUSES
            and review_task.assignee
            and review_task.assignee != agent
        ):
            raise TriggerAgentError(
                status.HTTP_409_CONFLICT,
                f"Task {review_task.id} is already under review by {review_task.assignee!r}. "
                f"Reassign the task if {agent!r} should take it over, or let the review in flight "
                f"finish.",
                request_level=True,
            )
        try:
            await enter_selected_task(session, review_task, agent=agent, is_review=True)
        except TransitionRefusedError as exc:
            # The guard's own sentence, not a restatement of it: it already names both remedies and
            # the cost of doing nothing, and the operator meets the same words here as they would
            # attempting the transition directly. This is the case where the named reviewer is the
            # task's own author -- `enter_selected_task` writes the assignee first, so what
            # `_guard_reviewer_is_not_the_author` compares against is the reviewer being dispatched.
            raise TriggerAgentError(
                status.HTTP_403_FORBIDDEN, str(exc), request_level=True
            ) from exc

        try:
            review_context = await review_turn.prepare_review_turn(
                session,
                project_id=project_id,
                reviewer=agent,
                task_id=review_task_id,
                repo_root=repo_root,
            )
        except review_turn.ReviewTurnRefused as exc:
            # Task 3.4. The reason comes from the resolver unchanged, so the operator reads why
            # there is nothing to review rather than that something failed.
            raise TriggerAgentError(status.HTTP_409_CONFLICT, str(exc), request_level=True) from exc

    if work_dir and worktrees.is_writing_agent(config) and project_is_repo:
        raise TriggerAgentError(
            status.HTTP_400_BAD_REQUEST,
            "work_dir cannot override workspace isolation for a writing agent",
            request_level=True,
        )
    if work_dir:
        # Task 3.3: work_dir is resolved as a project-relative path, never an absolute
        # or escaping one — resolve_relative rejects traversal, absolute paths, control
        # characters, and symlink escapes in one place.
        try:
            effective_work_dir = str(workspace_root.resolve_relative(work_dir))
        except project_workspace.ProjectPathError as exc:
            raise TriggerAgentError(
                status.HTTP_400_BAD_REQUEST,
                f"Invalid work_dir: {exc}",
                request_level=True,
            ) from exc
        isolated_workspace: Optional[Path] = None
        # Not isolated, so the renderer never reads it; named on every branch so mypy sees one
        # type and a future branch cannot inherit a stale value from the one above it.
        workspace_branch: Optional[str] = None
    elif review_context is not None:
        # Task 3.1: the review checkout replaces `resolve_agent_workspace` outright. The agent's own
        # working worktree is not part of this turn, which is what makes the wrong directory
        # *outside the boundary* rather than merely the wrong choice.
        effective_work_dir = str(review_context.workspace)
        isolated_workspace = review_context.workspace
        # A review checkout is detached (`ensure_review_checkout`), so it is on no branch at all.
        # The renderer's review block says so in its own words and never reaches the branch
        # sentence, which is why this is `None` rather than the reviewer's own branch.
        workspace_branch = None
    else:
        # Which workspace this turn is about, not whose turn it is (design D3). A turn bound to a
        # task executes in that task's own checkout, so approving one task cannot merge another
        # task's commits along with it (F58); a turn bound to nothing gets the agent's own
        # workspace, exactly as before. `binding` was resolved above precisely so this line could
        # ask (D2), and the three values below are resolved in the Hub layer because `worktrees`
        # does not read the database.
        turn_workspace = await task_workspace.resolve_turn_workspace_inputs(
            session,
            project_id=project_id,
            repo_root=repo_root,
            task=binding.task,
        )
        # A task's checkout admits one writing turn at a time (design D8). This is the invariant
        # that used to follow for free from one-checkout-per-agent: the per-agent refusal at the
        # top of this function is per *agent*, `resolve_bound_task` never consults `Task.assignee`,
        # and `bind_run_to_task` fills `assignee` only when it is empty — so before this line an
        # operator starting task T on `builder-2` while `builder-1` was already running on it
        # handed two live processes the same working directory on the same branch.
        #
        # **Scoped by `takes_task_workspace`, not by a restatement of it.** D8 names three
        # exemptions — a review turn, a read-only agent, a grandfathered task — and each is a case
        # where refusing would forbid something that is safe today. All three are already answered
        # by *which workspace this turn gets*: a review turn never reaches this branch at all
        # (`review_context` pre-empts it above), and read-only, non-repository and grandfathered
        # turns share a checkout that two agents have always shared. Asking the resolver's own
        # predicate is what keeps the refusal and the isolation from drifting apart.
        #
        # Below `resolve_turn_workspace_inputs` because that call is the grandfathering read and
        # reads only; above `resolve_turn_workspace` because that call is the first thing that
        # *provisions*. Nothing is on disk when this refuses.
        if worktrees.takes_task_workspace(repo_root, config, turn_workspace.task_id):
            holder = (await tasks_held_by_a_running_turn(session, project_id)).get(
                turn_workspace.task_id
            )
            if holder is not None and holder != agent:
                raise TriggerAgentError(
                    status.HTTP_409_CONFLICT,
                    f"{holder} is already running a turn on task {turn_workspace.task_id}; "
                    f"a task's checkout takes one writing turn at a time.",
                    # It clears when that turn ends, so the queue entry waits rather than counting
                    # a delivery attempt towards abandonment (design D8, and `turn_scheduler`).
                    transient=True,
                )

        try:
            workspace = worktrees.resolve_turn_workspace(
                repo_root,
                agent,
                config,
                task_id=turn_workspace.task_id,
                base=turn_workspace.base,
                prerequisites=turn_workspace.prerequisites,
            )
        except (worktrees.GitCommandError, worktrees.IsolationUnavailableError) as exc:
            raise TriggerAgentError(
                status.HTTP_409_CONFLICT,
                f"Could not prepare isolated worktree for {agent}: {exc}",
            ) from exc
        effective_work_dir = str(workspace)
        isolated_workspace = workspace if workspace != repo_root else None
        # Task 6.5. Same argument as `effective_work_dir` above: computed here, from the same
        # inputs `resolve_turn_workspace` was just given, so the sentence the agent reads cannot
        # disagree with the branch its process is standing on.
        workspace_branch = worktrees.turn_branch_name(
            repo_root, agent, config, task_id=turn_workspace.task_id
        )

    # Build context from current Hub-owned state for every turn. Runners consume a file,
    # so materialize the canonical response inside the effective workspace immediately
    # before command construction; an edited charter is therefore visible on the next run.
    from .agents import _get_session_data, _render_hub_agent_context

    # `binding` was resolved above, before any workspace was provisioned (D2).
    task_document = await spec_document_for_task(session, binding.task)

    session_data = await _get_session_data(project_id, session)
    rendered_context = await _render_hub_agent_context(
        agent=agent,
        project_id=project_id,
        db=session,
        session_data=session_data,
        agent_row=agent_row,
        # The directory the run will actually execute in. Passed rather than recomputed so the
        # text an agent reads cannot disagree with the process's own cwd — agents were resolving
        # paths against the project root while running in a worktree, and every such read and
        # write was refused.
        work_dir=effective_work_dir,
        isolated=isolated_workspace is not None,
        workspace_branch=workspace_branch,
        # A writing agent working in the project directory is doing so because there is no
        # repository to cut a worktree from — the only remaining path through
        # `resolve_agent_workspace`. Told apart from a read-only agent sharing by choice,
        # because an agent that does not know there is no repository proposes branches,
        # offers to commit, and reads a failed `git status` as a broken environment.
        isolation_unavailable=worktrees.is_writing_agent(config) and not project_is_repo,
        # Which specification document the operator has open, when the message came from the
        # specification workspace. Deliberately here and not prepended to `message`: the message
        # is the durable record of what the operator said, and re-reading the conversation later
        # must not show them saying something they did not.
        spec_document=spec_document,
        # The document the bound task implements, which is a different claim from the one above:
        # that one is where the operator happens to be looking, this one is what the work is
        # against. Rendered as its own block for exactly that reason.
        task_spec_document=task_document,
        task_id=binding.task.id if binding.task is not None else None,
        # The other half of design D4: the boundary above enforces *where*, this states *what*.
        # A reviewer that is not told it is reviewing will helpfully fix the bug itself and report
        # the work as verified.
        review=review_context,
    )
    context_file = Path(effective_work_dir) / ".agentweave" / "context" / f"{agent}.md"
    try:
        context_file.parent.mkdir(parents=True, exist_ok=True)
        context_file.write_text(rendered_context["context"], encoding="utf-8")
    except OSError as exc:
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            f"Could not materialize canonical context for {agent}: {exc}",
        ) from exc

    # Task 4.5: tell the agent, at turn start, which access path is in use — never offer
    # one that isn't actually available in this environment.
    access_path = resolve_access_path(runner, probe["cli"] or agent, config.get("hub_client"))
    notices = [access_path_notice(access_path)]
    # F52: told once, up front, rather than discovered turn after turn by an agent that treats a
    # refused git command as work lost. `review_context is None` matches the condition `worktree`
    # is computed under below (a review checkout is read-only and never snapshotted); an agent with
    # no worktree at all (`isolated_workspace is None`) has nothing this notice would help with.
    if isolated_workspace is not None and review_context is None:
        notices.append(auto_snapshot_notice())
    # A specification turn says so beside the operator's message, not only in the system context.
    # Three live runs had the phase block, the precedence statement and the tool list all correctly
    # delivered, and reached for a different workflow anyway: what an agent weighs against the
    # request is what arrives with the request. Prepended rather than merged into `message`, which
    # stays the durable record of what the operator actually said — the same division
    # `access_path_notice` has always used.
    spec_phase, spec_is_unwritten = await _spec_phase_for(session, project_id, spec_document)
    spec_notice = spec_turn_notice(spec_phase, path=spec_document, is_unwritten=spec_is_unwritten)
    if spec_notice:
        notices.append(spec_notice)
    prompt = "\n\n".join([*notices, message])
    mcp_command = None
    if access_path == "mcp":
        canonical_server = Path(__file__).resolve().parents[2] / "mcp_server.py"
        mcp_command = [sys.executable, str(canonical_server)]

    # Codex uses the app-server transport unless the runner explicitly opts out; see
    # `uses_app_server`. Both transport sentinels are stripped before `flags` reaches
    # `build_command` — neither is a real `codex exec` argument, and either would otherwise
    # leak into that argv unchanged.
    runner_flags = list(runner_row.flags or [])
    use_codex_app_server = uses_app_server(runner, runner_flags)
    runner_flags = [f for f in runner_flags if f not in TRANSPORT_SENTINELS]

    try:
        cmd = build_command(
            runner=runner,
            cli=probe["cli"],
            prompt=prompt,
            model=model,
            context_file=context_file,
            session_id=resume_session_id,
            yolo=yolo,
            mcp_command=mcp_command,
            extra_flags=runner_flags,
            # F4 (`openspec/changes/2026-08-17-authoring-rigor-and-scope`, design D6): a turn
            # triggered with a specification document open loses file-write tools, mechanically,
            # regardless of phase, rigor or permission posture — a role boundary, not a rigor gate.
            restrict_spec_writes=bool(spec_document),
            control_overrides=control_overrides,
        )
    except UnsupportedRunnerError as exc:
        raise TriggerAgentError(
            status.HTTP_501_NOT_IMPLEMENTED, str(exc), request_level=True
        ) from exc

    run_id = f"run-{short_id()}"
    run_token = mint_run_token()

    # Task 4.1: identity is established here, once, by the Hub — never asserted by the
    # agent itself. Every tool call this run makes reads AW_AGENT_IDENTITY from its own
    # process environment; no tool accepts a caller-supplied identity. `env=None` meant
    # "inherit the Hub's own environment unchanged" (resolve_agent_env's contract) — that
    # base must be preserved, not replaced, when adding these two keys.
    env = dict(env) if env is not None else dict(os.environ)
    env["AW_AGENT_IDENTITY"] = agent
    env["AW_RUN_ID"] = run_id
    env["AW_RUN_TOKEN"] = run_token
    # The boundary the "Workspace only" posture enforces. Deliberately the same
    # `effective_work_dir` passed to the context renderer above as "Your workspace": the boundary
    # the agent is *told* about and the one that is *enforced* must come from one value, or an
    # agent can be refused at a line it was never shown.
    env["AW_WORKSPACE_DIR"] = effective_work_dir
    # Which approver posture this run is under. The approval tool serves both, and only this
    # tells it whether to decide against the workspace itself or put the call to the operator.
    if (control_overrides or {}).get("permission_mode") == "manual":
        env["AW_PERMISSION_POSTURE"] = OPERATOR_POSTURE
    # How long this agent waits on the operator. Set only when configured — an absent variable is
    # what tells the tool to use its own default, so writing one unconditionally would turn every
    # agent into a configured one and freeze today's numbers.
    if agent_row.permission_timeout_seconds is not None:
        env["AW_DECISION_TIMEOUT"] = str(agent_row.permission_timeout_seconds)
    if agent_row.question_timeout_seconds is not None:
        env["AW_QUESTION_TIMEOUT"] = str(agent_row.question_timeout_seconds)
    if turn_depth is not None:
        env["AW_TURN_DEPTH"] = str(turn_depth)
    explicit_hub_url = os.environ.get("HUB_URL")
    if explicit_hub_url:
        env["HUB_URL"] = explicit_hub_url
    else:
        observed = bound_address.get()
        if observed is None:
            raise TriggerAgentError(
                status.HTTP_409_CONFLICT,
                "Cannot determine the Hub's own address for this run: no HUB_URL is set "
                "in the Hub's environment and no bound address has been observed from an "
                "incoming connection yet. Set HUB_URL explicitly, or retry once the Hub "
                "has served at least one request.",
                # The refusal's own last sentence is the classification: it clears the moment a
                # request arrives. Left terminal, `schedule_agent` counted a delivery attempt for
                # every agent the startup re-drain touched — and that re-drain runs in `lifespan`,
                # before any request has been served, so it could not have succeeded. Three
                # restarts with a run in flight and the operator's message was withdrawn with
                # "the Hub stopped retrying", for a condition that had already stopped.
                transient=True,
            )
        # The agent is always spawned as a local subprocess of the Hub (native mode);
        # only the observed *port* corrects the defect (settings.aw_port can silently
        # diverge from where uvicorn actually bound). The host is always loopback.
        _, observed_port = observed
        env["HUB_URL"] = f"http://127.0.0.1:{observed_port}"
    # A parent service environment may contain operator credentials. Never pass them
    # through to a spawned run: AW_RUN_TOKEN is the run's complete authority.
    env.pop("HUB_API_KEY", None)
    env.pop("HUB_PROJECT_ID", None)
    # The same principle covers the Hub's own service configuration, which is not run
    # authority either. DATABASE_URL is the sharpest case: `_hub_native_start` exports it
    # into the Hub's environment (cli.py), so without this every spawned agent inherits a
    # writable handle to the operator's live database — and `pytest hub/tests/`, the command
    # this repository's own instructions tell an agent to run, has fixtures that drop every
    # table in whatever DATABASE_URL names. AW_BOOTSTRAP_API_KEY is the instance operator
    # credential and AW_TICKET_SECRET signs SSE tickets; an agent holding either can act as
    # the operator rather than as its run.
    env.pop("DATABASE_URL", None)
    env.pop("AW_BOOTSTRAP_API_KEY", None)
    env.pop("AW_TICKET_SECRET", None)

    run = Run(
        id=run_id,
        project_id=project_id,
        agent=agent,
        session_id=resume_session_id,
        conversation_id=conversation.id,
        status="running",
        turn_depth=turn_depth,
        initiator=initiator,
        capability_token_hash=hash_run_token(run_token),
        instance_id=instance_identity.get(),
        divergence_source_run_id=divergence_source_run_id,
        # Design D7. The same value the process is given as its cwd, so the record and the
        # process cannot disagree — the argument `workspace_branch` above is made for, applied to
        # the directory rather than the branch. Written here rather than at either runner's
        # finalisation because the Claude/Codex split happens later and *inside* `_execute_run`,
        # so there is one write and no way for the two spawn paths to differ.
        workspace_dir=effective_work_dir,
    )

    # The binding, and the automatic move it causes, are staged here — before delivery, which is
    # what commits — so a bound run whose task never moved cannot exist as a partial write.
    #
    # *Which* task it is was resolved further up, before the context was rendered, because the
    # context has to be able to name the specification the work implements. That resolution reads
    # only, and nothing below feeds back into it.
    bound_task, task_was_named, delegated_source_run_id = binding
    if delegated_source_run_id is not None:
        # Carried from the queue entry rather than passed in: the Hub queued this response in an
        # earlier call, and the retry bound cannot see its own source unless the entry brings it.
        run.divergence_source_run_id = delegated_source_run_id
        # The divergence record could not name its response when it was written — the answer was
        # queued, and only becomes a run here, whenever the agent was next free.
        await record_response_run(session, delegated_source_run_id, run.id)

    if task_was_named and bound_task is not None:
        # This turn named a task, so the thread follows it. The more specific statement wins, and
        # the operator does not have to release an old binding before starting something else here.
        rebind_conversation(conversation, bound_task)

    if bound_task is not None:
        await bind_run_to_task(session, run, bound_task)

    delivered = []
    if queue_entry_ids:
        delivered = await deliver_entries_with_run(
            session,
            project_id=project_id,
            agent=agent,
            entry_ids=queue_entry_ids,
            run=run,
        )
    else:
        session.add(run)
        await session.commit()

    # Register execution immediately after the atomic Run + delivery commit. Event rows are
    # observability; a transient failure while writing one must never strand a running Run
    # whose queue entries are already marked delivered but which has no process task.
    task = asyncio.create_task(
        _execute_run(
            project_id=project_id,
            agent=agent,
            run_id=run_id,
            conversation_id=conversation.id,
            runner=runner,
            cmd=cmd,
            model=model,
            work_dir=effective_work_dir,
            known_session_id=resume_session_id,
            env=env,
            # A **review** turn passes None, deliberately. `_execute_run` snapshots this directory
            # when the turn ends, and a reviewer is not an author: there is nothing of its to
            # preserve, and committing on a detached HEAD moves the checkout off the very commit
            # the review was about. Observed live on 2026-08-24 — `critic` reviewed `90aa643` and
            # the checkout ended at `886124f`, an orphan commit of three `.pyc` files that running
            # the tests had touched.
            worktree=None if review_context is not None else isolated_workspace,
            use_codex_app_server=use_codex_app_server,
            cli=probe["cli"],
            prompt=prompt,
            yolo=yolo,
            mcp_command=mcp_command,
            permission_mode=(control_overrides or {}).get("permission_mode"),
            # Config-style controls (Codex's Effort) render to `-c KEY=VALUE` in `cmd`, and `cmd`
            # is unused on the app-server transport — so they reached nothing there until this was
            # passed separately (F99). Rendered from the same catalog declaration `build_command`
            # renders above; the app-server path merges it into `thread/start`'s `config`.
            config_overrides=(
                render_control_config(catalog_provider_for_runner(runner) or "", control_overrides)
                if control_overrides
                else {}
            ),
        )
    )
    _background_runs.add(task)
    task.add_done_callback(_background_runs.discard)

    try:
        await persist_event(
            session,
            project_id,
            "run_triggered",
            {
                "agent": agent,
                "run_id": run_id,
                "conversation_id": conversation.id,
                "session_mode": session_mode,
                "initiator": initiator,
            },
            agent=agent,
        )
        for entry in delivered:
            payload = {
                "entry_id": entry.id,
                "agent": agent,
                "run_id": run_id,
                "conversation_id": conversation.id,
                "hop_depth": entry.hop_depth,
            }
            await persist_event(session, project_id, "queue_entry_delivered", payload, agent=agent)
            await sse_manager.broadcast(project_id, "queue_entry_delivered", payload)
    except Exception:
        logger.exception(
            "Run %s started but its trigger/delivery events could not be persisted", run_id
        )

    return TriggerAgentResponse(
        success=True,
        message=f"{agent} started (run {run_id}).",
        agent=agent,
        run_id=run_id,
        status="running",
        conversation_id=conversation.id,
        provider_session_id=resume_session_id,
        session_id=resume_session_id,
    )


@router.post("/trigger", response_model=TriggerAgentResponse)
async def trigger_agent(
    body: TriggerAgentRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Append input to an AgentWeave conversation and schedule it when possible."""
    from sqlalchemy import select

    project_id, _ = project
    try:
        worktrees.validate_agent_name(body.agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.session_mode is not None and body.session_mode not in ("new", "resume"):
        raise HTTPException(status_code=400, detail="session_mode must be 'new' or 'resume'")
    if body.session_mode == "resume" and not body.session_id:
        raise HTTPException(
            status_code=400, detail="session_id is required when session_mode='resume'"
        )

    # Mirrors the same guard in `trigger_agent_directly` — see its comment for why this is the
    # one invariant that makes "nothing runs an archived agent" true rather than aspirational.
    archived_check = await session.execute(
        select(Agent.lifecycle).where(Agent.project_id == project_id, Agent.name == body.agent)
    )
    if archived_check.scalars().first() == "archived":
        raise HTTPException(
            status_code=409,
            detail=f"{body.agent} is archived and cannot be triggered. Unarchive it first.",
        )

    try:
        workspace_root = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        project_workspace.raise_workspace_http_error(exc)

    config = await get_agent_config(project_id, body.agent, session)
    # Mirrors the same guard in `trigger_agent_directly`, including its repository condition:
    # there is no isolation to override in a project that is not a git repository.
    if (
        body.work_dir
        and worktrees.is_writing_agent(config)
        and worktrees.is_git_repo(workspace_root.root)
    ):
        raise HTTPException(
            status_code=400,
            detail="work_dir cannot override workspace isolation for a writing agent",
        )
    if body.work_dir:
        try:
            workspace_root.resolve_relative(body.work_dir)
        except project_workspace.ProjectPathError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid work_dir: {exc}") from exc

    conversation: Optional[Conversation] = None
    if body.conversation_id is not None:
        conversation = await get_open_conversation(
            session,
            project_id=project_id,
            agent=body.agent,
            conversation_id=body.conversation_id,
        )
        if conversation is None:
            raise HTTPException(status_code=409, detail="Conversation is unavailable")
    elif body.session_mode == "resume" and body.session_id:
        conversation = await conversation_for_provider_session(
            session,
            project_id=project_id,
            agent=body.agent,
            provider_session_id=body.session_id,
        )
        if conversation is None:
            conversation = new_conversation(
                project_id=project_id, agent=body.agent, origin="operator"
            )
            conversation.provider_session_id = body.session_id
            session.add(conversation)
    else:
        # This route queues its entry as `origin_type="operator"` below; the conversation it
        # opens is the same act.
        # No inheritance here, deliberately. `agent-conversation-workspace` requires that a
        # conversation the *operator* starts begins clean — they are looking at the composer and
        # can choose. What this change fixes is the conversation a peer or a job opens, where
        # nobody was asked.
        conversation = new_conversation(project_id=project_id, agent=body.agent, origin="operator")
        session.add(conversation)

    if body.task_id:
        # Refused now, while the operator is looking at the response, rather than at spawn — a
        # request that names a task the project does not have is a mistake, not a reason to start
        # an unbound run whose boundary is then never checked.
        named_task = await resolve_task_for_project(session, body.task_id, project_id)
        # And one refusal more, for the same reason (F79). A task the operator has already approved
        # or rejected takes no new work: `resolve_bound_task` drops the binding when it meets one,
        # so without this the request would be answered `200` and the run would start silently
        # ignoring the task it was asked about — the same shape as F78, where following the
        # product's own instruction returned success and changed nothing.
        #
        # **Here rather than in `resolve_bound_task`.** This route does not run the turn; it queues
        # an entry, and the task reaches `resolve_bound_task` as a *delegation*, where dropping the
        # binding is the right disposition and refusing is not (see that function). The explicit
        # branch there is reached only by a caller passing `task_id` to `trigger_agent_directly`,
        # and its one caller never does — a guard placed there would be tested, correct, and unable
        # to fire.
        decided = decided_task_refusal(named_task)
        if decided is not None:
            raise HTTPException(status_code=409, detail=decided)

    if body.review_task_id:
        # Same reasoning, and one refusal more: a task with no evidence naming a commit cannot be
        # reviewed at all, and the operator should learn that here rather than by watching a run
        # start and immediately fail.
        review_target = await resolve_task_for_project(session, body.review_task_id, project_id)
        target = await requirement_evidence.commit_for_task_review(session, body.review_task_id)
        if not target.resolved:
            raise HTTPException(status_code=409, detail=target.refusal)
        # The same three questions `trigger_agent_directly` asks before it staffs the review,
        # asked again here so the operator gets an answer instead of an acknowledgement.
        #
        # **Found by driving it** (design D11). The dispatch-time refusals are correct and the
        # task is left untouched, but `turn_scheduler` catches `TriggerAgentError` and records it
        # as the entry's `waiting_reason`, so `POST /agent/trigger` answered
        # `200 {"success": true, "status": "queued"}` with the refusal's own sentence buried in a
        # field named for something else. An operator who asks for a review that can never happen
        # is told it succeeded. Duplicated rather than moved: the flow path reaches
        # `trigger_agent_directly` without passing through this route, so the checks below are the
        # operator's answer and the ones there remain the authority.
        refusal = await review_dispatch_refusal(session, review_target, reviewer=body.agent)
        if refusal is not None:
            raise HTTPException(status_code=refusal[0], detail=refusal[1])

    if body.overrides:
        agent_row_result = await session.execute(
            select(Agent).where(Agent.project_id == project_id, Agent.name == body.agent)
        )
        agent_row = agent_row_result.scalars().first()
        if agent_row is None or agent_row.runner_id is None:
            raise HTTPException(
                status_code=409, detail=f"{body.agent} has no runner bound; cannot set overrides."
            )
        runner_row = await session.get(Runner, agent_row.runner_id)
        if runner_row is None:
            raise HTTPException(
                status_code=409, detail=f"{body.agent}'s bound runner no longer exists."
            )
        accepted, rejection = validate_overrides(runner_row.cli, body.overrides)
        if rejection is not None:
            raise HTTPException(status_code=400, detail=rejection.reason)
        # Overrides are stored per conversation, not per agent — the runner binding
        # this validated against is unchanged (design.md: "Rejected: overrides on the
        # agent").
        conversation.runtime_overrides = accepted

    entry = new_entry(
        project_id=project_id,
        agent=body.agent,
        origin_type="operator",
        content=body.message,
        hop_depth=0,
        session_mode=body.session_mode,
        session_id=body.session_id,
        conversation_id=conversation.id,
        work_dir=body.work_dir,
        spec_document=body.spec_document,
        # Carried on the entry rather than held for the spawn, so an operator starting work from a
        # board card binds through the same path a delegation does. The scheduler may start this
        # agent's turn from a later call than this one, and anything held only here would be gone.
        task_id=body.task_id,
        review_task_id=body.review_task_id,
    )
    session.add(entry)
    conversation.updated_at = entry.arrived_at
    name_conversation(conversation, body.message)
    await session.commit()
    payload = {
        "entry_id": entry.id,
        "agent": body.agent,
        "conversation_id": conversation.id,
        "origin_type": "operator",
        "hop_depth": 0,
    }
    await persist_event(session, project_id, "queue_entry_queued", payload, agent=body.agent)
    await sse_manager.broadcast(project_id, "queue_entry_queued", payload)

    from ...turn_scheduler import schedule_agent

    scheduled = await schedule_agent(project_id, body.agent)
    # The scheduler picks the conversation of the *oldest* eligible entry across this
    # agent's whole queue, which is not necessarily the conversation this request just
    # appended to (spec `agent-conversation-workspace`: "Different conversations never
    # share one provider turn"). When it picked a different one, this caller's input is
    # still queued: report that, and this request's own conversation, rather than another
    # conversation's run — the response must always describe the input it accepted (same
    # spec: "the response contains the new conversation_id whether its status is running
    # or queued").
    if scheduled.response is not None and scheduled.response.conversation_id == conversation.id:
        response = scheduled.response
        response.queue_entry_id = entry.id
        return response
    refusal = scheduled.refusal
    if refusal is not None and entry.id in refusal.entry_ids:
        # F108: this request asked for something the Hub will never do, and until now it was told
        # `200 {"success": true, "status": "queued"}` with the refusal's own sentence delivered in
        # a field named for waiting. The refusal carries its own status because the Hub has already
        # distinguished these correctly — 403 for reviewing your own work, 409 for a target in the
        # wrong state — and flattening them here would discard that.
        #
        # Only when the refusal names *this* entry. `schedule_agent` builds its turn from the
        # oldest eligible entry across the whole queue, so the refusal frequently belongs to
        # another conversation; answering it to whoever happened to arrive would report a refusal
        # about input this caller never submitted and cannot act on.
        if await withdraw_refused_entry(session, project_id, entry.id, refusal.detail):
            # The queue has to agree with the answer, and the operator has to be told it does.
            # `queue_entry_queued` was already broadcast a few lines above, so a silent withdrawal
            # leaves them holding an error *and* a queue card still counting the input — the same
            # disagreement this whole change removes, moved one surface over (design D12).
            #
            # `queue_entry_withdrawn`, not `queue_entry_abandoned`: that one means the Hub gave up
            # after trying, carries an attempt count and a run id, and gets its own operator-facing
            # treatment. Nothing was ever tried here and nobody gave up — the request was answered.
            withdrawn_payload = {"entry_id": entry.id, "agent": body.agent}
            await persist_event(
                session,
                project_id,
                "queue_entry_withdrawn",
                withdrawn_payload,
                agent=body.agent,
            )
            await sse_manager.broadcast(project_id, "queue_entry_withdrawn", withdrawn_payload)
        raise HTTPException(status_code=refusal.status_code, detail=refusal.detail)
    waiting_reason = scheduled.waiting_reason
    if scheduled.response is not None:
        waiting_reason = (
            "an older conversation's queued input is being delivered first "
            f"(run {scheduled.response.run_id})"
        )
    elif refusal is not None:
        # A refusal that names other entries describes a conversation this caller did not ask
        # about, cannot act on, and may not be entitled to read. Say what is true of *this* input
        # instead — the same treatment the success path above already gives the same mismatch.
        #
        # Only reachable for a request-level refusal, and that is why this branch is safe. An
        # environment-level one produces no `refusal` at all and keeps stating its own sentence
        # here, which is right: "no runner is bound to this agent" is true of the agent, not of
        # one conversation, so every caller waiting on that agent needs to read it.
        waiting_reason = "queued behind other input for this agent"
    return TriggerAgentResponse(
        success=True,
        message=f"Input queued for {body.agent}.",
        agent=body.agent,
        status="queued",
        conversation_id=conversation.id,
        provider_session_id=conversation.provider_session_id,
        session_id=conversation.provider_session_id,
        queue_entry_id=entry.id,
        waiting_reason=waiting_reason,
    )


class StopAgentResponse(BaseModel):
    success: bool
    message: str
    agent: str
    run_id: str
    status: str


@router.post("/{agent}/stop", response_model=StopAgentResponse)
async def stop_agent_run(
    agent: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Interrupt the agent's in-progress direct-spawn run, if any.

    Force-terminates the owned PTY process. `_execute_run`'s own read/wait loop observes
    the exit and does the actual status/broadcast bookkeeping (see `_stop_requested` above)
    — this endpoint only signals intent and terminates the process, it does not itself mark
    the Run row, since that must happen only after the process has actually exited.
    """
    from sqlalchemy import select

    project_id, _ = project

    result = await session.execute(
        select(Run)
        .where(Run.project_id == project_id, Run.agent == agent, Run.status == "running")
        .order_by(Run.started_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{agent} has no run in progress.",
        )

    pty = run_liveness.active_ptys.get(run.id)
    if pty is not None:
        _stop_requested.add(run.id)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: pty.terminate(force=True))
    elif run.id in run_liveness.active_app_server_runs:
        # No process handle to terminate directly (codex_appserver.run_turn owns the
        # subprocess internally) — `_stop_requested` is itself the signal: `run_turn`'s
        # `should_interrupt` polls this same set and sends `turn/interrupt` within one poll
        # interval (task 2.7).
        _stop_requested.add(run.id)
    else:
        # Spawned but not yet registered, or already past its read/wait loop — either way
        # there's nothing left to terminate; the run's own completion handling will settle
        # its final status shortly.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{agent}'s run is not in a stoppable state right now.",
        )

    return StopAgentResponse(
        success=True,
        message=f"Stop signal sent to {agent} (run {run.id}).",
        agent=agent,
        run_id=run.id,
        status="stopping",
    )


async def terminate_all_active_runs() -> int:
    """Terminate every currently-tracked run's process tree (task 3.9: a clean Hub
    shutdown must not leave an agent process, or anything it spawned, orphaned).

    Called from `main.py`'s `lifespan()` teardown. Deliberately does not touch any `Run`
    row's DB status — a shutdown-then-restart is picked up by `run_reconciliation.py`'s
    `reconcile_interrupted_runs()` on the next boot (task 3.8), which is the single place
    that owns transitioning a run's persisted status; duplicating that here risks the two
    disagreeing about *when* a run's status actually changes.

    An app-server run has no process handle here to kill directly — the same
    `_stop_requested` signal `stop_agent_run` uses is the only lever available, so this is
    best-effort within `run_turn`'s poll interval, not an immediate kill like the PTY/pipe
    case. `run_turn`'s own `finally` still closes its subprocess once its loop notices.

    Returns the number of runs terminated or signalled to stop.
    """
    loop = asyncio.get_running_loop()
    ptys = list(run_liveness.active_ptys.values())
    for pty in ptys:
        await loop.run_in_executor(None, lambda p=pty: terminate_process_tree(p.pid, force=True))
    app_server_run_ids = list(run_liveness.active_app_server_runs)
    _stop_requested.update(app_server_run_ids)
    return len(ptys) + len(app_server_run_ids)


async def _restamp_evidence_footprints(
    db: AsyncSession,
    *,
    project_id: str,
    run_id: str,
    worktree: Optional[Path],
    snapshot_sha: Optional[str],
) -> None:
    """Point this run's evidence at the commit that contains its work.

    Evidence is recorded mid-turn, while the work is still uncommitted, so it can only name the
    commit the turn started from. `snapshot_worktree` has just made the commit that actually holds
    the work, and this is the first moment the right answer is knowable.

    Best-effort, and for the same reason the snapshot above it is: a git failure here must not turn
    a finished run into a failed one. A run that never reaches this point keeps the stale footprint,
    which is the pre-existing behaviour rather than a new one.
    """
    if worktree is None:
        return
    try:
        project = await db.get(Project, project_id)
        await requirement_evidence.restamp_run_footprints(
            db,
            project_id=project_id,
            run_id=run_id,
            root=worktree,
            commit_sha=snapshot_sha,
            main_branch=project.main_branch if project else None,
        )
    except Exception:  # noqa: BLE001 - never worsen a run's outcome over a footprint
        logger.warning("Could not re-stamp evidence footprints for run %s", run_id, exc_info=True)


async def _report_abandoned_entries(
    db: AsyncSession, project_id: str, agent: str, run_id: str
) -> None:
    """Tell the operator about input the Hub has stopped trying to deliver.

    Retrying without limit is indistinguishable from being stuck, so the Hub eventually gives up —
    but a message dropped silently is worse than one dropped loudly. Emitted at `warn`, because
    something the operator or another agent said is not going to be acted on.
    """
    abandoned = await abandoned_for_run(db, run_id)
    for entry in abandoned:
        payload = {
            "entry_id": entry.id,
            "agent": agent,
            "run_id": run_id,
            "attempts": entry.delivery_attempts,
            "reason": entry.abandoned_reason,
            "conversation_id": entry.conversation_id,
        }
        await persist_event(
            db, project_id, "queue_entry_abandoned", payload, agent=agent, severity="warn"
        )
        await sse_manager.broadcast(project_id, "queue_entry_abandoned", payload)


def _transport_failure_fields(exc: BaseException, conversation_id: Optional[str]) -> dict:
    """What a run that never got going can say about why.

    The normal-completion broadcast carries `exit_code`/`conversation_id`; this path carried only
    a string, so the two shapes disagreed exactly where diagnosis is hardest. `getattr` because
    this `except` also catches `FileNotFoundError`/`OSError`/`TimeoutError`, which carry none of
    these — an absent fact is reported as absent rather than invented.
    """
    return {
        "error": str(exc),
        # Rendered, not raw — this dict is broadcast for display. See `_runtime_failure_fields`.
        "exit_code": readable_exit_code(getattr(exc, "exit_code", None)),
        "method": getattr(exc, "method", None),
        # Absent until 2026-08-14, so the tail could only surface by having been composed into
        # `str(exc)`. Of the three facts this dict was written to report — exit code, method,
        # stderr tail — only the first two were ever in it.
        "stderr_tail": getattr(exc, "stderr_tail", None) or None,
        "conversation_id": conversation_id,
    }


def _runtime_failure_fields(outcome, lifecycle_event: str) -> dict:
    """What the app-server itself did, for a turn that failed without raising.

    The pre-spawn path reports this through `_transport_failure_fields`, off an `AppServerError`.
    A turn that fails once it is under way has no exception at all — `run_turn` returns a failed
    `TurnOutcome` — so these facts have to be lifted off the outcome instead. Until they were, a
    killed app-server produced a `run_failed` carrying only the synthetic exit code.

    Only on a failure, and only for facts that exist: a completed run has nothing to explain, and
    a key that is present but null invites a reader to render "exit: null".

    The status is **rendered**, not raw. Measured 2026-08-15 against a live Hub: this payload went
    out as `runtime_exit_code: 4294967295` while `run.error` for the same run said `exit -1`, so one
    death was described by three numbers. D3 put normalisation "where the value is composed for a
    human" and kept recorded values raw — a broadcast payload is the former, not the latter, and
    reading it as the latter is what produced the defect. `TurnOutcome.exit_code` and
    `AppServerError.exit_code` still hold what the platform reported; every surface a person reads
    now renders it.
    """
    if lifecycle_event != "run_failed":
        return {}
    fields = {}
    if getattr(outcome, "exit_code", None) is not None:
        fields["runtime_exit_code"] = readable_exit_code(outcome.exit_code)
    if getattr(outcome, "stderr_tail", None):
        fields["stderr_tail"] = outcome.stderr_tail
    return fields


_RUN_LIFECYCLE_EVENTS = ("run_started", "run_completed", "run_failed", "run_stopped")


async def _broadcast_run_lifecycle(
    db: AsyncSession,
    project_id: str,
    event_type: str,
    *,
    agent: str,
    run_id: str,
    **fields,
) -> None:
    """Persist + SSE-broadcast one of the typed run-lifecycle events.

    A distinct, named event per phase (rather than folding everything into the
    generic `agent_output` stream) is what lets the UI render "run started" /
    "run failed" as first-class states instead of grepping status text out of
    output lines — see design.md's Typed activity stream section.
    """
    assert event_type in _RUN_LIFECYCLE_EVENTS
    payload = {"agent": agent, "run_id": run_id, **fields}
    # L9-1's rule — "a broadcast payload is a display surface" — applied here rather than at each
    # caller, which is how the pty path came to miss it: `_transport_failure_fields` and
    # `_runtime_failure_fields` render, and the Claude path passes `exit_code=exit_code` straight
    # from the process. Killing an agent then told the operator `Run failed (exit 4294967295)`,
    # which is the exact sentence loop 8 filed. `readable_exit_code` is idempotent, so the two
    # callers that already render are unaffected. `Run.exit_code` in the database stays raw (D3).
    for key in ("exit_code", "runtime_exit_code"):
        if key in payload:
            payload[key] = readable_exit_code(payload[key])
    await persist_event(
        db,
        project_id,
        event_type,
        payload,
        agent=agent,
        severity="warn" if event_type == "run_failed" else "info",
    )
    await sse_manager.broadcast(project_id, event_type, payload)


async def _execute_run(
    *,
    project_id: str,
    agent: str,
    run_id: str,
    conversation_id: str,
    runner: str,
    cmd: list,
    model: Optional[str],
    work_dir: Optional[str],
    known_session_id: Optional[str],
    env: Optional[Dict[str, str]] = None,
    worktree: Optional[Path] = None,
    use_codex_app_server: bool = False,
    cli: Optional[str] = None,
    prompt: Optional[str] = None,
    yolo: bool = False,
    mcp_command: Optional[List[str]] = None,
    permission_mode: Optional[str] = None,
    config_overrides: Optional[Dict[str, str]] = None,
) -> None:
    """Background task: spawn, capture output, persist Run/AgentOutput, broadcast SSE.

    *worktree*, when given, is this run's isolated git worktree (task 5.1) — its
    working directory *is* `work_dir` here, but `_execute_run` needs the fact that it's
    an isolated worktree specifically (not just "some cwd") to know whether to snapshot
    it once the run ends (task 5.3's conflict detection needs real commits to compare).

    *use_codex_app_server* (task 2.8) selects a completely separate execution path —
    `_execute_codex_appserver_run` below — since the app-server transport has no PTY/pipe
    subprocess for this function's own read/wait loop to drive; `cli`/`prompt`/`yolo`/
    `mcp_command` are only meaningful for that path (`cmd` was still built for it by the
    caller, but is unused here — app-server has no argv, it speaks JSON-RPC). Anything the
    caller renders *into* that argv therefore has to arrive here by its own parameter or it
    reaches nothing: `permission_mode` was rescued by hand, and `config_overrides` — every
    config-style control, Codex's Effort today — is the rest of that class (F99).
    """
    if use_codex_app_server:
        await _execute_codex_appserver_run(
            project_id=project_id,
            agent=agent,
            run_id=run_id,
            conversation_id=conversation_id,
            cli=cli,
            prompt=prompt,
            model=model,
            work_dir=work_dir,
            known_session_id=known_session_id,
            yolo=yolo,
            mcp_command=mcp_command,
            env=env,
            worktree=worktree,
            permission_mode=permission_mode,
            config_overrides=config_overrides,
        )
        return

    loop = asyncio.get_running_loop()

    try:
        if runner == "codex":
            pty = await loop.run_in_executor(
                None,
                lambda: PipeSession.spawn(cmd, cwd=work_dir, env=env),
            )
        else:
            pty = await loop.run_in_executor(
                None,
                lambda: PtySession.spawn(
                    cmd,
                    cwd=work_dir,
                    env=env,
                    dimensions=STRUCTURED_OUTPUT_DIMENSIONS,
                ),
            )
    # Was `except FileNotFoundError`, which is one way a spawn fails out of many. A corrupt or
    # non-executable runner binary raises `OSError` (`[WinError 193] %1 is not a valid Win32
    # application`), a denied one `PermissionError`, and pywinpty's own failures neither — and
    # every one of those escaped this coroutine entirely. The `Run` row stayed `running` forever,
    # so `POST /agent/trigger`'s "already has a run in progress" guard refused that agent every
    # subsequent turn, and the exception went to asyncio's unretrieved-task handler where nothing
    # reads it. The recovery was to restart the Hub. `except Exception` does not catch
    # `CancelledError`, which is a `BaseException` in 3.8+, so real cancellation still propagates.
    except Exception as exc:  # noqa: BLE001 — a spawn that fails any way at all still ends the run
        async with async_session_factory() as db:
            run = await db.get(Run, run_id)
            if run:
                run.status = "failed"
                run.error = str(exc)
                run.ended_at = datetime.now(timezone.utc)
                # Nothing spawned, so nothing can have asked — swept anyway, because the rule is
                # "a terminal run leaves nothing pending", not "the paths where we expect some".
                await expire_pending_for_run(db, run_id)
                await record_turn_usage(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    agent=agent,
                    runner=runner,
                    sample=None,
                )
            # Design D13, task A4.3 — same as `_execute_run`'s success-path finalize below;
            # a spawn that never started still ends the firing that queued it.
            await finalize_job_run_for_conversation(db, conversation_id, "failed")
            returned = await return_run_entries(db, run_id)
            await db.commit()
            await _report_abandoned_entries(db, project_id, agent, run_id)
            await _broadcast_run_lifecycle(
                db,
                project_id,
                "run_failed",
                agent=agent,
                run_id=run_id,
                **_transport_failure_fields(exc, conversation_id),
            )
            for entry_id in returned:
                payload = {"entry_id": entry_id, "agent": agent, "run_id": run_id}
                await persist_event(db, project_id, "queue_entry_queued", payload, agent=agent)
                await sse_manager.broadcast(project_id, "queue_entry_queued", payload)
        # This branch `return`s before the `schedule_agent` the normal path runs at its end, so
        # without this an entry handed back here waits for something else to drain it. Nothing
        # does on a timer: `redrain_queued_agents` is reachable only from project open, settings
        # save and relocate. Measured — an entry sat `queued` at one attempt until an unrelated
        # settings save drove the second, which is a limit protecting nobody.
        from ...turn_scheduler import redrain_queued_agents

        # A re-drain, not `schedule_agent(project_id, agent)`, and unconditional rather than
        # gated on `returned` — F90. `redrain_queued_agents` schedules every agent that has an
        # entry queued, which is a strict superset: `schedule_agent` returns "queue is empty" for
        # an agent with nothing waiting, so this agent's own entries are still picked up, and so
        # is the agent parked behind the task checkout this run was holding (design D8). A spawn
        # that never started still ends the run, and the run ending is what frees that checkout.
        await redrain_queued_agents(project_id)
        return

    run_liveness.active_ptys[run_id] = pty
    try:
        async with async_session_factory() as db:
            run = await db.get(Run, run_id)
            if run:
                run.pid = pty.pid
                await db.commit()
            await _broadcast_run_lifecycle(
                db,
                project_id,
                "run_started",
                agent=agent,
                run_id=run_id,
                runner=runner,
                model=model,
            )

        parse_line = parse_claude_line if runner in ("claude", "claude_proxy", "native") else None

        session_id = known_session_id
        binding_conflict: Optional[str] = None
        accounting_sample: Optional[AccountingSample] = None
        sequence = 0
        buffer = ""

        async def _flush_line(raw_line: str) -> None:
            nonlocal accounting_sample, binding_conflict, session_id, sequence
            # ConPTY output is control-sequence-laden, not plain text (live-verified — see
            # pty_runner.strip_ansi_escapes's docstring) — every line needs stripping before
            # a JSON-parse attempt, not just the first (e.g. a trailing cursor-restore
            # sequence ConPTY appends after the child exits arrives as its own line).
            line = strip_ansi_escapes(raw_line.rstrip("\r"))
            if not line.strip():
                return
            parsed = (
                parse_line(line) if parse_line is not None else parse_codex_line(line, model=model)
            )
            # Resolve session_id from *this* line before writing its own events, so the row
            # that establishes the session carries it too, not just subsequent rows.
            if parsed.session_id:
                async with async_session_factory() as db:
                    run = await db.get(Run, run_id)
                    conversation = await get_conversation_by_id(db, conversation_id)
                    if conversation is None:
                        binding_conflict = "Conversation disappeared during provider binding"
                    elif conversation.provider_session_id is None:
                        conversation.provider_session_id = parsed.session_id
                        conversation.updated_at = datetime.now(timezone.utc)
                        session_id = parsed.session_id
                    elif conversation.provider_session_id == parsed.session_id:
                        session_id = parsed.session_id
                    else:
                        binding_conflict = (
                            "Provider session binding conflict: "
                            f"expected {conversation.provider_session_id!r}, "
                            f"received {parsed.session_id!r}"
                        )
                    if run and binding_conflict is None:
                        run.session_id = session_id
                    await db.commit()
                    if binding_conflict is not None:
                        await persist_event(
                            db,
                            project_id,
                            "conversation_binding_conflict",
                            {
                                "agent": agent,
                                "run_id": run_id,
                                "conversation_id": conversation_id,
                                "error": binding_conflict,
                            },
                            agent=agent,
                            severity="warn",
                        )
                        return
            for event in parsed.events:
                sequence += 1
                async with async_session_factory() as db:
                    await record_agent_output(
                        db,
                        project_id,
                        agent,
                        content=event.content,
                        session_id=session_id,
                        conversation_id=conversation_id,
                        kind=event.kind,
                        payload=event.payload,
                        run_id=run_id,
                        sequence=sequence,
                    )
            if parsed.usage is not None:
                async with async_session_factory() as db:
                    await record_context_usage(
                        db, project_id, agent, parsed.usage.to_payload(agent)
                    )
            if parsed.accounting is not None:
                accounting_sample = (
                    parsed.accounting
                    if accounting_sample is None
                    else accounting_sample.merged(parsed.accounting)
                )

        while True:
            chunk = await loop.run_in_executor(None, pty.read)
            if not chunk:
                break
            buffer += chunk
            while "\n" in buffer:
                raw_line, buffer = buffer.split("\n", 1)
                await _flush_line(raw_line)
        if buffer.strip():
            await _flush_line(buffer)

        exit_code = await loop.run_in_executor(None, pty.wait)

        if runner == "codex" and session_id:
            codex_home = Path(env["CODEX_HOME"]) if env and env.get("CODEX_HOME") else None
            rollout_accounting = await loop.run_in_executor(
                None,
                lambda: read_codex_rollout_accounting(
                    session_id, codex_home=codex_home, model=model
                ),
            )
            if rollout_accounting is not None:
                accounting_sample = (
                    rollout_accounting
                    if accounting_sample is None
                    else accounting_sample.merged(rollout_accounting)
                )

        snapshot_sha: Optional[str] = None
        if worktree is not None:
            # Task 5.3 needs real commits to compare branches with `git merge-tree` —
            # an agent's turn just ends with dirty files in its worktree otherwise, which
            # a conflict check has nothing to diff against. Best-effort: a git failure here
            # must not turn a completed/failed run into something worse than it already is.
            try:
                snapshot_sha = await loop.run_in_executor(
                    None, lambda: worktrees.snapshot_worktree(worktree, agent)
                )
            except worktrees.GitCommandError:
                logger.warning(
                    "Could not snapshot %r's worktree after run %s", agent, run_id, exc_info=True
                )

        # A deliberate stop (task 3.7) also exits the read loop and reaches this same
        # point — force-terminating a process rarely yields exit code 0, so without this
        # check a stop would be misreported as "failed". Checked before the exit-code
        # branch below so a stop always wins regardless of what the process happened to
        # exit with.
        if binding_conflict is not None:
            final_status, lifecycle_event = "failed", "run_failed"
        elif run_id in _stop_requested:
            final_status, lifecycle_event = "stopped", "run_stopped"
        elif exit_code == 0:
            final_status, lifecycle_event = "completed", "run_completed"
        else:
            final_status, lifecycle_event = "failed", "run_failed"

        async with async_session_factory() as db:
            run = await db.get(Run, run_id)
            if run is None:
                # Loud on purpose. This was a bare `if run:` with no `else`, so a finalize that
                # could not see its own row did nothing and said nothing: no exception, no log and
                # no `error` field, while the row stays `running` for good.
                # `turn_scheduler.schedule_agent` then refuses every later turn for the agent
                # (`turn_scheduler.py:37-43`) and `trigger_agent` answers 200/`queued` to each, so
                # the agent goes quietly deaf while every surface still reads "running". That is
                # the same unbounded outage the `except` handler below was widened to prevent,
                # reached by a second route — and a run that ends but cannot record that it ended
                # is a defect wherever it comes from, so it is reported rather than swallowed.
                logger.error(
                    "Run %s for %r finished (%s, exit %r) but its row was not visible to the "
                    "finalizing session, so the terminal status could not be recorded. The row "
                    "stays 'running' and the agent will queue every later turn.",
                    run_id,
                    agent,
                    final_status,
                    exit_code,
                )
            if run:
                run.status = final_status
                run.exit_code = exit_code
                if binding_conflict is not None:
                    run.error = binding_conflict
                run.ended_at = datetime.now(timezone.utc)
                # NULL when the turn changed nothing — `snapshot_worktree` commits only a dirty
                # tree. A checkpoint reads these to say what its conversation changed.
                run.snapshot_commit_sha = snapshot_sha
                # Evidence this run recorded named the commit the turn *started* from, because the
                # work was still uncommitted then. The commit above is the one that holds it.
                await _restamp_evidence_footprints(
                    db,
                    project_id=project_id,
                    run_id=run_id,
                    worktree=worktree,
                    snapshot_sha=snapshot_sha,
                )
                # A run that is over has stopped waiting on anything, so nothing it opened may
                # still read as answerable. In the same transaction as `ended_at`: the two facts
                # must not be separable by a reader.
                await expire_pending_for_run(db, run_id)
                await record_turn_usage(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    agent=agent,
                    runner=runner,
                    sample=accounting_sample,
                )
            # Outside the `if run` guard, and before the commit that closes this block. A run that
            # ended abnormally is carrying input nobody else will hand back, and the spawn-failure
            # branch above already reads this way — a run row that has vanished still has entries.
            # Until this existed, `return_run_entries` was reachable only from the two *pre-spawn*
            # `except` blocks, so a runtime that died once the turn was under way came back as a
            # failed status here and its entries stayed `delivered` at zero attempts: never
            # retried, never abandoned, never reported. A deliberate stop is `stopped`, not
            # `failed`, so it keeps its input.
            #
            # A binding conflict is excluded, and it is the one failure that has to be. It is
            # raised *after* the turn ran — the agent did the work and streamed its output — so the
            # input was processed rather than lost, and re-delivering it makes the agent redo a
            # completed turn. Worse, the retry would defeat the check it comes from: at
            # `RESUME_RETRY_LIMIT` the conversation gives up its provider session, so the third
            # attempt binds the very session id the conflict refused, and a misbehaving CLI
            # overwrites the binding this check exists to protect.
            #
            # Design D13, task A4.3: if this run's conversation belongs to a job's loop firing,
            # that firing is no longer "in progress" once the agent's own turn has ended, one
            # way or the other. A no-op for the common case of a run that was never a firing.
            await finalize_job_run_for_conversation(db, conversation_id, final_status)
            returned = (
                await return_run_entries(db, run_id)
                if final_status == "failed" and binding_conflict is None
                else []
            )
            await db.commit()
            # The run boundary. After the commit, so the check reads the run's final state, and
            # outside the `if run` block for the same reason — a missing run row is not a
            # divergence, and `evaluate_run_end` says so itself.
            #
            # Skipped when this run's input went back to the queue, exactly as
            # `run_reconciliation.py:59` skips it: the work is about to be handed to a new run that
            # will bind to the same task, so nothing has been dropped. The condition is on the
            # returned set rather than on `final_status` — a failed run whose entries were all
            # abandoned on this attempt has genuinely dropped its work and must still be evaluated.
            if not returned:
                await evaluate_run_end(run_id)
                # The author's handover (finding F43). Beside the divergence check because it is
                # the same boundary asking the mirrored question: that one is "did this run drop
                # the work", this one is "did it finish work somebody else now has to read". Both
                # runners reach it for the reason the divergence check does -- the boundary is
                # AgentWeave's, not either agent's. Not awaited: generation is a ~19s CLI spawn,
                # and it self-declines for anything that is not a flow agent handing over with
                # notes already recorded for its reviewer.
                consider_handover_from_run_end(run_id)
            await _report_abandoned_entries(db, project_id, agent, run_id)
            await _broadcast_run_lifecycle(
                db,
                project_id,
                lifecycle_event,
                agent=agent,
                run_id=run_id,
                conversation_id=conversation_id,
                session_id=session_id,
                exit_code=exit_code,
            )
            for entry_id in returned:
                payload = {"entry_id": entry_id, "agent": agent, "run_id": run_id}
                await persist_event(db, project_id, "queue_entry_queued", payload, agent=agent)
                await sse_manager.broadcast(project_id, "queue_entry_queued", payload)
            # Persisted *and* broadcast, through the one writer that does both. This was a bare
            # `sse_manager.broadcast`, so the line existed only for as long as the live stream did.
            #
            # Design D6, re-argued from measurement 2026-09-02. The row that satisfies the
            # client's `isSuccessCompletionEntry` today is written by a different producer — the
            # stream parser at `runner_parsing.py:356` — and only for a Claude-family runner that
            # announced a clean turn (`parse_claude_line` is selected at `:1867`;
            # `status_event("completed")` occurs exactly once in the Hub). So this line is the
            # only settled signal a **stopped, failed or binding-conflicted** run has ever had on
            # either runner, and the only one a **Codex** run has ever had for any outcome at all.
            # It also carries the exit code, which was otherwise unrecoverable the moment the
            # stream ended.
            #
            # The justification that used to sit here — that AgentOutputPanel's "Handoff" flow
            # scans the output stream for this line — is stale: that effect was deleted
            # (`AgentOutputPanel.tsx:148-151`). The consumer that matters is `lastRunSettled`
            # (`AgentTimeline.tsx:115`), and it reads the *persisted* row, so the shape below is
            # what has to be preserved. The key set is unchanged; only the id differs, because
            # `record_agent_output` mints `out-{short_id()}` and takes no override. Nothing in
            # `hub/ui/src` keys on the old deterministic `status-{run_id}`.
            #
            # `phase` stays "completed" even for a stopped/failed run — it means "the run has
            # ended", not "it succeeded" — and `AgentTimeline.tsx:430` returns null for it either
            # way. The row is durable rather than visible; the visible outcome is the terminal
            # label the timeline route's `runs` map carries.
            await record_agent_output(
                db,
                project_id,
                agent,
                content=f"Run {final_status} (exit {exit_code}).",
                session_id=session_id,
                conversation_id=conversation_id,
                kind="status",
                payload={"phase": "completed", "exit_code": exit_code},
                run_id=run_id,
                sequence=sequence + 1,
            )

        # After the response has landed, so the titler sees the exchange rather than the
        # opening line alone, and so nothing the operator is waiting on is delayed by it.
        await maybe_generate_title(project_id=project_id, conversation_id=conversation_id)

        # A turn ending with queued entries starts the next turn without waiting for
        # operator input. The scheduler itself applies the hop budget and drain cap.
        from ...turn_scheduler import redrain_queued_agents

        # Every agent with something queued, not just this one (F90).
        #
        # `schedule_agent(project_id, agent)` was here, and it is right for the ordinary case: a
        # turn that ended with its own entries queued starts the next one. It is not enough for a
        # hold that belongs to another agent. A task's checkout admits one writing turn at a time
        # (design D8), and the agent refused by that rule is refused *transiently* — the entry
        # keeps its delivery attempts, stays `queued`, and `turn_scheduler` says "the next tick
        # tries again". There is no tick. `redrain_queued_agents` is reachable from project open,
        # settings save and relocate, and from nowhere else, so the entry waited on an unrelated
        # operator action.
        #
        # Measured on 2026-08-28: `builder` held a task, `reviewer`'s turn on the same task was
        # parked, `builder` finished, and four minutes later every agent was idle with the entry
        # still `queued` at zero attempts and `waiting_reason: null`. A settings save delivered it
        # instantly.
        #
        # Project-scoped rather than "agents waiting on the task this run held", deliberately. The
        # invariant is that a run ending frees whatever it held, and the task checkout is only
        # today's instance of that; scoping to the task would be correct now and silently
        # incomplete for the next hold anyone adds. Cheap either way — the query returns only
        # agents that actually have something queued, and `schedule_agent` refuses a busy one.
        #
        # A superset of what it replaces rather than an addition to it: `schedule_agent` answers
        # "queue is empty" for an agent with nothing waiting, so re-draining covers this agent's
        # own entries too and calling both would schedule it twice.
        await redrain_queued_agents(project_id)
    except (Exception, asyncio.CancelledError) as exc:
        # Every step above this point is inside the same `try` and none of it is wrapped
        # individually — so an exception anywhere between the spawn succeeding and this turn's
        # own bookkeeping (title generation, the next-turn scheduler, ...) used to leave the
        # `Run` row exactly where the spawn-success commit put it: `status="running"`, forever.
        # `turn_scheduler.schedule_agent` refuses a new turn while one is `running`
        # (`turn_scheduler.py:37-43`), so the agent silently queued every future trigger instead
        # of running it — an unbounded outage with no error anywhere a human would see. Measured
        # live in CI (`test_a_conversation_whose_model_changed_attributes_usage_per_turn`,
        # 2026-08-17): `run_liveness.active_ptys` and `_background_runs` both empty — the task
        # had genuinely finished — while the `Run` row still read `running` with `error=None`,
        # which ruled out every regular `Exception` (an `except Exception` guard here, tried
        # first, changed nothing — same symptom, same `error=None` on the next CI run).
        # `CancelledError` is a `BaseException` in Python 3.8+, not an `Exception`, and nothing
        # in this codebase calls `.cancel()` on this task (`_stop_requested` is a cooperative
        # flag the read loop checks itself, not a cancellation) — but that only means no *known*
        # caller does; a test transport or event-loop teardown cancelling an orphaned background
        # task is exactly the kind of thing that would vanish from view rather than log
        # anything, since asyncio's own default handler does not warn on an unretrieved
        # `CancelledError` the way it does for everything else. Re-raised below, once the row is
        # marked, to preserve real cancellation semantics for anything that legitimately depends
        # on it propagating.
        logger.exception("Unhandled error in run %s for %r", run_id, agent)
        already_terminal = False
        async with async_session_factory() as db:
            run = await db.get(Run, run_id)
            if run is None or run.status != "running":
                # The turn itself already reached a terminal status (or the row is gone) before
                # this exception happened, so whatever failed is downstream of a turn that
                # already succeeded or failed cleanly. Overwriting that here would let unrelated
                # bookkeeping failures relabel a completed run as failed.
                already_terminal = True
            else:
                run.status = "failed"
                run.error = str(exc)
                run.ended_at = datetime.now(timezone.utc)
                await expire_pending_for_run(db, run_id)
                # The last of `_execute_run`'s five terminal sites to record one, and the only one
                # reached without knowing whether the turn produced telemetry — so `sample=None`,
                # an explicitly unavailable outcome, for the same reason the `FileNotFoundError`
                # branch above records one for a run that never spawned at all. Idempotent: a turn
                # that had already parsed its result recorded a measured outcome, and
                # `record_turn_usage` returns that existing row rather than overwriting it.
                await record_turn_usage(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    agent=agent,
                    runner=runner,
                    sample=None,
                )
                # Design D13, task A4.3 — same as `_execute_run`'s other finalize sites.
                await finalize_job_run_for_conversation(db, conversation_id, "failed")
                returned = await return_run_entries(db, run_id)
                await db.commit()
                await _report_abandoned_entries(db, project_id, agent, run_id)
                await _broadcast_run_lifecycle(
                    db,
                    project_id,
                    "run_failed",
                    agent=agent,
                    run_id=run_id,
                    **_transport_failure_fields(exc, conversation_id),
                )
                for entry_id in returned:
                    payload = {"entry_id": entry_id, "agent": agent, "run_id": run_id}
                    await persist_event(db, project_id, "queue_entry_queued", payload, agent=agent)
                    await sse_manager.broadcast(project_id, "queue_entry_queued", payload)
        if not already_terminal:
            from ...turn_scheduler import redrain_queued_agents

            # Unconditional, where this was gated on `returned`. A run that fails releases the
            # task checkout it held exactly as a run that succeeds does, so an agent parked behind
            # it by design D8 has to be re-evaluated whether or not *this* run handed anything
            # back. Gating on `returned` would mean the hold outlives the holder whenever the
            # failing turn had no queue of its own — which is the ordinary case.
            await redrain_queued_agents(project_id)
        if isinstance(exc, asyncio.CancelledError):
            raise
    finally:
        run_liveness.active_ptys.pop(run_id, None)
        _stop_requested.discard(run_id)


# How Codex's approval methods read on the operator's card. The raw method names
# ("item/commandExecution/requestApproval") are protocol, not something to put in front of a
# person deciding in seconds.
_CODEX_APPROVAL_LABELS = {
    "item/commandExecution/requestApproval": "a command",
    "item/fileChange/requestApproval": "a file change",
}


def _codex_posture(permission_mode: Optional[str]) -> Optional[str]:
    """Map the operator's chosen posture onto what `decide_approval` understands.

    "manual" is the operator-answered posture for both providers; the value differs only
    because Claude's spelling is its CLI's own.

    Every posture that changes a Codex decision has to survive this mapping. "Full access" used
    to fall through to `None`, and `None` is the *default* posture — so a thread the operator had
    put under full access started `workspace-write`/`on-request` and declined every approval it
    then raised, which is strictly less than "Workspace only" grants. It only ever appeared to
    work because setting an agent's *default* posture also writes the legacy `config["yolo"]`
    flag, and `yolo` reaches `_thread_policy` by its own route; the composer's per-run override
    writes no such flag, so the same choice made there did the opposite. Measured live on both
    surfaces, 2026-08-28: the agent-default run wrote outside its worktree, the per-run-override
    run was refused by the sandbox.

    `acceptEdits` stays mapped to `None` deliberately. It *is* the default posture, and its
    Codex meaning — edit freely inside the workspace, refuse an escalation out of it — is what
    the default pair already produces.
    """
    if permission_mode == "manual":
        return OPERATOR_POSTURE
    if permission_mode == WORKSPACE_PERMISSION_MODE:
        return WORKSPACE_PERMISSION_MODE
    if permission_mode == FULL_ACCESS_PERMISSION_MODE:
        return FULL_ACCESS_PERMISSION_MODE
    return None


def _codex_decision_timeout(env: Optional[Dict[str, str]]) -> int:
    """This run's permission wait, from the same environment variable the Claude path uses.

    Read from `env` rather than threaded as another parameter because the trigger already put it
    there for the MCP process, and one carrier for one setting means the two transports cannot
    drift apart. Anything unparseable or out of range falls back, matching `mcp_server`'s rule.
    """
    # Imported here, not at module scope: `.agents` imports this module back.
    from .agents import MAX_WAITING_SECONDS, MIN_WAITING_SECONDS

    raw = (env or {}).get("AW_DECISION_TIMEOUT")
    if not raw:
        return CODEX_OPERATOR_DECISION_TIMEOUT
    try:
        value = int(raw)
    except ValueError:
        return CODEX_OPERATOR_DECISION_TIMEOUT
    if MIN_WAITING_SECONDS <= value <= MAX_WAITING_SECONDS:
        return value
    return CODEX_OPERATOR_DECISION_TIMEOUT


async def _await_operator_permission(
    *,
    project_id: str,
    agent: str,
    run_id: str,
    method: str,
    subject: Dict[str, object],
    timeout_seconds: Optional[int] = None,
) -> bool:
    """Open a permission request for a Codex approval and wait for the operator.

    The Codex counterpart of `mcp_server._ask_operator`, and it holds the same line: a turn is
    suspended, not failed, while this waits, so the wait is bounded and running out denies.
    Codex is waiting on a JSON-RPC response the whole time.
    """
    request_id = f"perm-{short_id()}"
    async with async_session_factory() as db:
        db.add(
            PermissionRequest(
                id=request_id,
                project_id=project_id,
                agent=agent,
                run_id=run_id,
                conversation_id=await conversation_id_for_run(db, run_id),
                tool_name=_CODEX_APPROVAL_LABELS.get(method, method),
                tool_use_id="",
                tool_input=dict(subject),
                status="pending",
            )
        )
        await db.commit()
    await sse_manager.broadcast(
        project_id,
        "permission_requested",
        {
            "id": request_id,
            "agent": agent,
            "tool_name": _CODEX_APPROVAL_LABELS.get(method, method),
            "run_id": run_id,
        },
    )

    deadline = asyncio.get_event_loop().time() + (
        timeout_seconds if timeout_seconds is not None else CODEX_OPERATOR_DECISION_TIMEOUT
    )
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(CODEX_OPERATOR_POLL_SECONDS)
        async with async_session_factory() as db:
            row = await db.get(PermissionRequest, request_id)
            status_now = row.status if row is not None else "denied"
        if status_now == "allowed":
            return True
        if status_now in ("denied", "expired"):
            return False

    async with async_session_factory() as db:
        row = await db.get(PermissionRequest, request_id)
        if row is not None and row.status == "pending":
            row.status = "expired"
            await db.commit()
    return False


async def _execute_codex_appserver_run(
    *,
    project_id: str,
    agent: str,
    run_id: str,
    conversation_id: str,
    cli: str,
    prompt: str,
    model: Optional[str],
    work_dir: Optional[str],
    known_session_id: Optional[str],
    yolo: bool,
    mcp_command: Optional[List[str]],
    env: Optional[Dict[str, str]],
    worktree: Optional[Path],
    permission_mode: Optional[str] = None,
    config_overrides: Optional[Dict[str, str]] = None,
) -> None:
    """Codex `app-server` (task 2.8) counterpart to `_execute_run`'s PTY/pipe read loop above.

    `codex_appserver.run_turn` owns the actual subprocess and JSON-RPC exchange internally
    (see its own docstring); this function's job is only to wire that transport's callbacks
    to the same recording/broadcast/scheduling calls `_execute_run` makes for `exec`, so the
    two transports are indistinguishable to everything downstream of a `Run` row (task 2.5's
    stated goal) — a `Run`, its `AgentOutput` rows, its usage accounting, and its lifecycle
    broadcasts all look the same regardless of which transport produced them.
    """
    run_liveness.active_app_server_runs.add(run_id)
    try:
        async with async_session_factory() as db:
            await _broadcast_run_lifecycle(
                db,
                project_id,
                "run_started",
                agent=agent,
                run_id=run_id,
                runner="codex",
                model=model,
            )

        session_id = known_session_id
        binding_conflict: Optional[str] = None
        accounting_sample: Optional[AccountingSample] = None
        sequence = 0

        async def _bind_session_id(thread_id: str) -> None:
            # Mirrors `_execute_run._flush_line`'s conversation-binding logic (same
            # conflict/first-writer rules), fired once per turn instead of once per line —
            # app-server hands the Hub its session identity up front, `exec` reveals it
            # mid-stream.
            nonlocal binding_conflict, session_id
            async with async_session_factory() as db:
                run = await db.get(Run, run_id)
                conversation = await get_conversation_by_id(db, conversation_id)
                if conversation is None:
                    binding_conflict = "Conversation disappeared during provider binding"
                elif conversation.provider_session_id is None:
                    conversation.provider_session_id = thread_id
                    conversation.updated_at = datetime.now(timezone.utc)
                    session_id = thread_id
                elif conversation.provider_session_id == thread_id:
                    session_id = thread_id
                else:
                    binding_conflict = (
                        "Provider session binding conflict: "
                        f"expected {conversation.provider_session_id!r}, received {thread_id!r}"
                    )
                if run and binding_conflict is None:
                    run.session_id = session_id
                await db.commit()
                if binding_conflict is not None:
                    await persist_event(
                        db,
                        project_id,
                        "conversation_binding_conflict",
                        {
                            "agent": agent,
                            "run_id": run_id,
                            "conversation_id": conversation_id,
                            "error": binding_conflict,
                        },
                        agent=agent,
                        severity="warn",
                    )

        async def _on_event(event) -> None:
            nonlocal sequence
            sequence += 1
            async with async_session_factory() as db:
                await record_agent_output(
                    db,
                    project_id,
                    agent,
                    content=event.content,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    kind=event.kind,
                    payload=event.payload,
                    run_id=run_id,
                    sequence=sequence,
                )

        async def _on_usage(usage) -> None:
            async with async_session_factory() as db:
                await record_context_usage(db, project_id, agent, usage.to_payload(agent))

        async def _on_accounting(accounting) -> None:
            nonlocal accounting_sample
            accounting_sample = (
                accounting if accounting_sample is None else accounting_sample.merged(accounting)
            )

        async def _on_refusal(method: str, subject: Dict[str, Any]) -> None:
            """Record a refusal this runtime decided by itself.

            Claude's refusals reach the event log through `approve_tool_call`, which is a
            `--permission-prompt-tool` flag and therefore Claude-only. A Codex agent declined by
            its own sandbox produced nothing at all: not an event, not an SSE frame, not a line in
            the timeline. Found live -- a reviewing agent was refused permission to write its own
            review file and said so in prose, while the Hub's durable record showed a clean run.
            """
            reason = subject.get("reason") or ""
            # `paths` before `grantRoot`: a refused file change now names the files it wanted
            # (F107), and the root it asked to be granted is the coarser fallback for the case
            # where the turn never saw the item.
            detail = (
                subject.get("command") or subject.get("paths") or subject.get("grantRoot") or ""
            )
            async with async_session_factory() as db:
                await persist_event(
                    db,
                    project_id=project_id,
                    event_type="permission_denied",
                    agent=agent,
                    data={
                        "tool_name": codex_approval_label(method),
                        "reason": reason or (f"outside {agent}'s workspace" if detail else ""),
                        "detail": detail if isinstance(detail, str) else " ".join(map(str, detail)),
                        "run_id": run_id,
                        "decided_by": "runtime",
                    },
                    severity="warn",
                )
            await sse_manager.broadcast(
                project_id,
                "permission_denied",
                {"agent": agent, "tool_name": codex_approval_label(method), "run_id": run_id},
            )

        try:
            outcome: TurnOutcome = await codex_run_turn(
                cli=cli,
                posture=_codex_posture(permission_mode),
                workspace=work_dir,
                request_approval=lambda method, subject: _await_operator_permission(
                    project_id=project_id,
                    agent=agent,
                    run_id=run_id,
                    method=method,
                    subject=subject,
                    timeout_seconds=_codex_decision_timeout(env),
                ),
                cwd=work_dir,
                env=env,
                prompt=prompt,
                model=model,
                resume_thread_id=known_session_id,
                yolo=yolo,
                mcp_command=mcp_command,
                config_overrides=config_overrides,
                on_event=_on_event,
                on_usage=_on_usage,
                on_accounting=_on_accounting,
                on_thread_started=_bind_session_id,
                should_interrupt=lambda: run_id in _stop_requested,
                on_refusal=_on_refusal,
            )
        except (FileNotFoundError, AppServerError, asyncio.TimeoutError, OSError) as exc:
            # Mirrors `_execute_run`'s own early-spawn-failure handling: nothing was ever
            # delivered to the agent, so returned queue entries go back to "queued" rather
            # than being recorded against a run that never really started.
            async with async_session_factory() as db:
                run = await db.get(Run, run_id)
                if run:
                    run.status = "failed"
                    run.error = str(exc)
                    run.ended_at = datetime.now(timezone.utc)
                    # See `_execute_run`'s spawn-failure branch.
                    await expire_pending_for_run(db, run_id)
                    await record_turn_usage(
                        db,
                        run_id=run_id,
                        project_id=project_id,
                        agent=agent,
                        runner="codex",
                        sample=None,
                    )
                # Design D13, task A4.3 — see `_execute_run`'s spawn-failure branch.
                await finalize_job_run_for_conversation(db, conversation_id, "failed")
                returned = await return_run_entries(db, run_id)
                await db.commit()
                await _report_abandoned_entries(db, project_id, agent, run_id)
                await _broadcast_run_lifecycle(
                    db,
                    project_id,
                    "run_failed",
                    agent=agent,
                    run_id=run_id,
                    **_transport_failure_fields(exc, conversation_id),
                )
                for entry_id in returned:
                    payload = {"entry_id": entry_id, "agent": agent, "run_id": run_id}
                    await persist_event(db, project_id, "queue_entry_queued", payload, agent=agent)
                    await sse_manager.broadcast(project_id, "queue_entry_queued", payload)
            # See `_execute_run`'s spawn-failure branch: this one `return`s too, so the entries it
            # hands back need the same push.
            from ...turn_scheduler import redrain_queued_agents

            # See `_execute_run`'s spawn-failure branch: a re-drain, unconditionally, so this
            # run's task checkout stops holding anyone back.
            await redrain_queued_agents(project_id)
            return

        snapshot_sha: Optional[str] = None
        if worktree is not None:
            # Same best-effort snapshot as `_execute_run` — a git failure here must not turn
            # a completed/failed run into something worse than it already is.
            try:
                loop = asyncio.get_running_loop()
                snapshot_sha = await loop.run_in_executor(
                    None, lambda: worktrees.snapshot_worktree(worktree, agent)
                )
            except worktrees.GitCommandError:
                logger.warning(
                    "Could not snapshot %r's worktree after run %s", agent, run_id, exc_info=True
                )

        # A deliberate stop reaches here as `TurnOutcome.status == "interrupted"` (run_turn's
        # own `should_interrupt` handling), the app-server equivalent of exec's
        # `run_id in _stop_requested` check — that same set is what `should_interrupt` above
        # polled to decide to send `turn/interrupt` in the first place.
        if binding_conflict is not None:
            final_status, lifecycle_event = "failed", "run_failed"
        elif outcome.status == "interrupted":
            final_status, lifecycle_event = "stopped", "run_stopped"
        elif outcome.status == "completed":
            final_status, lifecycle_event = "completed", "run_completed"
        else:
            final_status, lifecycle_event = "failed", "run_failed"
        # No process exit code exists for this transport; 0/1 keeps `Run.exit_code` and the
        # "Run {status} (exit {code})" status line meaningful to the same UI code that reads
        # them for the exec path (AgentOutputPanel's handoff-detection, see below).
        exit_code = 0 if final_status == "completed" else 1

        async with async_session_factory() as db:
            run = await db.get(Run, run_id)
            if run:
                run.status = final_status
                run.exit_code = exit_code
                if binding_conflict is not None:
                    run.error = binding_conflict
                elif outcome.error:
                    run.error = outcome.error
                run.ended_at = datetime.now(timezone.utc)
                # NULL when the turn changed nothing — see `_execute_run`.
                run.snapshot_commit_sha = snapshot_sha
                # See `_execute_run`.
                await _restamp_evidence_footprints(
                    db,
                    project_id=project_id,
                    run_id=run_id,
                    worktree=worktree,
                    snapshot_sha=snapshot_sha,
                )
                # See `_execute_run`. A no-op on the Codex path's own approvals, which expire
                # themselves at their `asyncio.TimeoutError` — the guard is `status == "pending"`,
                # so arriving second changes nothing rather than double-writing.
                await expire_pending_for_run(db, run_id)
                await record_turn_usage(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    agent=agent,
                    runner="codex",
                    sample=accounting_sample,
                )
            # See `_execute_run`. This is the path a killed app-server actually takes: `run_turn`
            # returns a failed `TurnOutcome` rather than raising, so the pre-spawn `except` above
            # never sees it. A stop arrives as `outcome.status == "interrupted"` → `stopped`, and
            # keeps its input. A binding conflict is excluded for the reason given there.
            #
            # See `_execute_run`'s identical call — design D13, task A4.3.
            await finalize_job_run_for_conversation(db, conversation_id, final_status)
            returned = (
                await return_run_entries(db, run_id)
                if final_status == "failed" and binding_conflict is None
                else []
            )
            await db.commit()
            # The run boundary, as in `_execute_run`. Both runners reach it, because the check sits
            # at a boundary AgentWeave owns rather than inside either agent. Skipped when the input
            # went back to the queue, for the reason given there.
            if not returned:
                await evaluate_run_end(run_id)
                # The author's handover (finding F43). Beside the divergence check because it is
                # the same boundary asking the mirrored question: that one is "did this run drop
                # the work", this one is "did it finish work somebody else now has to read". Both
                # runners reach it for the reason the divergence check does -- the boundary is
                # AgentWeave's, not either agent's. Not awaited: generation is a ~19s CLI spawn,
                # and it self-declines for anything that is not a flow agent handing over with
                # notes already recorded for its reviewer.
                consider_handover_from_run_end(run_id)
            await _report_abandoned_entries(db, project_id, agent, run_id)
            # `exit_code` above is the synthetic 0/1 this transport has to invent, because there is
            # no per-turn process status; `AgentOutputPanel.tsx` reads it to detect a handoff and
            # the status line derives from it, so its meaning is fixed. The runtime's own status
            # travels beside it under its own name — one death used to report two numbers with
            # nothing to say which was which. Omitted, not nulled, where there is nothing to say.
            await _broadcast_run_lifecycle(
                db,
                project_id,
                lifecycle_event,
                agent=agent,
                run_id=run_id,
                conversation_id=conversation_id,
                session_id=session_id,
                exit_code=exit_code,
                **_runtime_failure_fields(outcome, lifecycle_event),
            )
            for entry_id in returned:
                payload = {"entry_id": entry_id, "agent": agent, "run_id": run_id}
                await persist_event(db, project_id, "queue_entry_queued", payload, agent=agent)
                await sse_manager.broadcast(project_id, "queue_entry_queued", payload)
            # Persisted and broadcast through the same one writer as `_execute_run`'s identical
            # line, for the reason given there in full. This transport is where it matters most:
            # neither Codex transport emits a completion sentinel of its own
            # (`parse_codex_line`'s only `status_event` is "plan", `runner_parsing.py:574`; the
            # app-server's only one is "plan", `codex_appserver.py:544`), so before this a Codex
            # run had no settled signal for *any* outcome, a clean completion included.
            await record_agent_output(
                db,
                project_id,
                agent,
                content=f"Run {final_status} (exit {exit_code}).",
                session_id=session_id,
                conversation_id=conversation_id,
                kind="status",
                payload={"phase": "completed", "exit_code": exit_code},
                run_id=run_id,
                sequence=sequence + 1,
            )

        await maybe_generate_title(project_id=project_id, conversation_id=conversation_id)

        from ...turn_scheduler import redrain_queued_agents

        # See `_execute_run`: the same release, for the same reason.
        await redrain_queued_agents(project_id)
    finally:
        run_liveness.active_app_server_runs.discard(run_id)
        _stop_requested.discard(run_id)


@router.get("/sessions/{agent}")
async def get_agent_sessions(
    agent: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Get unique session IDs for an agent from AgentOutput table.

    Returns sessions that the agent has generated output for, ordered by recency.
    Each session includes last_active (most recent output) and started_at (first output).
    """
    from sqlalchemy import func, select

    from ...db.models import AgentOutput

    project_id, _ = project

    # Group by session_id to get first and last output timestamps per session
    q = (
        select(
            AgentOutput.session_id,
            func.max(AgentOutput.timestamp).label("last_active"),
            func.min(AgentOutput.timestamp).label("started_at"),
        )
        .where(
            AgentOutput.project_id == project_id,
            AgentOutput.agent == agent,
            AgentOutput.session_id.isnot(None),
        )
        .group_by(AgentOutput.session_id)
        .order_by(func.max(AgentOutput.timestamp).desc())
    )
    result = await session.execute(q)
    rows = result.all()

    sessions = [
        {
            "id": row.session_id,
            "type": "agent",
            "path": f".agentweave/agents/{agent}-session.json",
            "last_active": row.last_active.isoformat() if row.last_active else None,
            "started_at": row.started_at.isoformat() if row.started_at else None,
        }
        for row in rows
        if row.session_id
    ]

    return {"sessions": sessions}
