"""Durable per-agent inbound queue primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from .conversations import get_conversation_by_id
from .db.models import InboundQueueEntry, Project, Run
from .utils import short_id

if TYPE_CHECKING:
    from .provider_allowance import AllowanceRefusal

DEFAULT_HOP_BUDGET = 6
DEFAULT_TURN_DELIVERY_CAP = 10


def new_entry(
    *,
    project_id: str,
    agent: str,
    origin_type: str,
    content: str,
    hop_depth: int,
    origin_agent: Optional[str] = None,
    message_id: Optional[str] = None,
    session_mode: Optional[str] = None,
    session_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    work_dir: Optional[str] = None,
    spec_document: Optional[str] = None,
    task_id: Optional[str] = None,
    divergence_source_run_id: Optional[str] = None,
    review_task_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> InboundQueueEntry:
    if origin_type not in ("operator", "agent", "job", "checkpoint", "divergence"):
        raise ValueError(
            "origin_type must be 'operator', 'agent', 'job', 'checkpoint', or 'divergence'"
        )
    if (origin_type == "agent") != bool(origin_agent):
        raise ValueError("agent origins require origin_agent; operator origins forbid it")
    if hop_depth < 0:
        raise ValueError("hop_depth must be non-negative")
    return InboundQueueEntry(
        id=f"entry-{short_id()}",
        project_id=project_id,
        agent=agent,
        origin_type=origin_type,
        origin_agent=origin_agent,
        content=content,
        arrived_at=datetime.now(timezone.utc),
        hop_depth=hop_depth,
        message_id=message_id,
        session_mode=session_mode,
        session_id=session_id,
        conversation_id=conversation_id,
        work_dir=work_dir,
        spec_document=spec_document,
        task_id=task_id,
        divergence_source_run_id=divergence_source_run_id,
        review_task_id=review_task_id,
        job_id=job_id,
        state="queued",
    )


async def project_limits(db: AsyncSession, project_id: str) -> tuple[int, int]:
    project = await db.get(Project, project_id)
    if project is None:
        raise ValueError(f"project {project_id!r} does not exist")
    return project.hop_budget, project.turn_delivery_cap


async def queued_entries(
    db: AsyncSession,
    project_id: str,
    agent: str,
    conversation_id: Optional[str] = None,
) -> List[InboundQueueEntry]:
    predicates = [
        InboundQueueEntry.project_id == project_id,
        InboundQueueEntry.agent == agent,
        InboundQueueEntry.state == "queued",
    ]
    if conversation_id is not None:
        predicates.append(InboundQueueEntry.conversation_id == conversation_id)
    result = await db.execute(
        select(InboundQueueEntry).where(*predicates).order_by(InboundQueueEntry.sequence)
    )
    return list(result.scalars().all())


def can_start(entries: Iterable[InboundQueueEntry], hop_budget: int) -> bool:
    return any(entry.hop_depth <= hop_budget for entry in entries)


def entry_kind(entry: InboundQueueEntry) -> Optional[str]:
    """Returns "review" or "work", or `None` for an entry naming neither (design D3, F66).

    `review_task_id` wins when both are set — the divergence response that restaffs a failed
    review sets both to the same task (`run_divergence.py`), and that entry needs the review
    checkout, not the ordinary worktree, so it is a review turn regardless of the `task_id` beside
    it.
    """
    if entry.review_task_id is not None:
        return "review"
    if entry.task_id is not None:
        return "work"
    return None


def select_turn(
    entries: Sequence[InboundQueueEntry], hop_budget: int, cap: int
) -> Tuple[Optional[InboundQueueEntry], List[InboundQueueEntry]]:
    """The turn *entries* would start: its controlling entry and the entries riding on it.

    The one place the composition is decided, called by the scheduler that starts the turn and by
    `GET /queue/{agent}/status` that explains why it has not started (F133): two predicates over
    "the turn" had drifted, and the status route answered for every queued entry rather than the
    entries a turn would carry. *entries* arrive in queue order. The controlling entry is the first
    within the hop budget; the turn is that entry's conversation, within budget, of its kind
    (an entry naming no kind rides along with either), capped. `(None, [])` when nothing is
    within budget.

    Filtered by depth and by kind, as well as by conversation: `can_start` asks whether the turn
    may begin, and nothing used to ask which entries may ride on it, so an over-budget entry was
    bundled into a turn admitted by a shallower one (design D1, F5). A review entry and a work
    entry batched together delivered a turn that was neither, so the controlling entry's kind
    decides the turn and the other kind's entries are deferred (design D3, F66).
    """
    controlling = next((entry for entry in entries if entry.hop_depth <= hop_budget), None)
    if controlling is None:
        return None, []
    controlling_kind = entry_kind(controlling)
    selected = [
        entry
        for entry in entries
        if entry.conversation_id == controlling.conversation_id
        and entry.hop_depth <= hop_budget
        and (
            controlling_kind is None
            or entry_kind(entry) is None
            or entry_kind(entry) == controlling_kind
        )
    ][:cap]
    return controlling, selected


def format_turn_prompt(entries: Iterable[InboundQueueEntry]) -> str:
    blocks = ["[AgentWeave inbound queue — delivered inline in arrival order]"]
    for entry in entries:
        if entry.origin_type == "operator":
            origin = "Operator"
        elif entry.origin_type == "job":
            origin = "Scheduled job"
        elif entry.origin_type == "checkpoint":
            origin = "Checkpoint"
        elif entry.origin_type == "divergence":
            origin = "Divergence"
        else:
            origin = f'Agent "{entry.origin_agent}"'
        # Per entry rather than in the preamble, because `delivery_attempts` is per entry: one turn
        # can carry a retried input alongside one never tried before, and a blanket sentence would
        # misdescribe the second. An agent handed the same instruction twice has no other way to
        # tell — it may find its own half-finished work and read it as someone else's.
        #
        # The fact and nothing more. What to do about half-finished work depends on what the work
        # was, so an instruction to inspect or redo would be wrong often enough to cost more than
        # it saves. Absent at zero attempts, which is every ordinary delivery.
        #
        # A delivery the provider refused on usage grounds counts here too, though not towards
        # the limits (`a-spent-allowance-holds-the-queue`, D8): it was cut off before or during
        # the turn all the same, and the resumed session may hold the agent's own copy of it.
        retry = ""
        earlier = (entry.delivery_attempts or 0) + (entry.allowance_refusals or 0)
        if earlier:
            retry = (
                f" — delivery attempt {earlier + 1}; "
                f"an earlier attempt was cut off before it finished"
            )
        blocks.append(f"{origin} (hop {entry.hop_depth}){retry}:\n{entry.content}")
    return "\n\n".join(blocks)


class QueueChangedError(RuntimeError):
    """The entries a turn was about to deliver are no longer all queued -- withdrawn, or delivered
    elsewhere, between being selected and being claimed. Nothing was delivered. A fact about
    timing, not a fault: `agent_trigger` turns it into a transient refusal, so the scheduler
    re-reads what is still queued and counts nothing (F338)."""


async def deliver_entries_with_run(
    db: AsyncSession,
    *,
    project_id: str,
    agent: str,
    entry_ids: List[str],
    run: Run,
) -> List[InboundQueueEntry]:
    """Atomically stamp exactly *entry_ids* delivered while creating *run*."""
    result = await db.execute(
        select(InboundQueueEntry)
        .where(
            InboundQueueEntry.project_id == project_id,
            InboundQueueEntry.agent == agent,
            InboundQueueEntry.id.in_(entry_ids),
            InboundQueueEntry.state == "queued",
        )
        .order_by(InboundQueueEntry.sequence)
    )
    entries = list(result.scalars().all())
    if [entry.id for entry in entries] != entry_ids:
        raise QueueChangedError("queue changed before atomic delivery")
    if run.conversation_id is not None and any(
        entry.conversation_id != run.conversation_id for entry in entries
    ):
        raise RuntimeError("one run cannot deliver entries from different conversations")
    now = datetime.now(timezone.utc)
    # F338: the claim is the `UPDATE`'s own condition, as F328 made every withdrawal. The select
    # above runs outside a write transaction on a plain turn (SQLite locks at the write, not the
    # read), so an operator's withdrawal can commit between it and this commit; writing these rows
    # back by primary key overwrote that `withdrawn` with `delivered`, after the operator had been
    # answered 200. Now whichever writes first wins, and a delivery that lost refuses whole. The run
    # is flushed first so the rows can name it.
    db.add(run)
    await db.flush()
    claimed = await db.execute(
        update(InboundQueueEntry)
        .where(
            InboundQueueEntry.project_id == project_id,
            InboundQueueEntry.agent == agent,
            InboundQueueEntry.id.in_(entry_ids),
            InboundQueueEntry.state == "queued",
        )
        .values(
            state="delivered",
            delivered_in_run_id=run.id,
            delivered_at=now,
            # The wait is over, so the reason it was waiting is history. Cleared here rather than
            # left to age because a delivered entry can come back — `return_run_entries` requeues
            # it — and a stale explanation of a wait that ended is worse than none (F97).
            waiting_reason=None,
        )
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != len(entry_ids):
        # Nothing of this delivery may land: not the rows it did claim, not the run, not anything
        # the caller staged for it (the task binding is staged before delivery for this reason).
        await db.rollback()
        raise QueueChangedError("queue changed before atomic delivery")
    for entry in entries:
        set_committed_value(entry, "state", "delivered")
        set_committed_value(entry, "delivered_in_run_id", run.id)
        set_committed_value(entry, "delivered_at", now)
        set_committed_value(entry, "waiting_reason", None)
    await db.commit()
    return entries


#: Failed deliveries of one entry before the next turn starts a fresh provider session.
#:
#: Not 1: a single failure is routinely a Hub restart or a transient spawn error, and discarding a
#: live provider session costs the agent its whole provider-side context irreversibly. Strictly
#: below `DELIVERY_ATTEMPT_LIMIT`, or the fresh session is never actually tried.
RESUME_RETRY_LIMIT = 2

#: Failed deliveries before the Hub stops retrying and says so.
#:
#: Exactly one attempt on the original session, one that trips the reset, and one on a fresh
#: session — the third is what distinguishes "the session was poisoned" from "the input is
#: poisoned". Fewer, and a Hub restart could discard an operator's message; more, and an agent is
#: wedged across four failing turns before anyone is told.
DELIVERY_ATTEMPT_LIMIT = 3


async def return_run_entries(
    db: AsyncSession, run_id: str, *, refusal: Optional["AllowanceRefusal"] = None
) -> List[str]:
    """Put a failed run's input back, unless putting it back is what keeps failing.

    Returning an entry keeps it lost-proof, and used to be unconditional. But a returned entry
    keeps its place in arrival order *and* its binding to the conversation it arrived on, and the
    scheduler adopts the oldest queued entry's conversation for the turn — so if that conversation's
    provider session cannot be resumed, every delivery re-kills the runtime and every later input,
    including a request for a fresh conversation, queues behind the one doing the killing. Observed
    live: four entries, four consecutive failures, no way through.

    So: count the attempt; at `RESUME_RETRY_LIMIT` give up on the provider session, which is what
    actually breaks the loop; at `DELIVERY_ATTEMPT_LIMIT` give up on the entry and record why.

    `conversation_id` is deliberately *not* cleared — an entry belonging to no conversation cannot
    be scheduled at all, so it would wedge silently and forever, strictly worse than today.
    `arrived_at` is deliberately not bumped: ordering is by `sequence`, so it would change nothing
    about scheduling and only hide how long the input has been stuck.

    Returns the ids that went back to `queued`, as it always has. Abandoned ids are reported
    separately by `abandoned_for_run`, so a caller that only wants the requeued set is unaffected.

    **A refusal is returned without being counted** (`a-spent-allowance-holds-the-queue`, D2). When
    the provider refused the turn because the agent's usage allowance is spent, *refusal* is given:
    the entry goes back to `queued` with `allowance_refusals` counted instead, and neither limit is
    evaluated. Here the session *was* resumed and the input was not what failed, so clearing the
    provider session would discard the agent's context for nothing, and withdrawing the entry would
    drop the operator's message for a wait with a stated end. `waiting_reason` stays cleared: the
    status route derives the hold live, and a stored copy would outlive it (F97).
    """
    result = await db.execute(
        select(InboundQueueEntry).where(
            InboundQueueEntry.delivered_in_run_id == run_id,
            InboundQueueEntry.state == "delivered",
        )
    )
    entries = list(result.scalars().all())
    requeued: List[str] = []
    for entry in entries:
        entry.delivered_at = None
        if refusal is not None:
            entry.allowance_refusals = (entry.allowance_refusals or 0) + 1
            entry.state = "queued"
            entry.delivered_in_run_id = None
            requeued.append(entry.id)
            continue
        entry.delivery_attempts = (entry.delivery_attempts or 0) + 1

        if entry.delivery_attempts >= RESUME_RETRY_LIMIT and entry.conversation_id:
            # The one change that breaks the loop. Cleared rather than flagged, because
            # `session_mode` is derived from whether this is set — so clearing it makes the next
            # delivery a fresh start, and the turn after that re-binds whatever session it gets.
            conversation = await get_conversation_by_id(db, entry.conversation_id)
            if conversation is not None and conversation.provider_session_id is not None:
                conversation.provider_session_id = None

        if entry.delivery_attempts >= DELIVERY_ATTEMPT_LIMIT:
            entry.state = "withdrawn"
            entry.withdrawn_at = datetime.now(timezone.utc)
            entry.abandoned_reason = (
                f"delivery failed {entry.delivery_attempts} times; the Hub stopped retrying"
            )
            # `delivered_in_run_id` is deliberately kept: it is the operator's breadcrumb from a
            # dropped message to the run that ate it.
            continue

        entry.state = "queued"
        entry.delivered_in_run_id = None
        requeued.append(entry.id)
    return requeued


async def abandoned_for_run(db: AsyncSession, run_id: str) -> List[InboundQueueEntry]:
    """The entries this run's failure gave up on, so the caller can report them."""
    result = await db.execute(
        select(InboundQueueEntry).where(
            InboundQueueEntry.delivered_in_run_id == run_id,
            InboundQueueEntry.state == "withdrawn",
            InboundQueueEntry.abandoned_reason.is_not(None),
        )
    )
    return list(result.scalars().all())


