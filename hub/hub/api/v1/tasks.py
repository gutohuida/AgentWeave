"""Task endpoints — POST/GET/GET{id}/PATCH."""

import re
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ... import (
    dependency_gate,
    project_workspace,
    spec_lifecycle,
    spec_reading,
    task_dependency_writer,
)
from ...agent_activity import latest_activity_by_agent
from ...agent_status import effective_heartbeat_status
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import (
    Agent,
    AgentHeartbeat,
    AIJob,
    EvidenceReview,
    Loop,
    Project,
    Question,
    RequirementEvidence,
    Run,
    RunDivergence,
    SpecDocument,
    SpecRequirement,
    Task,
    TaskDependency,
    TaskIntegration,
    TaskRequirementLink,
    TaskRequirementReference,
)
from ...requirement_evidence import REJECTED as EVIDENCE_REJECTED
from ...requirement_links import LinkRefusedError, absorb_free_text, link, resolve_identifiers
from ...run_task_binding import (
    TERMINAL_FOR_BINDING,
    reason_from_question,
    release_bindings_to,
    release_reason,
)
from ...schemas.tasks import (
    TaskCreate,
    TaskDependencyRef,
    TaskIntegrationSummary,
    TaskResponse,
    TaskUpdate,
)
from ...spec_lifecycle import Actor as SpecActor
from ...sse import sse_manager
from ...task_transition_service import (
    TransitionRefusedError,
    apply_transition,
    guard_entry_status,
    retry_integration,
)
from ...task_transitions import (
    ACTOR_OPERATOR,
    STATUS_BLOCKED,
    Actor,
    allowed_map_for,
    operator,
)
from ...utils import persist_event, short_id

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _task_response(
    task: Task,
    heartbeat: Optional[AgentHeartbeat] = None,
    *,
    has_open_divergence: bool = False,
    latest_integration: Optional[TaskIntegration] = None,
    approval_report: Optional[List[Any]] = None,
) -> TaskResponse:
    response = TaskResponse.model_validate(task)
    effective_status, effective_message = effective_heartbeat_status(heartbeat)
    response.assignee_status = effective_status if task.assignee else None
    response.assignee_status_msg = effective_message
    response.assignee_last_seen = heartbeat.timestamp if heartbeat else None
    response.has_open_divergence = has_open_divergence
    response.latest_integration = (
        TaskIntegrationSummary.model_validate(latest_integration)
        if latest_integration is not None
        else None
    )
    response.approval_report = list(approval_report or [])
    return response


async def _attach_requirements(
    session: AsyncSession, responses: List[TaskResponse], *, project_id: str
) -> List[TaskResponse]:
    """Fill in what each task serves, what that requirement says, and what resolved to nothing.

    Batched across the whole page rather than queried per task: a board with a
    hundred cards would otherwise take two hundred round trips to answer a
    question that is two joins.

    The **wording** comes from the document, never from the row — `SpecRequirement` holds only a
    digest, precisely so it cannot come to disagree with the document about what a requirement says.
    One file read per distinct document, so the cost is a function of how many specifications a
    board draws on rather than how finely the work was decomposed.

    An identifier alone is only actionable by a reader who can open the document, which for an agent
    was not true at all until recently. Carrying the statement is what makes a task independently
    workable.
    """
    task_ids = [response.id for response in responses]
    if not task_ids:
        return responses

    links = await session.execute(
        select(TaskRequirementLink.task_id, SpecRequirement)
        .join(SpecRequirement, SpecRequirement.id == TaskRequirementLink.requirement_id)
        .where(TaskRequirementLink.task_id.in_(task_ids))
        .order_by(SpecRequirement.identifier)
    )
    rows = list(links)

    # Degrading is the requirement, not caution: `resolve_project_workspace` raises when a project's
    # directory has moved, and a task board must not fail because a specification is unreachable.
    wording: dict[str, dict] = {}
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
        payloads = await spec_reading.payloads_for_documents(
            session, workspace, [requirement.document_id for _, requirement in rows]
        )
        wording = {
            document_id: spec_reading.statements_by_key(payload)
            for document_id, payload in payloads.items()
        }
    except Exception:
        wording = {}

    # `requirement_coverage._state` now has a `rejected` state for a requirement whose only
    # current-digest evidence was turned down, but that state only holds while every row is
    # rejected — the moment a task acquires *any* other evidence (awaiting, accepted), coverage
    # moves on and the rejection stops being visible there. This signal is independent of coverage
    # state for that reason: it names the rejection even after a later acceptance moves coverage to
    # `verified`, so approving the task above it is never silent about an earlier turned-down
    # attempt. Scoped to the current digest, the same way coverage itself is: a rejection against a
    # since-reworded requirement said nothing about what the requirement now asks for the day it was
    # rejected, so it should not read as a live warning here either.
    rejected_by_requirement: dict[str, dict] = {}
    requirement_ids = {requirement.id for _, requirement in rows}
    if requirement_ids:
        current_digest = {requirement.id: requirement.digest for _, requirement in rows}
        review_rows = await session.execute(
            select(
                RequirementEvidence.requirement_id,
                RequirementEvidence.digest,
                EvidenceReview.reason,
            )
            .join(EvidenceReview, EvidenceReview.evidence_id == RequirementEvidence.id)
            .where(
                RequirementEvidence.requirement_id.in_(requirement_ids),
                RequirementEvidence.review_state == EVIDENCE_REJECTED,
                EvidenceReview.decision == EVIDENCE_REJECTED,
            )
            .order_by(EvidenceReview.created_at.desc())
        )
        for requirement_id, digest, reason in review_rows:
            if digest != current_digest.get(requirement_id):
                continue
            entry = rejected_by_requirement.setdefault(
                requirement_id, {"count": 0, "reason": reason}
            )
            entry["count"] += 1

    # `.order_by(SpecRequirement.identifier)` above sorts as text, so `FR-11` lands between `FR-1`
    # and `FR-2`. The data is right and the order reads as a defect, which costs a diagnosis every
    # time someone checks what a task is tied to. Sorted here rather than in SQL: a natural sort
    # has no portable expression across SQLite and Postgres, and the rows per task are few. The
    # query's own ordering is kept — it is what makes this sort's stability meaningful.
    def _natural(item: dict) -> list:
        # Digit runs compared as numbers, everything else as text. Nothing constrains an
        # operator-authored identifier to the `XX-N` shape, so a wholly non-numeric one has to
        # come out somewhere deterministic rather than raise.
        parts = re.split(r"(\d+)", item["identifier"])
        return [(1, int(part), "") if part.isdigit() else (0, 0, part) for part in parts]

    by_task: dict[str, list] = {}
    for task_id, requirement in rows:
        stated = wording.get(requirement.document_id, {}).get(requirement.key) or {}
        rejection = rejected_by_requirement.get(requirement.id)
        by_task.setdefault(task_id, []).append(
            {
                "identifier": requirement.identifier,
                "requirement_id": requirement.id,
                "document_id": requirement.document_id,
                "state": requirement.state,
                "anchor": requirement.anchor,
                "key": requirement.key,
                # Null where the document no longer words it — which is what a retired requirement
                # is, and the honest answer rather than a stale copy.
                "statement": stated.get("statement"),
                "modal": stated.get("modal"),
                # True only for evidence rejected against the requirement's *current* digest — see
                # the query above. Kept independent of coverage's `rejected` state: this stays true
                # even after a later acceptance moves `state` on to `verified`.
                "has_rejected_evidence": rejection is not None,
                "rejected_evidence_count": rejection["count"] if rejection else 0,
                "latest_rejection_reason": rejection["reason"] if rejection else None,
            }
        )

    references = await session.execute(
        select(TaskRequirementReference).where(TaskRequirementReference.task_id.in_(task_ids))
    )
    unresolved: dict[str, list] = {}
    for reference in references.scalars().all():
        unresolved.setdefault(reference.task_id, []).append(
            {"reference": reference.reference, "reason": reference.reason}
        )

    for links in by_task.values():
        links.sort(key=_natural)

    for response in responses:
        response.requirement_links = by_task.get(response.id, [])
        response.unresolved_requirements = unresolved.get(response.id, [])
        # Derived from the links already fetched — no extra query. Unresolved references are
        # deliberately excluded: they round-trip as `unresolved_requirements`, and including them
        # here would invite a GET→PATCH cycle to resubmit a reference that already failed.
        response.requirement_ids = [item["identifier"] for item in response.requirement_links]
    return responses


