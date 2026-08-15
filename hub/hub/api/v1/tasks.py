"""Task endpoints — POST/GET/GET{id}/PATCH."""

import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ... import project_workspace, spec_reading
from ...agent_status import effective_heartbeat_status
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import (
    AgentHeartbeat,
    EvidenceReview,
    RequirementEvidence,
    RunDivergence,
    SpecRequirement,
    Task,
    TaskIntegration,
    TaskRequirementLink,
    TaskRequirementReference,
)
from ...requirement_evidence import REJECTED as EVIDENCE_REJECTED
from ...requirement_links import LinkRefusedError, absorb_free_text, link, resolve_identifiers
from ...run_task_binding import (
    TERMINAL_FOR_BINDING,
    release_conversations_bound_to,
    release_reason,
)
from ...schemas.tasks import TaskCreate, TaskIntegrationSummary, TaskResponse, TaskUpdate
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

    # A requirement whose only evidence was rejected reads identically to one nobody has ever
    # attempted — `requirement_coverage._state` falls through to `in_progress` either way, because
    # coverage's precedence has no state for "tried and rejected". Approving the task above it would
    # be silent about that. Scoped to the current digest, the same way coverage itself is: a
    # rejection against a since-reworded requirement said nothing about what the requirement now
    # asks for the day it was rejected, so it should not read as a live warning here either.
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
                # the query above. `state` alone cannot say this: it is coverage's `in_progress`
                # either way.
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


async def create_task_for_actor(
    body: TaskCreate,
    *,
    project_id: str,
    assigner: Optional[str],
    created_by_run_id: Optional[str],
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
        session=session,
    )


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    agent: Optional[str] = Query(None),
    task_status: Optional[str] = Query(None, alias="status"),
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
    return await _attach_requirements(
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
        # exception handler turns into 409/403. Nothing has been mutated at that point, so the
        # refusal cannot leave a half-applied update behind.
        await apply_transition(session, task, body.status, actor)
        # Every exit from the waiting status drops the text, whichever exit it was — released,
        # reassigned or abandoned. A reason outliving its block describes something that already
        # arrived.
        if body.status != STATUS_BLOCKED:
            release_reason(task)
        else:
            task.blocked_reason = body.blocked_reason
        # There is no more working to do at these, so a thread that stayed bound would keep
        # attributing turns to a task the operator has already decided about — and put stalled
        # markers on work they approved (design D7).
        if body.status in TERMINAL_FOR_BINDING:
            await release_conversations_bound_to(session, task)
    if body.priority is not None:
        task.priority = body.priority
    if body.assignee is not None:
        task.assignee = body.assignee
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
            )
        ],
        project_id=project_id,
    )
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