@dataclass
class ReleaseOutcome:
    """The result of asking to release a budget-held entry.

    The refusal is returned rather than raised, matching `commit_for_task_review`: there are two
    distinct ways this fails and an operator can only act on one of them. An entry that is gone or
    already handled is somebody else's doing; an entry sitting inside the budget is waiting for a
    reason the release action would not fix, and saying "released" would be a lie about which
    thing was stuck.
    """

    entry: Optional[InboundQueueEntry] = None
    refusal: Optional[str] = None
    refusal_status: int = 409
    #: The depth the entry carried before the re-base, for the record of what the operator did.
    released_from_depth: Optional[int] = None


async def not_queued_reason(
    db: AsyncSession, project_id: str, entry_id: str, action: str
) -> Tuple[int, str]:
    """Why *entry_id* cannot be withdrawn or released, as `(status, sentence)` (F200).

    One sentence used to cover four states, and it told an operator whose entry was withdrawn, or
    was never this project's, that it had been delivered. An unknown id and another project's read
    the same, so the refusal does not tell a caller that an entry exists elsewhere.
    """
    result = await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None or entry.project_id != project_id:
        return 404, f"No queue entry {entry_id} in this project."
    if entry.state == "delivered":
        run = f" in run {entry.delivered_in_run_id}" if entry.delivered_in_run_id else ""
        return (
            409,
            f"Queue entry {entry_id} was already delivered{run}; there is nothing to {action}.",
        )
    if entry.state == "withdrawn" and entry.abandoned_reason:
        return 409, (
            f"The Hub already gave up delivering queue entry {entry_id} "
            f"({entry.abandoned_reason.rstrip('.')}). Send the message again to retry it."
        )
    if entry.state == "withdrawn":
        return 409, f"Queue entry {entry_id} was already withdrawn; there is nothing to {action}."
    # Still queued: it changed state and back between the attempt and this read.
    return 409, f"Queue entry {entry_id} changed while this {action} was being made; try again."