async def _attach_dependencies(
    session: AsyncSession, responses: List[TaskResponse], *, project_id: str
) -> List[TaskResponse]:
    """Fill in what each task depends on, what depends on it, and whether that's worth flagging.

    Batched across the whole page for the same reason `_attach_requirements` is (task 7.1): one
    query for every edge touching this page, not one per task. `dependency_state` (task 7.2) is
    derived from the same rows rather than a second call into `dependency_gate.evaluate` — that
    module answers "may this task start", scoped to one task; this answers "what should the read
    model say", scoped to a page, and the two are the same join read two different ways.
    """
    task_ids = [response.id for response in responses]
    if not task_ids:
        return responses

    edges = (
        await session.execute(
            select(TaskDependency.task_id, TaskDependency.depends_on_task_id).where(
                TaskDependency.project_id == project_id,
                (
                    TaskDependency.task_id.in_(task_ids)
                    | TaskDependency.depends_on_task_id.in_(task_ids)
                ),
            )
        )
    ).all()
    if not edges:
        return responses

    other_ids = {tid for pair in edges for tid in pair} - set(task_ids)
    by_response = {response.id: response for response in responses}
    known = {
        response.id: {
            "id": response.id,
            "title": response.title,
            "status": response.status,
            "spec_document_id": response.spec_document_id,
        }
        for response in responses
    }
    if other_ids:
        other_rows = await session.execute(
            select(Task.id, Task.title, Task.status, Task.spec_document_id).where(
                Task.id.in_(other_ids)
            )
        )
        for other_id, title, other_status, other_document_id in other_rows:
            known[other_id] = {
                "id": other_id,
                "title": title,
                "status": other_status,
                "spec_document_id": other_document_id,
            }

    prerequisites: dict[str, list] = {}
    dependents: dict[str, list] = {}
    for task_id, depends_on_task_id in edges:
        if task_id in by_response and depends_on_task_id in known:
            prerequisites.setdefault(task_id, []).append(known[depends_on_task_id])
        if depends_on_task_id in by_response and task_id in known:
            dependents.setdefault(depends_on_task_id, []).append(known[task_id])

    for response in responses:
        own_prerequisites = prerequisites.get(response.id, [])
        response.prerequisites = [TaskDependencyRef(**entry) for entry in own_prerequisites]
        response.dependents = [
            TaskDependencyRef(**entry) for entry in dependents.get(response.id, [])
        ]
        rejected = [
            p for p in own_prerequisites if p["status"] == dependency_gate.PERMANENTLY_UNMET_STATUS
        ]
        unmet = [
            p
            for p in own_prerequisites
            if p["status"] != dependency_gate.MET_STATUS
            and p["status"] != dependency_gate.PERMANENTLY_UNMET_STATUS
        ]
        if response.status == "in_progress" and (rejected or unmet):
            # Already started, and a prerequisite no longer clears the gate that let it start —
            # design D8's "flagged, not stopped". The gate itself only guards `-> in_progress`, so
            # this state is read-model-only: nothing in `task_transition_service` reacts to it.
            response.dependency_state = "running_on_regressed"
        elif rejected:
            response.dependency_state = "gated_on_rejected"
        elif unmet:
            response.dependency_state = "gated"
        else:
            response.dependency_state = None
    return responses


