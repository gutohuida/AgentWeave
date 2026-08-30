"""What a run is working on, and whether it did it.

Before this module a run did not know what task it was for. `Run` carried project, agent, session,
conversation, pid and heartbeat and nothing about the work, so the only way a task's status could
stay current was an agent remembering to say so — not a discipline problem but a missing edge in
the data model (`openspec/changes/2026-08-10-run-task-binding/`, and the exploration
`2026-08-10-enforcing-the-development-cycle.md`).

Two capabilities live here, and they are the same edge read in both directions:

**Binding** — the runtime attaches a run to the one task that caused it, and moves that task to
`in_progress` itself. The agent is never asked, so it cannot forget.

**The boundary question** — when the run ends, did it move its task? Asked at the run boundary,
which AgentWeave owns for every runner, rather than inside the agent, which is what makes it
enforcement rather than instruction.

Deliberately narrow: this module resolves, binds, and answers. It starts no processes and writes no
divergence records — spawning a response to a divergence needs the trigger path, and a module that
both decides and spawns would be impossible to test without one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, NamedTuple, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import InboundQueueEntry, Question, Run, SpecDocument, Task, TaskTransition
from .sse import sse_manager
from .task_transition_service import (
    ORIGIN_ACTOR,
    ORIGIN_RUNTIME,
    TransitionRefusedError,
    apply_transition,
)
from .task_transitions import (
    STATUS_BLOCKED,
    TERMINAL_STATUSES,
    allowed_targets,
    operator,
    run_actor,
)
from .utils import persist_event

# --------------------------------------------------------------------------------------
# What a task says should happen when work bound to it is dropped
# --------------------------------------------------------------------------------------

#: Record it and show it. Starts nothing, spends nothing.
POLICY_SURFACE = "surface"
#: Run the same agent once more, bound to the same task.
POLICY_RETRY = "retry"
#: Reassign to the task's escalation agent and run that one.
POLICY_ESCALATE = "escalate"

#: Pinned to the column's declared default in `db/models.py` by test. `surface` being the default is
#: load-bearing rather than incidental: it is what every task already on a board acquires, so
#: introducing this capability cannot start runs nobody asked for (design D7).
POLICIES = frozenset({POLICY_SURFACE, POLICY_RETRY, POLICY_ESCALATE})
DEFAULT_POLICY = POLICY_SURFACE

#: What governed a *review* that gave no verdict, recorded in `RunDivergence.policy_applied`.
#:
#: **Deliberately not a member of `POLICIES`, and a task can never carry it.** The column records
#: which rule governed, and reviews are governed by the reviewer resolution rather than by the
#: task's `divergence_policy` (design D3). Writing the task's own policy there instead would be a
#: false record — a `retry` task whose review failed would show `policy_applied: retry` beside an
#: outcome nothing retried, which is precisely the one-word-two-meanings defect this change exists
#: to end. Keeping it out of `POLICIES` is what stops an operator setting it on a task.
POLICY_REVIEW = "review"

#: What governed a *live flow's own work turn* diverging on a task whose policy was `retry`,
#: recorded in `RunDivergence.policy_applied` (design D7).
#:
#: **Deliberately not a member of `POLICIES`**, for the same reason `POLICY_REVIEW` is kept out:
#: the column records which rule actually governed, and a live flow governs its own work turn's
#: divergence directly rather than through the task's `divergence_policy` — the flow is going to
#: fire the task again on its own next tick, so starting a `retry` run here would race it. Writing
#: `policy_applied='retry'` beside an outcome nothing retried would be the one-word-two-meanings
#: defect this change exists to end, inverted onto a fourth case `POLICY_REVIEW` did not cover.
#: `escalate` is unaffected — it reassigns to a *different* agent, which is not something the
#: flow's next firing does.
POLICY_FLOW = "flow"

#: What was actually done. Differs from the policy whenever one fell back — `escalate` naming no
#: agent, or a retry that had already spent its single hop.
OUTCOME_SURFACED = "surfaced"
OUTCOME_RETRIED = "retried"
OUTCOME_ESCALATED = "escalated"
#: A failed review answered by resolving the reviewer again (design D4). Distinct from `retried`,
#: which is the same agent given another turn, and from `escalated`, which is `task.escalation_agent`
#: — a second reviewer resolution that `agent-flows` forbids in terms. It is a different agent,
#: chosen by the one resolution the product already uses.
OUTCOME_RESTAFFED = "restaffed"
OUTCOMES = frozenset({OUTCOME_SURFACED, OUTCOME_RETRIED, OUTCOME_ESCALATED, OUTCOME_RESTAFFED})


class TaskBindingError(Exception):
    """A named task that cannot be bound. Carries the HTTP status a route should send.

    A 404 rather than a 403 for a task in another project: the caller's authority is not in
    question, the row is simply not one they can see, and saying "forbidden" would confirm the id
    exists somewhere.
    """

    http_status = 404

    def __init__(self, detail: str, http_status: Optional[int] = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if http_status is not None:
            # A task that exists, is visible, and is simply finished being worked on is a conflict
            # with its state, not a missing row (F79). Overridden per raise rather than by a second
            # exception class, because `main.py`'s single handler is what makes these reach HTTP and
            # MCP identically.
            self.http_status = http_status


async def resolve_task_for_project(session: AsyncSession, task_id: str, project_id: str) -> Task:
    """The task, or a refusal naming which id failed and why.

    Validated at the moment of the call rather than at spawn, so an agent naming a task it cannot
    see learns immediately, in the tool result it is already reading, rather than through a run
    that quietly starts unbound.
    """
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise TaskBindingError(
            f"Task {task_id!r} does not exist in this project. A delegation may only name a task "
            f"in the project the delegating run belongs to."
        )
    return task


# --------------------------------------------------------------------------------------
# Binding
# --------------------------------------------------------------------------------------


def decided_task_refusal(task: Task) -> Optional[str]:
    """Why `task` takes no new work, or None because it still does (F79).

    The band is `TERMINAL_FOR_BINDING`, the same one `release_bindings_to` releases at and for the
    same stated reason: work that has been approved or abandoned is finished being worked on, and a
    run that kept attributing turns to it would put stalled markers on something the operator has
    already decided about (design D7). Asking one function rather than writing the band twice is
    what keeps the release and the refusal from drifting apart.

    Only ever asked about `task_id` -- the task a turn *works on*. `review_task_id` names the task a
    turn *inspects*, and inspecting decided work is exactly what a review is for.

    Two callers, two dispositions, and the difference is who is speaking. `POST /agent/trigger`
    refuses on it, because the operator is naming the task right now and is reading the response.
    `resolve_bound_task` drops the binding on it, because a delegation naming the task was true
    when it was queued and has merely stopped being so, and `turn_scheduler` would read a refusal
    there as grounds to abandon the message entirely.
    """
    if task.status not in TERMINAL_FOR_BINDING:
        return None
    return (
        f"Task {task.id!r} is {task.status!r}, which is a decision the operator has already made "
        f"about it, so a run cannot be started to work on it. Move it to 'revision_needed' to "
        f"reopen it, or start the turn without naming a task."
    )


def task_named_by(entry: InboundQueueEntry) -> Optional[str]:
    """The task this entry is about, whichever way it says so.

    Two columns name a task and they mean different things. `task_id` is the task the receiving run
    is *working on*. `review_task_id` is the task it is *inspecting* — set only where the dispatch
    made this selection as a review, and read at spawn to check out the author's commit (design D9
    of `loop-becomes-a-flow`, finding F10). Both are statements that this turn is about that task,
    which is the only thing binding needs.

    Until 2026-08-26 binding read `task_id` alone, and no dispatch path has ever set it on a review
    entry — so `run.task_id` was NULL on every review run the product had started, and the boundary
    check waved each of them through on *"no task to have neglected"*. Two `under_review → approved`
    transitions exist that no run records having caused.

    `review_task_id` is **not** merged into `task_id` and does not stop meaning "check out this
    commit". `task_id` wins where an entry carries both, which after design D5 is a divergence
    response to a review: the two name the same task there, and the precedence keeps the two
    purposes separable rather than collapsing them again — the exact defect this fixes, inverted.
    """
    return entry.task_id or entry.review_task_id


def binding_from_entries(
    entries: Iterable[InboundQueueEntry],
) -> Tuple[Optional[str], Optional[str]]:
    """What the earliest queued entry naming a task says: `(task_id, divergence_source_run_id)`.

    A turn can deliver several items and more than one may name a task. The earliest queued wins,
    matching the order `format_turn_prompt` assembles the prompt in — deterministic rather than
    clever. The alternative is a run whose binding depends on delivery timing, which would make the
    boundary check unreproducible. Ordering is over both sources together, not `task_id` first, for
    symmetry with the case that used to reach here: until `every-run-knows-its-task` (design D3), a
    turn could batch work and a review together and had to bind by arrival because nothing else
    told them apart. That batch can no longer *survive* — the scheduler narrows `selected` to one
    kind before a turn starts, and a caller that hand-builds a mixed one is refused at the trigger
    with a 409. It can still be seen here, though, and that changed: since D2 of
    `work-is-isolated-per-task` moved `resolve_bound_task` above the review-turn block,
    `binding_from_entries` runs *before* `_review_task_from_entries` raises that refusal. So the
    arrival-order tie-break below is not merely symmetry with a case that used to reach here — it
    is what a mixed batch gets for the few statements between the two, and it must stay total
    rather than assert one kind. Nothing is bound from it: the refusal follows before any run
    exists.

    Both values come from the *same* entry. Taking the source from a different one would let an
    unrelated item in the same turn spend a chain's retry hop.
    """
    named = [entry for entry in entries if task_named_by(entry)]
    if not named:
        return None, None
    # `sequence` is the queue's own order and is what `queued_entries` sorts by. Falling back to 0
    # keeps this usable with unflushed entries in tests, where every sequence is None.
    named.sort(key=lambda entry: entry.sequence or 0)
    return task_named_by(named[0]), named[0].divergence_source_run_id


async def review_task_for_run(session: AsyncSession, run: Run) -> Optional[str]:
    """The task `run` was started to *review*, or None if it was not started to review one.

    Read from the entries this run was delivered rather than from a column on `Run`, because that
    is where the fact already lives: `review_task_id` is set by whichever dispatch made this
    selection as a review — the flow's two staging paths and the operator's direct trigger — and
    every review turn in the product reaches a runner through one of them. Adding a `Run.is_review`
    column would restate a fact the queue already holds, and a restated fact is one that can
    disagree with its source (this change's own principle).

    Asked at the run boundary to decide which régime governs a divergence: a work run answers to
    the task's `divergence_policy`, and a review answers to the reviewer resolution instead
    (design D3). Before the boundary could ask, it could not tell the two apart, and after D1 it
    must — a bound review reaches machinery that had never seen one.

    `.limit(1)` is safe because a turn batching requests to review more than one task is refused
    at trigger time with a 409 (`agent_trigger._review_task_from_entries`), so at most one distinct
    value can exist here.
    """
    return await session.scalar(
        select(InboundQueueEntry.review_task_id)
        .where(InboundQueueEntry.delivered_in_run_id == run.id)
        .where(InboundQueueEntry.review_task_id.isnot(None))
        .limit(1)
    )


async def binding_for_delivery(
    session: AsyncSession, entry_ids: Optional[Iterable[str]]
) -> Tuple[Optional[str], Optional[str]]:
    """The binding the entries this turn is about to deliver imply."""
    ids = list(entry_ids or [])
    if not ids:
        return None, None
    result = await session.execute(
        select(InboundQueueEntry)
        .where(InboundQueueEntry.id.in_(ids))
        .order_by(InboundQueueEntry.sequence)
    )
    return binding_from_entries(result.scalars().all())


async def tasks_held_by_a_running_turn(session: AsyncSession, project_id: str) -> Dict[str, str]:
    """`task_id -> the agent whose running turn is bound to it`, for one project (design D8).

    Keying a workspace by task broke the coupling that used to make "one process per checkout" true
    for free: a checkout belonged to an agent, and an agent may have only one run in flight. A task
    can now be handed to two agents by two ordinary clicks, and they would share a working
    directory on one branch — the silent lost update `worktrees` exists to prevent, arriving along
    a new axis.

    **One query, one implementation, two callers asking two different questions.** The trigger path
    asks *"may this turn start"* and refuses; the flow scheduler asks *"why can this candidate not
    be staffed"* and records it, for finding F23's reason — a candidate dropped silently makes a
    busy flow report itself stalled. Answering it once as a map rather than twice as a predicate is
    deliberate: the scheduler walks a whole queue and would otherwise ask per candidate, and
    `scheduler.py`'s own comments record what happens when the same fact acquires a third asker.

    Cheap by construction: at most one running `Run` exists per agent (`agent_trigger` refuses a
    second), so this is bounded by the roster, not by history.
    """
    rows = await session.execute(
        select(Run.task_id, Run.agent).where(
            Run.project_id == project_id,
            Run.status == "running",
            Run.task_id.isnot(None),
        )
    )
    # Last writer wins on a duplicate, which cannot arise while the refusal below holds and is not
    # worth a second decision if it ever does: either agent is a truthful answer to "who holds it".
    return {task_id: agent for task_id, agent in rows.all() if task_id and agent}


class BoundTask(NamedTuple):
    """What `resolve_bound_task` answers.

    `named` separates "this turn said which task" from "the thread was already about one", which is
    what decides whether the conversation is rebound. Collapsing them would silently rebind a
    thread on every follow-up.
    """

    task: Optional[Task]
    named: bool
    delegated_source_run_id: Optional[str]


async def resolve_bound_task(
    session: AsyncSession,
    *,
    project_id: str,
    conversation,
    queue_entry_ids: Optional[Iterable[str]] = None,
    task_id: Optional[str] = None,
) -> BoundTask:
    """Which task this turn is about, and the run that delegated it. **Reads only.**

    Split out from the staging block in `agent_trigger` so it can be answered *before* the turn
    context is rendered. The context has to be able to say which specification the work implements,
    and the binding used to be resolved a hundred lines after the render — so the answer existed,
    just not yet.

    The staging that follows — rebinding the conversation, binding the run, recording the response
    run — deliberately stays where it is: it is placed before delivery, which is what commits, so a
    bound run whose task never moved cannot exist as a partial write.

    Safe to read twice because the mutations never feed back into this: `rebind_conversation` runs
    only where a task was named, and `binding_for_conversation` only reads where one was not.

    A delegated task takes precedence over an explicitly requested one because it is the more
    specific statement: an operator draining a queue did not choose what those items are about.
    """
    delegated_task_id, delegated_source_run_id = await binding_for_delivery(
        session, queue_entry_ids
    )

    bound_task: Optional[Task] = None
    if delegated_task_id:
        try:
            bound_task = await resolve_task_for_project(session, delegated_task_id, project_id)
        except TaskBindingError:
            # Validated once already, when the delegation was sent. If the task has since been
            # deleted the turn still runs, unbound: refusing to start would let removing a row
            # cancel work the agent was legitimately asked to do.
            bound_task = None
        if bound_task is not None and decided_task_refusal(bound_task) is not None:
            # The same disposition, one column over, and for the same reason (F79). An entry queued
            # before the operator approved the task is an instruction that has stopped being true,
            # not a wrong request — and `turn_scheduler` would read a refusal here as grounds to
            # abandon the entry after three attempts, discarding a message the agent was
            # legitimately sent because of a decision taken about something else. The turn runs;
            # only the claim that it is work on that task is dropped.
            bound_task = None
    elif task_id:
        # Asked for explicitly, now, by the operator or by a divergence response. A refusal here is
        # the right answer — nothing else in the request implies the work.
        bound_task = await resolve_task_for_project(session, task_id, project_id)

    if bound_task is not None:
        return BoundTask(bound_task, True, delegated_source_run_id)

    # Nothing named one, so inherit what the thread is already about. This is the whole point of
    # the conversation binding: without it a follow-up typed into the composer sends no task id,
    # and every turn after the first went unchecked — including the one where the agent actually
    # stopped.
    inherited = await binding_for_conversation(session, conversation, project_id)
    return BoundTask(inherited, False, delegated_source_run_id)


async def spec_document_for_task(session: AsyncSession, task: Optional[Task]) -> Optional[str]:
    """The path of the document *task* implements, if it names one.

    The link already existed — `Task.spec_document_id` is written when a document's declared tasks
    are materialised at approval — and reached nothing. An agent handed the task could not get from
    it to the document, and `read_spec_document` takes a path.

    Returns the path, never the id: the id is a database identifier that names nothing the agent
    has seen, and it is what the builder tried and was refused on.
    """
    if task is None or not getattr(task, "spec_document_id", None):
        return None
    document = await session.get(SpecDocument, task.spec_document_id)
    return document.path if document is not None else None


async def bind_run_to_task(
    session: AsyncSession,
    run: Run,
    task: Task,
) -> Optional[TaskTransition]:
    """Attach `run` to `task` and start the task if it can be started.

    Returns the transition when one was made, else None. Both are ordinary outcomes: binding is a
    statement about the run, not a claim about the task's status, so a task already `completed`
    binds and moves nowhere.

    The move goes through `apply_transition` with `origin='runtime'` — B1's own entry point, with
    B1's own legality check and the seam B3's evidence checks and B4's completion gates plug into.
    A path that set `task.status` here directly would be a bypass of every gate not yet written.

    A task that is `blocked` binds and stays blocked. `blocked -> in_progress` is a legal edge for a
    run, so without the explicit guard below the act of starting a run would silently unpark a task
    still waiting on an unanswered question — and that run's end would then find it un-blocked and
    record a divergence, which is the bug this whole line of work exists to remove. A block is
    released by the answer arriving or by the operator saying so, never by something merely starting.

    The task also learns *who* is doing it. Two paths reach `in_progress` and until 2026-08-24 only
    one named an agent: the loop's claim sets `claimed_task.assignee` from its selection
    (`scheduler.py` — `job.agent` until `loop-becomes-a-flow` group 2 made it the selection's own
    agent, so a flow's reviewer is recorded as the assignee rather than the job's owner), a direct
    `task_id` trigger set nothing. So a task a run was actively working
    read `status: in_progress, assignee: null` — and since `assignee_status` is derived from that
    null (`_task_response`), the board reported `idle` about an agent that was at that moment
    running. Written here rather than in the trigger route because this is the one place both paths
    pass through.

    Only where the task does not already name someone else. An operator who assigned the card to a
    person, or a loop that claimed it for one agent, has made a statement; a run starting is not
    grounds to overwrite it. Re-binding the same agent is a no-op either way.

    Nothing is committed. The caller stages this alongside the `Run` insert so a bound run whose
    task never moved cannot exist as a partial write.
    """
    run.task_id = task.id
    actor = run_actor(run.id, run.agent)

    if run.agent and not task.assignee:
        task.assignee = run.agent

    if task.status == STATUS_BLOCKED:
        return None

    if "in_progress" not in allowed_targets(task.status, actor.kind):
        return None

    try:
        return await apply_transition(session, task, "in_progress", actor, origin=ORIGIN_RUNTIME)
    except TransitionRefusedError:
        # The reachability check above already covers the map, so this cannot be an illegal edge or
        # the author/reviewer path. Since `task-dependencies` §5 it CAN be the dependency gate: a run
        # binds to a task whose prerequisites are not all `approved` yet. Caught rather than assumed
        # away either way — a refusal here must leave the run bound and the task untouched, never
        # propagate and fail the spawn. A task left un-started this way stays `pending`/`assigned`
        # with the run attached but idle; `loop-notices-and-reacts` (S4) is where the loop itself
        # learns to route around a gated task rather than claim one and sit idle on it.
        return None


# --------------------------------------------------------------------------------------
# The binding that outlives one run
# --------------------------------------------------------------------------------------

#: Statuses at which a conversation's binding releases itself. Work that has been approved or
#: abandoned is finished being worked on, and a thread that kept attributing turns to it would put
#: stalled markers on a task the operator has already decided about (design D7).
#:
#: `completed` and `under_review` are deliberately absent: work under review comes back often, and
#: releasing there would unbind precisely the thread that is about to do the revisions.
#: Derived from the lifecycle bands (`loop-notices-and-reacts` 3.7) rather than listed. The
#: reasoning above is why it is the terminal band and not a wider one, and it survives the
#: derivation because the band means the same thing.
TERMINAL_FOR_BINDING: Tuple[str, ...] = tuple(sorted(TERMINAL_STATUSES))


async def binding_for_conversation(
    session: AsyncSession,
    conversation,
    project_id: str,
) -> Optional[Task]:
    """The task this thread is already about, if it is about one and that task still exists.

    Inheritance is what makes turn two of a piece of work checked at all. Silent when the task has
    been deleted since — the turn still runs, unbound, because removing a row must not cancel work
    the operator asked for.
    """
    task_id = getattr(conversation, "task_id", None)
    if not task_id:
        return None
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        return None
    return task


def rebind_conversation(conversation, task: Optional[Task]) -> None:
    """Point the thread at `task`, or at nothing.

    Called when a turn names a task of its own — an operator starting work from a card, or a
    delegation carrying one. The more specific statement wins, and the thread follows it, so the
    operator does not have to release the old binding before starting something else here.
    """
    conversation.task_id = task.id if task is not None else None


async def release_conversations_bound_to(session: AsyncSession, task: Task) -> int:
    """Unbind every conversation pointed at `task`. Returns how many were released.

    Called when the task reaches a status there is no more working to do at. Not inferred from what
    a thread seems to be about — the only two triggers are this and an explicit operator release,
    because a binding that quietly disappears stops checking runs without saying so.
    """
    from .db.models import Conversation

    result = await session.execute(select(Conversation).where(Conversation.task_id == task.id))
    conversations = list(result.scalars().all())
    for conversation in conversations:
        conversation.task_id = None
    return len(conversations)


async def release_bindings_to(session: AsyncSession, task: Task) -> None:
    """Release everything still claiming to be work on `task`, at the moment it is decided.

    Two surfaces can carry that claim into a *future* run and both have to let go together, or the
    rule holds on one and is bypassed on the other — which is exactly what F79 was: the
    conversations released on approval, the queued turns did not, and one of them was delivered 29
    minutes later against work that had already merged to `master`.

    Called from the one place a task reaches a terminal status, so a third surface acquiring a
    binding has one function to be added to rather than a call site to be remembered at.
    """
    await release_conversations_bound_to(session, task)
    await _release_queued_entries_bound_to(session, task)


async def _release_queued_entries_bound_to(session: AsyncSession, task: Task) -> int:
    """Unbind the turns still waiting to be delivered against `task`. Returns how many.

    **Queued only.** A `delivered` entry is the record of a turn that already happened, and its
    run's boundary check was decided against that binding; rewriting it would make the history
    disagree with the runs it explains.

    **`task_id` only.** `review_task_id` says this turn *inspects* the task, which is legitimate
    precisely when the work is finished, and clearing it would put back the hole
    `every-run-knows-its-task` D3 closed -- review runs with a NULL `task_id`, and `under_review ->
    approved` transitions that no run records having caused.
    """
    result = await session.execute(
        select(InboundQueueEntry).where(
            InboundQueueEntry.task_id == task.id,
            InboundQueueEntry.state == "queued",
        )
    )
    entries = list(result.scalars().all())
    for entry in entries:
        entry.task_id = None
    return len(entries)


# --------------------------------------------------------------------------------------
# Waiting on a person
# --------------------------------------------------------------------------------------

#: How much of a question's text becomes the task's blocked reason. Long enough to identify which
#: question parked the task on a card, short enough not to turn the card into a wall of text —
#: the full question is one click away on the question itself, which is where it belongs.
_REASON_LIMIT = 280


def reason_from_question(question: Question) -> str:
    """The one sentence a card shows for a task waiting on *question*.

    Public because two surfaces need the identical wording: `block_task_for_question` writes it to
    `blocked_reason` when the task parks, and `tasks.py`'s `_attach_awaiting_answer` reports the
    same wait *before* it parks (F14). Two spellings of the same wait would read as two different
    situations.
    """
    text = " ".join((question.question or "").split())
    if len(text) > _REASON_LIMIT:
        text = text[: _REASON_LIMIT - 1].rstrip() + "…"
    return f"Waiting on your answer: {text}" if text else "Waiting on your answer."


def proceeded_without_answer_reason(question: Question) -> str:
    """The one sentence a card shows for work that went ahead without an answer to *question*.

    A sibling of `reason_from_question` rather than a second spelling of it, trimmed by the same
    limit, for the same reason: the wait and its ending are the same question read at two moments,
    and two surfaces spelling them differently would read as two different situations.

    Not "timed out" and not "expired". What matters to whoever reads the task later is not that a
    clock ran out but that a decision was taken and the operator was not part of it.
    """
    text = " ".join((question.question or "").split())
    if len(text) > _REASON_LIMIT:
        text = text[: _REASON_LIMIT - 1].rstrip() + "…"
    return f"Proceeded without your answer: {text}" if text else "Proceeded without your answer."


async def unanswered_blocking_question(session: AsyncSession, run: Run) -> Optional[Question]:
    """The question this run asked and is still waiting on, if there is one.

    Only `blocking=True` counts. `ask_user(blocking=False)` is the agent leaving a note and carrying
    on, and a task parked on a note would make the status mean "an agent mentioned something"
    (design R1).

    Scoped to questions *this run* opened. A question another run left unanswered is not evidence
    that this run stopped for it, and treating it as such would park a task on the strength of an
    unrelated agent's unfinished business.

    A question the operator declined does not count either
    (`2026-08-11-declining-a-question`, D4). Without that exclusion this check would immediately undo
    a decline: the operator closes the question, the task is released, the run ends, and the task is
    parked again on the very question they just closed.

    **Nor does a question whose wait has ended** (`a-task-waits-while-its-run-waits`, design D6).
    `wait_ended_at` introduces a state that did not exist before it: unanswered, undeclined, and
    nobody waiting. Without this exclusion a timed-out run would park its task at the boundary and
    suppress a divergence that is real — the agent proceeded, then dropped the work, and the record
    would say it was waiting on somebody.

    Note the ordering this creates for the run-end sweep: the sweep has to find its candidate
    *before* recording `wait_ended_at`, because after that this predicate will not return it again.
    That is also what makes a sweep arriving after the tool's report harmless.

    Earliest first: a run that asked several is waiting on the first thing it got stuck on, which is
    the more useful thing to name on the card.
    """
    result = await session.execute(
        select(Question)
        .where(Question.created_by_run_id == run.id)
        .where(Question.blocking.is_(True))
        .where(Question.answered.is_(False))
        .where(Question.declined.is_(False))
        .where(Question.wait_ended_at.is_(None))
        .order_by(Question.created_at, Question.batch_index)
        .limit(1)
    )
    return result.scalars().first()


async def block_task_for_question(
    session: AsyncSession,
    run: Run,
    task: Task,
    question: Question,
) -> Optional[TaskTransition]:
    """Park `task` because `run` is waiting on `question`. Returns the transition, or None.

    `origin='runtime'` — the Hub observed the block, the agent did not declare it (design D3, and
    D5's choice of how a blocked task escapes the divergence check). Keeping `origin` meaning "who
    caused this" is why the divergence check excludes the *status* rather than reading the block as
    the run advancing its own work.

    The question records which task it parked, so answering it knows what to release without
    re-deriving it from the run's binding — a run may be bound to a task the question was not about.

    Returns None when the map does not allow it, which is the ordinary case for a task that is not
    `in_progress`: a run can end with a question open while its task sits in `under_review`, and
    that is not a block, it is a question about something else.
    """
    actor = run_actor(run.id, run.agent)
    if STATUS_BLOCKED not in allowed_targets(task.status, actor.kind):
        if task.status == STATUS_BLOCKED:
            question.blocked_task_id = task.id
        return None

    try:
        transition = await apply_transition(
            session, task, STATUS_BLOCKED, actor, origin=ORIGIN_RUNTIME
        )
    except TransitionRefusedError:
        # Same reasoning as `bind_run_to_task`: a refusal here must leave the run ended and the
        # task untouched, never propagate and turn a finished run into a failed one.
        return None

    task.blocked_reason = reason_from_question(question)
    question.blocked_task_id = task.id
    return transition


async def announce_block(
    session: AsyncSession,
    run: Run,
    task: Task,
    question: Question,
) -> None:
    """Tell the operator's board that a task is now waiting on them.

    `info`, not `warn`. A divergence is `warn` because it wants attention on something that went
    wrong; this is the mechanism working — the agent asked rather than guessed. Warning about it
    would train the operator to read the one signal that means "someone did the right thing" as a
    problem.

    Here rather than in `run_divergence`, where it started, because it now has two callers: the
    ask-time park in the agent-facing questions route, and the run-end park below it. Beside
    `block_task_for_question` so the announcement and the transition it announces cannot drift
    apart.
    """
    payload = {
        "run_id": run.id,
        "agent": run.agent,
        "task_id": task.id,
        "task_title": task.title,
        "question_id": question.id,
        "reason": task.blocked_reason,
    }
    await persist_event(
        session,
        run.project_id,
        "task_blocked",
        payload,
        agent=run.agent,
        severity="info",
    )
    await sse_manager.broadcast(run.project_id, "task_blocked", payload)


def release_reason(task: Task) -> None:
    """Clear what a task was waiting for, because it is no longer waiting.

    Called wherever a task leaves `blocked`. Separate from the transition itself so that every exit
    — the answer arriving, the operator releasing it, reassignment, rejection — drops the text the
    same way. A reason outliving its block is a card that says it is waiting on something that
    already arrived.
    """
    task.blocked_reason = None


async def release_block_for_question(
    session: AsyncSession,
    question: Question,
) -> Optional[Task]:
    """The question is settled, so the task is no longer waiting. Returns the task, if one was
    released.

    Settled means answered *or* declined. One function rather than two, because the two differ only
    in what settled it and a block released one way but not the other is exactly the bug this
    guards (`2026-08-11-declining-a-question`, D3).

    Attributed to the **operator**, with the default `actor` origin: they answered, and answering is
    what released it. Not a runtime transition — the runtime observes a block, but it does not
    invent this one, and an origin of `runtime` here would additionally exempt the move from the
    divergence check for no reason.

    Silent when the task has moved on since. The operator may have rejected or reassigned it while
    it sat waiting, and an answer arriving afterwards must not drag it back into `in_progress`.
    """
    if not question.blocked_task_id:
        return None

    task = await session.get(Task, question.blocked_task_id)
    if task is None or task.status != STATUS_BLOCKED:
        return None

    try:
        await apply_transition(session, task, "in_progress", operator())
    except TransitionRefusedError:
        return None

    release_reason(task)
    return task


def wait_has_expired(question: Question, now: Optional[datetime] = None) -> bool:
    """Has the wait this question started demonstrably ended without an answer?

    The one predicate both signals share (design D4): the tool's report checks it before recording
    an expiry, and the run-end sweep checks it before recording one the report never delivered. Two
    spellings of it would be two chances to disagree about whether a wait ended.

    Everything it compares is the Hub's own. `wait_expires_at` was stamped Hub-side while serving
    the ask, so this is the Hub comparing its own clock against its own stamp — no cross-process
    comparison, and nothing the reporting party supplied.

    False when no deadline was ever recorded. A question nobody waited on cannot have stopped being
    waited on, and that is what keeps this a report of a fact rather than a way to create one.
    """
    deadline = question.wait_expires_at
    if deadline is None:
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline <= (now or datetime.now(timezone.utc))


async def release_block_for_expired_wait(
    session: AsyncSession,
    question: Question,
    run: Run,
) -> Optional[Task]:
    """The wait ended without an answer, so the task is no longer waiting. Returns the task, if one
    was released.

    The third exit from `blocked`, beside the operator's answer and their decline. Here rather than
    folded into `release_block_for_question` because what settled it is different in the one way
    that matters to the record: nobody answered. `release_block_for_question`'s docstring says the
    other two differ only in what settled them; this one also differs in *who*.

    Attributed to the **run**, with `origin=ORIGIN_RUNTIME`. The run is the party that stopped
    waiting, and the runtime is what observed it — the same attribution `block_task_for_question`
    uses for the park it undoes. `_guard_run_holds_the_task` takes its `run.task_id == task.id`
    no-op branch here, because the run is already bound.

    Silent when the task has moved on since, exactly as the other two are: the operator may have
    rejected or reassigned it while it waited, and a wait ending afterwards must not drag it back.

    Idempotent by the caller's construction, not this function's: both callers (the tool's report
    and the run-end sweep) check `wait_ended_at` before reaching here, and the `status != BLOCKED`
    guard below makes a second call a no-op regardless.
    """
    if not question.blocked_task_id:
        return None

    task = await session.get(Task, question.blocked_task_id)
    if task is None or task.status != STATUS_BLOCKED:
        return None

    try:
        await apply_transition(
            session, task, "in_progress", run_actor(run.id, run.agent), origin=ORIGIN_RUNTIME
        )
    except TransitionRefusedError:
        # Same reasoning as `block_task_for_question`: a refusal must leave the wait recorded and
        # the task untouched, never turn the agent's report into a failed request.
        return None

    release_reason(task)
    return task


# --------------------------------------------------------------------------------------
# The boundary question
# --------------------------------------------------------------------------------------


async def run_advanced_its_task(session: AsyncSession, run: Run) -> bool:
    """Did `run` move its bound task itself?

    `origin='actor'` is the whole point. The runtime's automatic move to `in_progress` is a
    transition by this run on this task, so a query that did not exclude it would answer True for
    every bound run and the check would report nothing (design D5).

    An unbound run returns True — it has no task to have neglected, and the caller should not have
    to special-case it before asking.
    """
    if not run.task_id:
        return True
    result = await session.execute(
        select(TaskTransition.sequence)
        .where(TaskTransition.run_id == run.id)
        .where(TaskTransition.task_id == run.task_id)
        .where(TaskTransition.origin == ORIGIN_ACTOR)
        .limit(1)
    )
    return result.first() is not None


def may_retry(run: Run) -> bool:
    """Whether a divergence of `run` may be answered by starting another run of the same agent.

    This is the entire retry bound (design D8). A run started in answer to a divergence carries the
    run that caused it, and never triggers one of its own — so `A diverges → B` can only be
    followed by escalation or surfacing. There is no max-attempts field to misconfigure and no loop
    is expressible.

    The bound is per chain, not per task lifetime: a response run that does move its task ends the
    chain, and a later independent run bound to the same task starts a fresh one.
    """
    return run.divergence_source_run_id is None