async def release_entry(db: AsyncSession, project_id: str, entry_id: str) -> ReleaseOutcome:
    """Re-base a budget-held entry to depth 0 so the next turn delivers it (design D3).

    Depth 0 rather than a `+N` grant: "the operator restarted this chain here" is a fact a later
    reader can reconstruct from the event, where an arithmetic grant leaves behind a depth whose
    meaning depends on history nobody recorded.
    """
    result = await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None or entry.project_id != project_id or entry.state != "queued":
        status, refusal = await not_queued_reason(db, project_id, entry_id, "release")
        return ReleaseOutcome(refusal=refusal, refusal_status=status)
    project = await db.get(Project, project_id)
    if project is None:
        raise ValueError(f"project {project_id!r} does not exist")
    if entry.hop_depth <= project.hop_budget:
        return ReleaseOutcome(
            refusal=(
                f"Queue entry is at hop {entry.hop_depth}, within the project's hop budget of "
                f"{project.hop_budget}, so the hop budget is not what is holding it. Check the "
                f"agent's queue status for the reason it is waiting."
            )
        )
    released_from = entry.hop_depth
    entry.hop_depth = 0
    await db.commit()
    return ReleaseOutcome(entry=entry, released_from_depth=released_from)


async def _withdraw_if_queued(
    db: AsyncSession, project_id: str, entry_id: str, **values: object
) -> Optional[InboundQueueEntry]:
    """Take a queued entry out of the queue, in one statement that asks whether it still is (F328).

    Returns the row as written, or `None` where it was not queued -- absent, delivered, or already
    withdrawn by somebody else.

    Every writer that takes an entry out of `queued` without delivering it -- the operator's
    withdrawal, a refused request's withdrawal, `schedule_agent` giving up -- used to read the row,
    check `state`, and then write it by primary key. Two of them racing for one entry both passed
    their checks, and whichever committed second overwrote the first: measured, an operator's
    withdrawal that waited on a review dispatch's write lock was answered as a success while the
    row and a `queue_entry_abandoned` event said the Hub had given up on it. The condition lives in
    the `UPDATE` itself because SQLite takes the write lock at the write, not at the read, so no
    read ahead of it can close that window. Whoever writes first wins; the other matches no row.

    Committed on both branches. A statement that matched nothing still opened a write transaction,
    and a rollback would expire every row the caller holds, which under `AsyncSession` turns the
    caller's next attribute read into `MissingGreenlet`.
    """
    result = await db.execute(
        update(InboundQueueEntry)
        .where(
            InboundQueueEntry.id == entry_id,
            InboundQueueEntry.project_id == project_id,
            InboundQueueEntry.state == "queued",
        )
        .values(state="withdrawn", withdrawn_at=datetime.now(timezone.utc), **values)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if not result.rowcount:
        return None
    # **`populate_existing=True` is load-bearing** (design D11 of the change that added
    # `withdraw_refused_entry`). The `UPDATE` bypassed the identity map and the session factory is
    # built with `expire_on_commit=False`, so a copy of this row the caller already holds -- which
    # the refused-request path always does -- would otherwise be returned still reading `queued`.
    return (
        await db.execute(
            select(InboundQueueEntry)
            .where(InboundQueueEntry.id == entry_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def withdraw_entry(
    db: AsyncSession, project_id: str, entry_id: str
) -> Optional[InboundQueueEntry]:
    return await _withdraw_if_queued(db, project_id, entry_id)


async def withdraw_refused_entry(
    db: AsyncSession, project_id: str, entry_id: str, reason: str
) -> bool:
    """Withdraw an entry whose submitting request is being answered with a refusal.

    Returns whether this call is the one that withdrew it, so the caller knows whether to announce
    it. `False` means somebody got there first — `schedule_agent` withdraws at the delivery-attempt
    limit on the very path that raised the refusal, and it announces its own.

    Design D11 of the change that added this found the check unable to fire: the caller's copy of
    the row, identity-mapped and never expired, still read `state="queued"` after the scheduler's
    own session withdrew it, and `populate_existing=True` on a read was the repair. The check is now
    the `UPDATE`'s own condition, asked of the database rather than of any copy (F328), so a stale
    copy can no longer satisfy it; the re-read that remains only brings that copy up to date.
    """
    return await _withdraw_if_queued(db, project_id, entry_id, abandoned_reason=reason) is not None