async def _attach_awaiting_answer(
    session: AsyncSession, responses: List[TaskResponse], *, project_id: str
) -> List[TaskResponse]:
    """Say which tasks have a live run waiting on an unanswered question (F14).

    A task only reaches `blocked` when the asking run *ends* with the question still open —
    `block_task_for_question` is reached from `run_divergence.evaluate_run_end` and nowhere else.
    That is the right moment to change a status, but it means the entire time an agent sits waiting
    for the operator, which is the whole point of `ask_user`, the board reads `in_progress` with no
    `blocked_reason`: it claims the work is progressing while nothing is happening and the answer
    is on the operator's desk.

    So this reports the wait without touching the status. Derived per request and never stored: the
    durable record is the question row, and a second copy on the task would be one more thing that
    can disagree with it — the same reasoning as `has_open_divergence` and `dependency_state`.

    Two ways a task is waiting, both counted:

    * a **running** run bound to the task asked it — the case the status cannot yet show;
    * the question already names the task in `blocked_task_id` — the parked case, so a `blocked`
      card and an `in_progress` one waiting on the same thing read alike.

    Only `blocking=True`, unanswered, undeclined questions count, matching
    `unanswered_blocking_question` exactly: a non-blocking `ask_user` is a note the agent left
    while carrying on, and a declined question is one the operator has already closed.
    """
    task_ids = {response.id for response in responses}
    if not task_ids:
        return responses

    rows = await session.execute(
        select(Question, Run.task_id)
        .outerjoin(Run, Run.id == Question.created_by_run_id)
        .where(
            Question.project_id == project_id,
            Question.blocking.is_(True),
            Question.answered.is_(False),
            Question.declined.is_(False),
        )
        .where(
            Question.blocked_task_id.in_(task_ids)
            | ((Run.status == "running") & Run.task_id.in_(task_ids))
        )
        .order_by(Question.created_at, Question.batch_index)
    )
    # Earliest first and `setdefault`: a run that asked several is waiting on the first thing it
    # got stuck on, which is the more useful thing to name — the same choice
    # `unanswered_blocking_question` makes with its ORDER BY.
    waiting: dict[str, Question] = {}
    for question, run_task_id in rows:
        for candidate in (question.blocked_task_id, run_task_id):
            if candidate in task_ids:
                waiting.setdefault(candidate, question)

    for response in responses:
        question = waiting.get(response.id)
        if question is not None:
            response.awaiting_answer_reason = reason_from_question(question)
    return responses


async def _attach_assignee_liveness(
    session: AsyncSession, responses: List[TaskResponse], *, project_id: str
) -> List[TaskResponse]:
    """Make the board agree with the rail and the panels about what an agent is doing (F6, F17).

    Both of this response's assignee fields were derived from `AgentHeartbeat` rows alone, and a
    Hub-spawned agent writes none — so a card whose agent was mid-run reported `assignee_status:
    "idle"` and `assignee_last_seen: null` about an agent that was, at that moment, working. The
    stress-test drive caught the status half as F6 and the timestamp half as F17.

    `agents.py` and `projects.py` already correct for this, each with a comment saying the two must
    not disagree about the same agent. The board was the third surface and the only one still
    reading heartbeats alone, so its cards contradicted the rail beside them.

    The precedence is copied from `agents.py`, deliberately and exactly: a live `Run` row wins over
    whatever the heartbeat said, including a `stalled` one, and clears the status message with it.
    That is not a claim that a run row is better evidence of health than a heartbeat — it is the
    only way the board and the rail can describe one agent the same way, which is the whole of what
    F6 reported. If that precedence is ever reconsidered it has to be reconsidered in one place for
    both surfaces, not softened here.

    `last_seen` is only ever filled in, never overwritten downward, because a missing timestamp is
    the defect and any observed one is an improvement on it.

    This also makes D12's live-pulse cue reachable rather than merely specified: `TaskCard` pulses
    on `assignee_status === "running"`, which since the watchdog was deleted no managed agent could
    ever report.
    """
    assignees = {response.assignee for response in responses if response.assignee}
    if not assignees:
        return responses

    running = await session.execute(
        select(Run.agent).where(
            Run.project_id == project_id,
            Run.agent.in_(assignees),
            Run.status == "running",
        )
    )
    agents_with_active_run = {name for (name,) in running}
    activity = await latest_activity_by_agent(session, project_id, assignees)

    for response in responses:
        if not response.assignee:
            continue
        if response.assignee in agents_with_active_run:
            response.assignee_status = "running"
            response.assignee_status_msg = None
        seen = activity.get(response.assignee)
        if seen is not None:
            response.assignee_last_seen = seen
    return responses


async def _tasks_with_open_divergence(
    session: AsyncSession, project_id: str, task_ids: set[str]
) -> set[str]:
    """Which of `task_ids` currently have a run that dropped them and nothing since.

    Computed rather than stored. The durable record is the divergence row; a flag on the task would
    be a second copy of the same fact, and the first thing it would do is disagree with it.
    """
    if not task_ids:
        return set()
    result = await session.execute(
        select(RunDivergence.task_id)
        .where(RunDivergence.project_id == project_id)
        .where(RunDivergence.task_id.in_(task_ids))
        .where(RunDivergence.resolved_at.is_(None))
        .distinct()
    )
    return {row[0] for row in result}


async def _latest_integrations_by_task(
    session: AsyncSession, project_id: str, task_ids: set[str]
) -> dict[str, TaskIntegration]:
    """The newest integration attempt per task, for the tasks that have ever had one.

    Same shape as `_latest_heartbeats_by_agent`: one query for the whole page rather than one per
    task, ordered newest-first so the first row seen per task is the one kept.
    """
    if not task_ids:
        return {}
    result = await session.execute(
        select(TaskIntegration)
        .where(
            TaskIntegration.project_id == project_id,
            TaskIntegration.task_id.in_(task_ids),
        )
        .order_by(TaskIntegration.task_id, TaskIntegration.created_at.desc())
    )
    latest: dict[str, TaskIntegration] = {}
    for row in result.scalars().all():
        latest.setdefault(row.task_id, row)
    return latest


async def _latest_heartbeats_by_agent(
    session: AsyncSession,
    project_id: str,
    agent_names: set[str],
) -> dict[str, AgentHeartbeat]:
    if not agent_names:
        return {}

    result = await session.execute(
        select(AgentHeartbeat)
        .where(
            AgentHeartbeat.project_id == project_id,
            AgentHeartbeat.agent.in_(agent_names),
        )
        .order_by(AgentHeartbeat.agent, AgentHeartbeat.timestamp.desc())
    )
    heartbeats: dict[str, AgentHeartbeat] = {}
    for heartbeat in result.scalars().all():
        heartbeats.setdefault(heartbeat.agent, heartbeat)
    return heartbeats


async def _authorize_loop_task_creation(
    session: AsyncSession, project_id: str, loop_id: str, actor: Actor, task_body: TaskCreate
) -> None:
    """Who may add a task directly to a loop's queue (`2026-08-18-a-loop-writes-its-own-queue`,
    design D1/D7/D8/D10/D12).

    D8 collapses "creator" into `Loop`'s own `AIJob.agent` — there is no separate creator field,
    deliberately, so the operator is always exempt and every other caller is measured against that
    one string.

    D10 generalises D7's "first fire" boundary into a consequence of `Loop.control` (task A1.4):
    control defaults to the operator, so a self-created loop whose control was never delegated
    still needs the operator once it has fired — the same outcome D7 stated directly. Before the
    first fire, the creator's own call is indistinguishable from `create_loop` accepting its
    initial queue (design D2's "definition window") and is let through regardless of delegation,
    exactly as it always was. Once delegated (`POST /loops/{id}/control`), the creator decides for
    itself at any point, `run_count` included — D10's "the creator can decide for himself".

    D12 (task A3.1): a loop that has already ended refuses EVERY caller, the operator included —
    unlike the checks below, which exempt the operator, this is not "who may extend the queue" but
    "does the queue still exist to extend". `Loop.ending_state` is the definitive stopped signal
    (set once, at the same site as `stop_reason`/`stopped_at`, only by the loop's own termination
    path — an operator `toggle_job` pause leaves all three `None`, deliberately: D6 rejected a
    third "paused" state, so a merely-disabled job is not "stopped" in this design's vocabulary).
    The refusal echoes the submitted task back (A3.2) so the caller can resubmit it as one of a new
    loop's `initial_tasks` — D12 explicitly rejects reviving the stopped loop itself, so nothing is
    created automatically here.

    D15 (`2026-08-18-a-loop-writes-its-own-queue`'s A5.3, closed by the 2026-08-19/20 autonomous
    run's P5): matching `actor.agent` to `job.agent` as bare strings, with neither ever checked
    against the `agents` table, meant whoever the *name* currently belonged to controlled the
    loop — not whoever currently holds it as a live `Agent` row. An archived creator's own name
    is still on `job.agent` forever (agent rows are never deleted or renamed), so a `Run` minted
    under that name — however it came to be minted — kept the loop's creator authority after the
    agent behind it was archived. The join below closes that: the name match is necessary but no
    longer sufficient, the creator must also currently resolve to an open `Agent`. Operator
    decision: archiving strips this privilege outright; it is not offered to whoever the name
    might belong to next, because — per `agent-configuration`'s spec and the guard now in
    `trigger_agent_directly` — no run can be minted under an archived name again anyway.
    """
    loop = await session.get(Loop, loop_id)
    if loop is None or loop.project_id != project_id:
        raise HTTPException(status_code=404, detail="Loop not found")
    if loop.ending_state is not None:
        raise HTTPException(
            status_code=403,
            detail={
                "message": (
                    f"This loop stopped ({loop.stop_reason or loop.ending_state}) at "
                    f"{loop.stopped_at.isoformat() if loop.stopped_at else 'an unknown time'} "
                    "and its queue is closed. It will not be revived — create a new loop and "
                    "pass this task as one of its initial_tasks instead."
                ),
                "code": "loop_stopped",
                "ending_state": loop.ending_state,
                "stop_reason": loop.stop_reason,
                "stopped_at": loop.stopped_at.isoformat() if loop.stopped_at else None,
                "offered_task": {
                    "title": task_body.title,
                    "description": task_body.description,
                    "priority": task_body.priority,
                    "assignee": task_body.assignee,
                    "requirements": task_body.requirements,
                    "requirement_ids": task_body.requirement_ids,
                    "spec_document": task_body.spec_document,
                    "acceptance_criteria": task_body.acceptance_criteria,
                    "deliverables": task_body.deliverables,
                    "notes": task_body.notes,
                },
            },
        )
    if actor.is_operator:
        return
    job = await session.get(AIJob, loop.job_id)
    creator_denied = HTTPException(
        status_code=403,
        detail=(
            "Only this loop's creator, or the operator, may add tasks to its queue "
            "directly. Use send_message to ask the creator to add it instead."
        ),
    )
    if job is None or actor.agent != job.agent:
        raise creator_denied
    # A missing `Agent` row is deliberately NOT refused here — a `Run` carrying a name with no
    # roster entry at all is the pre-existing, unrelated shape every other actor-derived test in
    # this codebase already relies on (`_active_run`-style fixtures, and self-registered agents
    # generally, never require a persisted `Agent` row to hold a run). Only a row that positively
    # exists and reads archived strips the privilege — that is the one state D15 is actually
    # about: a name whose original owner is provably gone.
    creator_row = (
        await session.execute(
            select(Agent).where(Agent.project_id == project_id, Agent.name == job.agent)
        )
    ).scalar_one_or_none()
    if creator_row is not None and creator_row.lifecycle == "archived":
        raise creator_denied
    delegated_to_creator = loop.control == "creator"
    if delegated_to_creator:
        return
    if job.run_count > 0:
        raise HTTPException(
            status_code=403,
            detail=(
                "This loop has already fired at least once — adding directly to its own queue "
                "now needs operator approval. Use ask_user to ask the operator to add it, "
                "naming the task and why this loop needs it."
            ),
        )


async def create_task_for_actor(
    body: TaskCreate,
    *,
    project_id: str,
    assigner: Optional[str],
    created_by_run_id: Optional[str],
    actor: Actor,
    session: AsyncSession,
) -> TaskResponse:
    # Honor a client-supplied id when present so the MCP `create_task` tool
    # can return the same id the Hub stored. Falls back to a fresh short id
    # for clients that don't supply one (e.g. direct API users).
    # A lifecycle that can be entered anywhere is not a lifecycle (design D10). Without this, a
    # caller creates a task already `approved` and never transitions at all, so no rule about
    # transitions can reach it. This is the single `Task(` construction site, so one guard covers
    # both the operator route and the agent plane.
    guard_entry_status(body.status)

    if body.loop_id is not None:
        await _authorize_loop_task_creation(session, project_id, body.loop_id, actor, body)

    # Resolved before the task exists. A create that stored the task and then refused its
    # requirements would leave work on the board whose author believes it is linked.
    try:
        named = (
            await resolve_identifiers(
                session, project_id, body.requirement_ids, document_path=body.spec_document
            )
            if body.requirement_ids
            else []
        )
    except LinkRefusedError as refusal:
        raise HTTPException(status_code=422, detail=str(refusal)) from refusal

    # Which document this work is against, so an agent given the task can reach it. `spec_document`
    # only ever disambiguated `requirement_ids` before, and the column was written solely by
    # `spec_tasks.materialise` — so the turn context could name a document for a task a document
    # *declared* and for no other, and an agent that decomposed its own work got nothing.
    #
    # Falls back to the document the named requirements agree on, because a task tracing to one
    # document's requirements is against that document whether or not the caller said so. Where
    # they disagree, nothing is recorded: guessing which one the work is against is worse than
    # leaving the agent to ask.
    document_ids = {row.document_id for row in named if row.document_id}
    spec_document_id = next(iter(document_ids)) if len(document_ids) == 1 else None

    task_id = body.id or f"task-{short_id()}"
    task = Task(
        id=task_id,
        project_id=project_id,
        title=body.title,
        description=body.description,
        status=body.status,
        priority=body.priority,
        assignee=body.assignee,
        assigner=assigner,
        requirements=body.requirements,
        acceptance_criteria=body.acceptance_criteria,
        deliverables=body.deliverables,
        notes=body.notes,
        created_by_run_id=created_by_run_id,
        spec_document_id=spec_document_id,
        loop_id=body.loop_id,
    )
    session.add(task)
    try:
        await session.commit()
    except IntegrityError as e:
        # Another writer beat us to this id (extremely unlikely with an 8-hex
        # suffix, but possible across distributed CLI + Hub). Reject with 409
        # so the caller can decide whether to retry with a fresh id.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task id '{task_id}' already exists",
        ) from e
    link_actor = SpecActor(
        kind="agent" if created_by_run_id else "operator",
        name=assigner or "",
        run_id=created_by_run_id,
    )
    await link(session, task, named, actor=link_actor)
    # The free-text list is converted too, so an agent still filling `requirements` with
    # `"FR-8 — initialize-members"` gets real links instead of a string that resolves to nothing.
    # Never a refusal: a free-text field that starts rejecting values breaks every caller that was
    # using it as prose.
    await absorb_free_text(session, task, body.requirements, actor=link_actor)
    await session.commit()

    await sse_manager.broadcast(project_id, "task_created", {"id": task.id, "title": body.title})
    await persist_event(
        session,
        project_id,
        "task_created",
        {"id": task.id, "title": body.title},
        agent=body.assignee,
    )
    await session.refresh(task)
    heartbeats = await _latest_heartbeats_by_agent(
        session,
        project_id,
        {task.assignee} if task.assignee else set(),
    )
    responses = await _attach_requirements(
        session,
        [_task_response(task, heartbeats.get(task.assignee) if task.assignee else None)],
        project_id=project_id,
    )
    responses = await _attach_awaiting_answer(session, responses, project_id=project_id)
    responses = await _attach_assignee_liveness(session, responses, project_id=project_id)
    return responses[0]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    return await create_task_for_actor(
        body,
        project_id=project_id,
        assigner=body.assigner,
        created_by_run_id=None,
        actor=operator(),
        session=session,
    )


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    agent: Optional[str] = Query(None),
    task_status: Optional[str] = Query(None, alias="status"),
    spec_document_id: Optional[str] = Query(None),
    exclude_archived_completed: bool = Query(False),
    loop_id: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    q = select(Task).where(Task.project_id == project_id)
    if agent:
        q = q.where(Task.assignee == agent)
    if task_status:
        q = q.where(Task.status == task_status)
    if spec_document_id:
        q = q.where(Task.spec_document_id == spec_document_id)
    elif loop_id:
        q = q.where(Task.loop_id == loop_id)
    elif exclude_archived_completed:
        archived_ids = select(SpecDocument.id).where(
            SpecDocument.project_id == project_id,
            SpecDocument.phase == spec_lifecycle.ARCHIVED,
        )
        # `Task.spec_document_id.in_(archived_ids)` alone evaluates to SQL NULL, not false, for a
        # row whose `spec_document_id` is NULL — and `~(NULL & ...)` is NULL too, which a WHERE
        # clause treats as "drop the row," excluding exactly the unlinked tasks this route must
        # never exclude. `.isnot(None)` is a real boolean (never NULL), so it short-circuits the
        # `&` to a real `False` for those rows before `in_()` is ever evaluated on them.
        q = q.where(
            ~(
                Task.spec_document_id.isnot(None)
                & Task.spec_document_id.in_(archived_ids)
                & Task.status.in_(TERMINAL_FOR_BINDING)
            )
        )
    q = q.order_by(Task.created_at).offset(offset).limit(limit)
    result = await session.execute(q)
    tasks = result.scalars().all()
    heartbeats = await _latest_heartbeats_by_agent(
        session,
        project_id,
        {task.assignee for task in tasks if task.assignee},
    )
    diverged = await _tasks_with_open_divergence(session, project_id, {task.id for task in tasks})
    integrations = await _latest_integrations_by_task(
        session, project_id, {task.id for task in tasks}
    )
    responses = await _attach_requirements(
        session,
        [
            _task_response(
                task,
                heartbeats.get(task.assignee) if task.assignee else None,
                has_open_divergence=task.id in diverged,
                latest_integration=integrations.get(task.id),
            )
            for task in tasks
        ],
        project_id=project_id,
    )
    responses = await _attach_dependencies(session, responses, project_id=project_id)
    responses = await _attach_awaiting_answer(session, responses, project_id=project_id)
    return await _attach_assignee_liveness(session, responses, project_id=project_id)


@router.get("/board")
async def task_board(
    spec_document_id: Optional[str] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """One document's tasks, and the edges between them, in a single call (task 7.3, design D9).

    Omitting `spec_document_id` returns the "no document" board — every hand-made task, which per
    D5 can never have an edge. `edges` is a flat list alongside `tasks` rather than only nested
    inside each task's `prerequisites`/`dependents` (already present via `_attach_dependencies`):
    a layout algorithm wants the graph's edge set once, not reconstructed by walking every card.

    Batched the same way `list_tasks` is — one query for the tasks, one for the edges among them,
    regardless of how many cards the document declared. Must not N+1 its way to a layout.
    """
    project_id, _ = project
    q = select(Task).where(Task.project_id == project_id)
    if spec_document_id:
        q = q.where(Task.spec_document_id == spec_document_id)
    else:
        q = q.where(Task.spec_document_id.is_(None))
    q = q.order_by(Task.created_at)
    tasks = (await session.execute(q)).scalars().all()
    task_ids = {task.id for task in tasks}
    heartbeats = await _latest_heartbeats_by_agent(
        session, project_id, {task.assignee for task in tasks if task.assignee}
    )
    diverged = await _tasks_with_open_divergence(session, project_id, task_ids)
    integrations = await _latest_integrations_by_task(session, project_id, task_ids)
    responses = await _attach_requirements(
        session,
        [
            _task_response(
                task,
                heartbeats.get(task.assignee) if task.assignee else None,
                has_open_divergence=task.id in diverged,
                latest_integration=integrations.get(task.id),
            )
            for task in tasks
        ],
        project_id=project_id,
    )
    responses = await _attach_dependencies(session, responses, project_id=project_id)
    responses = await _attach_awaiting_answer(session, responses, project_id=project_id)
    responses = await _attach_assignee_liveness(session, responses, project_id=project_id)
    edges: List[dict] = []
    if task_ids:
        edge_rows = await session.execute(
            select(TaskDependency.task_id, TaskDependency.depends_on_task_id).where(
                TaskDependency.project_id == project_id,
                TaskDependency.task_id.in_(task_ids),
            )
        )
        edges = [
            {"task_id": task_id, "depends_on_task_id": depends_on_task_id}
            for task_id, depends_on_task_id in edge_rows
        ]
    return {
        "spec_document_id": spec_document_id,
        "tasks": responses,
        "edges": edges,
    }


@router.get("/boards")
async def task_boards(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The picker: every board that has tasks, with outstanding counts (task 7.4, design D9).

    One row per `spec_document_id` that has ever had a task materialised against it, plus a
    standing `null`-keyed row for hand-made tasks (D9's "no document" board) when any exist.
    `outstanding` excludes only the two terminal statuses (`run_task_binding.TERMINAL_FOR_BINDING`)
    — a `rejected` task is resolved, not outstanding, even though it never reached `approved`.
    """
    project_id, _ = project
    rows = await session.execute(
        select(Task.spec_document_id, Task.status).where(Task.project_id == project_id)
    )
    totals: dict[Optional[str], int] = {}
    outstanding: dict[Optional[str], int] = {}
    for spec_document_id, task_status in rows:
        totals[spec_document_id] = totals.get(spec_document_id, 0) + 1
        if task_status not in TERMINAL_FOR_BINDING:
            outstanding[spec_document_id] = outstanding.get(spec_document_id, 0) + 1

    document_ids = [doc_id for doc_id in totals if doc_id is not None]
    titles: dict[str, str] = {}
    if document_ids:
        doc_rows = await session.execute(
            select(SpecDocument.id, SpecDocument.title).where(SpecDocument.id.in_(document_ids))
        )
        titles = dict(doc_rows.all())

    boards = [
        {
            "spec_document_id": doc_id,
            "title": titles.get(doc_id) if doc_id is not None else None,
            "total": total,
            "outstanding": outstanding.get(doc_id, 0),
        }
        for doc_id, total in totals.items()
    ]
    # Documents first (creation order via id is arbitrary; sort by title for a stable picker),
    # the "no document" board last — it is the overflow bucket D9 describes, not a project.
    boards.sort(key=lambda board: (board["spec_document_id"] is None, board["title"] or ""))
    return {"boards": boards}


@router.get("/{task_id}/integrations")
async def task_integrations(
    task_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """What approving this task did to the repository, including the times it did nothing.

    "My approved work is not on main" needs an answer, and a skipped merge with a stated reason is
    that answer. Read-only: the record is append-only, and no route edits or removes one. Retrying
    appends a fresh attempt rather than revising a past one — see `retry_task_integration`.
    """
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project[0]:
        raise HTTPException(status_code=404, detail="Task not found")

    return await _integration_view(session, task_id)


@router.get("/{task_id}/integration-preview")
async def task_integration_preview(
    task_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """What approving this task *would* write, before the operator approves it (F9).

    Approving is the most consequential act in the product and the only one that changes the
    operator's repository: it cherry-picks the commit named by each accepted piece of evidence into
    the project's main branch. Driven end to end on 2026-08-23, that worked exactly as designed —
    and nothing on the successful path ever said it was about to happen. The refusal path was
    already legible ("no accepted evidence names a commit"); the *write* was not.

    So this answers the same question the merge itself will ask, from the same source
    (`task_integration.integration_targets` and `Project.main_branch`), and the drawer states the
    answer beside the approve control. Deliberately read-only and deliberately cheap: no git
    subprocess, no conflict probe — that is `requirement_gate`'s job at the moment of approval,
    where a refusal can still stop it. This is a sentence, not a second gate.

    `will_merge` is false with a stated `reason` for the two ordinary cases — a project with no
    main branch configured, and a task whose evidence names no commit — because both are supported
    project shapes and neither is an error.
    """
    project_id, _ = project
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found")

    from ... import task_integration

    project_row = await session.get(Project, project_id)
    main_branch = project_row.main_branch if project_row else None
    targets = await task_integration.integration_targets(session, task)

    if not main_branch:
        reason = task_integration.NO_MAIN_BRANCH
    elif not targets:
        reason = task_integration.NOTHING_TO_MERGE
    else:
        reason = ""

    return {
        "task_id": task.id,
        "main_branch": main_branch,
        "targets": [
            {"commit_sha": target.commit_sha, "source_branch": target.branch} for target in targets
        ],
        "will_merge": bool(main_branch and targets),
        "reason": reason,
    }


async def _integration_view(session: AsyncSession, task_id: str) -> dict:
    """The response both the read route and the retry route return.

    One shape, so the UI can render a retry's answer with the component it already has.
    """
    from ... import task_integration

    rows = await task_integration.history_for(session, task_id)
    return {
        "integrations": [
            {
                "id": row.id,
                "commit_sha": row.commit_sha,
                "source_branch": row.source_branch,
                "target_branch": row.target_branch,
                "outcome": row.outcome,
                "reason": row.reason,
                "rode_along_commits": (
                    row.rode_along_commits.split(",") if row.rode_along_commits else []
                ),
                "mechanism": row.mechanism,
                "actor_kind": row.actor_kind,
                "actor": row.actor,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.post("/{task_id}/integrations/retry")
async def retry_task_integration(
    task_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Attempt the merge again for an approved task whose work is not in the product.

    A skipped merge names something the operator then puts right — most often a main branch that was
    never chosen. Approving again cannot re-run it, because restating a status is a no-op, so
    without this the reason text asks for a remediation that accomplishes nothing.
    """
    project_id, _ = project
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        await retry_integration(session, task, operator())
    except TransitionRefusedError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.detail) from exc
    await session.commit()

    view = await _integration_view(session, task_id)
    # After the commit: `persist_event` commits, so an event emitted before it would publish a
    # merge that had not been written yet.
    await persist_event(
        session,
        project_id,
        "task_integration_retried",
        {
            "task_id": task_id,
            "outcomes": [row["outcome"] for row in view["integrations"]][-3:],
        },
    )
    await sse_manager.broadcast(project_id, "task_integration_retried", {"task_id": task_id})
    return view


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    heartbeats = await _latest_heartbeats_by_agent(
        session,
        project_id,
        {task.assignee} if task.assignee else set(),
    )
    diverged = await _tasks_with_open_divergence(session, project_id, {task.id})
    integrations = await _latest_integrations_by_task(session, project_id, {task.id})
    responses = await _attach_requirements(
        session,
        [
            _task_response(
                task,
                heartbeats.get(task.assignee) if task.assignee else None,
                has_open_divergence=task.id in diverged,
                latest_integration=integrations.get(task.id),
            )
        ],
        project_id=project_id,
    )
    responses = await _attach_dependencies(session, responses, project_id=project_id)
    responses = await _attach_awaiting_answer(session, responses, project_id=project_id)
    responses = await _attach_assignee_liveness(session, responses, project_id=project_id)
    return responses[0]


async def update_task_for_actor(
    task_id: str,
    body: TaskUpdate,
    *,
    project_id: str,
    actor: Actor,
    session: AsyncSession,
) -> TaskResponse:
    """The single choke point both routes share, and therefore where the machine lives.

    `actor` is explicit rather than an `Optional[str]` run id whose absence meant "operator"
    (design D2): those are different claims, and only one of them is an authorisation.
    """
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    if body.loop_id is not None:
        # Task.loop_id is write-once, set only at creation (design D14,
        # 2026-08-18-a-loop-writes-its-own-queue). A loop's queue history has to be able to answer
        # what work it was ever given — `stop_when_queue_empties` depends on that history staying
        # accurate — and reassignment would break it. Checked before any other field is touched, so
        # a refused update leaves the task genuinely unchanged rather than half-applied.
        raise HTTPException(
            status_code=403,
            detail="A task's loop assignment is set at creation and cannot be changed afterwards.",
        )
    # Set only when this call performed a transition — `contract`'s report on approval reads off it
    # below. A no-op restatement of the current status returns `None` from `apply_transition`, which
    # carries no advisories the same way it carries no new transition row.
    approval_report: List[Any] = []
    # **Before the transition, not after it** (finding F70). `_guard_reviewer_is_not_the_author`
    # refuses `-> under_review` while the task still names the agent that completed it, and the
    # remedy it names -- assign a different reviewer -- is most naturally done in the same PATCH
    # that sends the task to review. Applied afterwards, that one call was refused on the strength
    # of an assignee the same request was about to replace, and the operator had to make two.
    # Nothing between here and the transition reads the old value: `release_reason` and
    # `release_bindings_to` are about the task and its runs, not about who holds it.
    if "assignee" in body.model_fields_set:
        # `model_fields_set`, not `is not None` (finding F78). The guard immediately below names
        # two remedies -- reassign, or "clear the assignee to review it yourself" -- and read as
        # "None means leave it alone" the second one could not be expressed at all: `assignee:
        # null` was indistinguishable from an omitted field, so the operator's PATCH came back
        # `200` with the author still in it and the guard refused them again. Omitting the field
        # still leaves the holder untouched, which is the half of the old reading that was right:
        # a PATCH about the priority must not unassign anybody. `""` arrives here as `None` --
        # the schema normalises it -- so the column never grows a second spelling of "nobody".
        task.assignee = body.assignee
    if body.status is not None:
        if body.status == STATUS_BLOCKED and not actor.is_operator:
            # A block is observed, never asserted (design D3). An agent that could declare itself
            # waiting on a person could claim to be waiting on one it never asked — the one claim a
            # completion gate would most reward, and the reason `blocked` is also withheld from the
            # MCP `update_task` signature. The map permits the edge to a run because the *runtime*
            # takes it on the run's behalf; this is what stops the agent asking for it directly.
            raise HTTPException(
                status_code=403,
                detail=(
                    "A task is recorded as waiting on a person because AgentWeave saw the run end "
                    "with an unanswered blocking question, not because an agent said so. Use "
                    "ask_user to ask, and the task will be parked for you."
                ),
            )
        # Raises TransitionRefusedError — an illegal move, or one this actor may not make — which the
        # exception handler turns into 409/403. A refusal cannot leave a half-applied update behind:
        # the assignee written above is *staged*, not committed, and `get_session` closes the session
        # on the way out, which rolls the transaction back. (This comment used to say nothing had
        # been mutated at this point, which stopped being true when F70 moved the assignee write
        # above the transition — the guarantee is the same, the reason for it is not.)
        transition = await apply_transition(session, task, body.status, actor)
        approval_report = list(getattr(transition, "reported_advisories", None) or [])
        # Every exit from the waiting status drops the text, whichever exit it was — released,
        # reassigned or abandoned. A reason outliving its block describes something that already
        # arrived.
        if body.status != STATUS_BLOCKED:
            release_reason(task)
        else:
            task.blocked_reason = body.blocked_reason
        # There is no more working to do at these, so anything that stayed bound would keep
        # attributing turns to a task the operator has already decided about — and put stalled
        # markers on work they approved (design D7). `release_bindings_to`, not the conversation
        # release it used to call: a turn already sitting in the inbound queue carries the same
        # claim and was not covered, so approving a task did not stop the turn queued against it
        # from arriving afterwards (F79).
        if body.status in TERMINAL_FOR_BINDING:
            await release_bindings_to(session, task)
    if body.priority is not None:
        task.priority = body.priority
    if body.description is not None:
        task.description = body.description
    if body.notes is not None:
        task.notes = body.notes
    if body.divergence_policy is not None or "escalation_agent" in body.model_fields_set:
        # The operator's, not the agent's. An agent able to set its own task's policy to `surface`
        # could disarm the check that exists to catch it dropping the work — the same reason no
        # agent-facing operation binds a run (`2026-08-10-run-task-binding`, design D2).
        if not actor.is_operator:
            raise HTTPException(
                status_code=403,
                detail=(
                    "How a dropped task is answered is the operator's setting. An agent cannot "
                    "change its own task's divergence policy or escalation agent."
                ),
            )
        if body.divergence_policy is not None:
            task.divergence_policy = body.divergence_policy
        if "escalation_agent" in body.model_fields_set:
            task.escalation_agent = body.escalation_agent
    if body.requirement_ids:
        try:
            named = await resolve_identifiers(
                session, project_id, body.requirement_ids, document_path=body.spec_document
            )
        except LinkRefusedError as refusal:
            raise HTTPException(status_code=422, detail=str(refusal)) from refusal
        await link(
            session,
            task,
            named,
            actor=SpecActor(
                kind="operator" if actor.is_operator else "agent",
                name=actor.agent or "",
                run_id=actor.run_id,
            ),
        )
    task.updated = datetime.now(timezone.utc)
    # Kept as the materialised latest writer (D4 of the proposal's impact notes). The rules read the
    # append-only history instead; this stays for existing consumers and is not what governs.
    task.updated_by_run_id = actor.run_id
    await session.commit()
    await session.refresh(task)
    await sse_manager.broadcast(project_id, "task_updated", {"id": task_id, "status": task.status})
    await persist_event(
        session,
        project_id,
        "task_updated",
        {"id": task_id, "status": task.status},
        agent=task.assignee,
    )
    await session.refresh(task)
    heartbeats = await _latest_heartbeats_by_agent(
        session,
        project_id,
        {task.assignee} if task.assignee else set(),
    )
    diverged = await _tasks_with_open_divergence(session, project_id, {task.id})
    integrations = await _latest_integrations_by_task(session, project_id, {task.id})
    responses = await _attach_requirements(
        session,
        [
            _task_response(
                task,
                heartbeats.get(task.assignee) if task.assignee else None,
                has_open_divergence=task.id in diverged,
                latest_integration=integrations.get(task.id),
                approval_report=approval_report,
            )
        ],
        project_id=project_id,
    )
    responses = await _attach_dependencies(session, responses, project_id=project_id)
    responses = await _attach_awaiting_answer(session, responses, project_id=project_id)
    responses = await _attach_assignee_liveness(session, responses, project_id=project_id)
    return responses[0]


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    body: TaskUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    return await update_task_for_actor(
        task_id,
        body,
        project_id=project_id,
        actor=operator(),
        session=session,
    )


@router.get("/transitions/allowed")
async def allowed_transitions(
    project: Tuple[str, str] = Depends(get_project),
):
    """The operator's own view of the transition map (design D13).

    Served from the same declaration the service enforces, so the control cannot offer a move that
    is then refused, and the client never holds a second copy of the map. One fetch per session
    rather than one per card — a board of forty tasks in the same status has one answer, not forty.
    """
    return {"actor_kind": ACTOR_OPERATOR, "transitions": allowed_map_for(ACTOR_OPERATOR)}


@router.get("/divergences/recent")
async def recent_divergences(
    limit: int = Query(50, ge=1, le=500),
    open_only: bool = Query(False),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Runs that ended holding work nobody moved.

    A read of the record rather than of the SSE stream, because the operator needs to see what
    happened while they were not watching — which is the whole reason this is a table and not only
    a broadcast (design D10).

    Newest first, and `resolved_at` is included rather than filtered by default: "this was dropped
    and then picked up" is as worth seeing as "this is still dropped".
    """
    project_id, _ = project
    q = select(RunDivergence).where(RunDivergence.project_id == project_id)
    if open_only:
        q = q.where(RunDivergence.resolved_at.is_(None))
    q = q.order_by(RunDivergence.sequence.desc()).limit(limit)
    result = await session.execute(q)
    return [
        {
            "id": row.id,
            "run_id": row.run_id,
            "agent": row.agent,
            "task_id": row.task_id,
            "task_status_at_end": row.task_status_at_end,
            "run_exit_status": row.run_exit_status,
            "policy_applied": row.policy_applied,
            "outcome": row.outcome,
            "response_run_id": row.response_run_id,
            "previous_assignee": row.previous_assignee,
            "created_at": row.created_at,
            "resolved_at": row.resolved_at,
        }
        for row in result.scalars().all()
    ]


class DependencyRequest(BaseModel):
    """One edge, named by task ids.

    Ids rather than document keys: keys are the document's own vocabulary, minted by the agent that
    authored the decomposition, and an operator declaring an ordering between two cards is looking
    at ids. `spec_tasks` keeps its key resolution and hands the shared writer resolved ids exactly
    as this does.
    """

    depends_on: str = Field(max_length=64)

    model_config = {"extra": "forbid"}


@router.post("/{task_id}/dependencies", status_code=status.HTTP_201_CREATED)
async def add_task_dependency(
    task_id: str,
    body: DependencyRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Declare that this task depends on another (F36).

    Until this existed, dependency rows were written in exactly one place — `spec_tasks.py`, reached
    only when an approved document carried `depends_on` keys. `TaskUpdate` refused the field with
    `422 extra_forbidden` and no route reached it, so an operator could not say "B needs A" about
    two tasks they had made, and `dependency_gate`, the Dependencies board tab, two tables and the
    `prerequisites`/`dependents` fields on every task response were reachable only if an agent
    happened to author the right keys. In the sweep the agent authored no ordering at all, so the
    graph came out empty and the gate was never exercisable.

    Refusals name what is wrong, following `refusal_detail`'s standard: an operator told only
    "invalid" tries the same thing again.
    """
    project_id, _ = project
    outcome = await task_dependency_writer.add_dependency(
        session, project_id, task_id, body.depends_on
    )

    if outcome == task_dependency_writer.SELF:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="a task cannot depend on itself",
        )
    if outcome == task_dependency_writer.MISSING:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"one of these tasks does not exist in this project: {task_id}, {body.depends_on}"
            ),
        )
    if outcome == task_dependency_writer.CYCLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"task {body.depends_on} already depends on {task_id}, directly or through others, "
                f"so this would make each wait on the other forever."
            ),
        )

    await session.commit()
    # `duplicate` is a 201 too. Declaring an edge that exists is a restatement of something already
    # true, not a conflict, and an operator who clicks twice has not made a mistake.
    return {"task_id": task_id, "depends_on": body.depends_on, "outcome": outcome}


@router.delete("/{task_id}/dependencies/{depends_on}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_task_dependency(
    task_id: str,
    depends_on: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Withdraw a declared dependency, so a wrong one is not permanent (the shape of F37).

    A 404 when there was no such edge, rather than a silent success: an operator removing an edge
    that is not there has misidentified something, and saying so is cheaper than letting them
    believe the graph changed.
    """
    project_id, _ = project
    removed = await task_dependency_writer.remove_dependency(
        session, project_id, task_id, depends_on
    )
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"task {task_id} does not depend on {depends_on}",
        )
    await session.commit()
