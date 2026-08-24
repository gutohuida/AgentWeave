"""APScheduler integration for AI Jobs in the Hub.

Runs inside the FastAPI lifespan, loads enabled jobs from DB,
and triggers agents when cron expressions match.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import dependency_gate
from .checkpoint_generation import render_checkpoint
from .checkpoints import latest_checkpoint_for_loop
from .conversations import (
    conversation_for_provider_session,
    inherit_runtime_overrides,
    name_conversation,
    new_conversation,
)
from .db.engine import async_session_factory
from .db.models import Agent, AIJob, Checkpoint, JobRun, Loop, Message, Question, Run, Task
from .run_task_binding import TERMINAL_FOR_BINDING
from .sse import sse_manager
from .task_transition_service import apply_transition
from .task_transitions import operator
from .utils import persist_event, short_id

logger = logging.getLogger(__name__)

_SECRET_RE = re.compile(r"(aw_live_[A-Za-z0-9_=-]+|sk-[A-Za-z0-9_=-]+|[A-Za-z0-9_=-]{32,})")


def _safe_error_summary(exc: Exception) -> str:
    return _SECRET_RE.sub("<redacted>", str(exc))[:500]


# --- Cron day-field ambiguity (finding F1) ---------------------------------------------------
#
# A cron expression that restricts BOTH day-of-month and day-of-week has two incompatible
# readings, and this repository holds both of them at once. `JobScheduler.add_job` builds an
# APScheduler `CronTrigger`, which **ANDs** the two fields, so the job fires only on days that
# satisfy both. `_do_fire_job` recomputes `job.next_run` with croniter, which **ORs** them, the
# way Vixie cron and every crontab on the operator's machine do. Measured 2026-08-23 on
# `proj-18e5d4e0`: `0 0 15 * 5` was stored with `next_run` 2026-08-28 and actually fires
# 2027-05-15 — 260 days apart, with the *displayed* value the standard-correct one and the
# behaviour the deviation.
#
# `hub/ui/src/lib/cron.ts` already declines this shape in prose (`isAmbiguousDayPair`), so the
# product had already recognised the ambiguity and still stored it. This is the same rule moved
# to the write boundary: the expression cannot be saved, so no surface has to guess which reading
# it meant. Refusing is chosen over picking a reading because either choice silently reschedules
# jobs that already exist, and because two jobs say exactly what the operator meant.

_CRON_DAY_ALIASES = {
    "sun": 0,
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
}


def _cron_value(
    token: str, minimum: int, maximum: int, aliases: Optional[Dict[str, int]]
) -> Optional[int]:
    """One bound of a cron field — a number or a three-letter alias — or ``None`` if unreadable."""
    resolved = (aliases or {}).get(token.lower())
    if resolved is None:
        resolved = int(token) if token.isdigit() else None
    if resolved is None or resolved < minimum or resolved > maximum:
        return None
    return resolved


def _cron_field_values(
    raw: str,
    minimum: int,
    maximum: int,
    aliases: Optional[Dict[str, int]] = None,
) -> Optional[Set[int]]:
    """The set of values one standard cron field selects, or ``None`` if this grammar cannot say.

    Deliberately the same subset `hub/ui/src/lib/cron.ts`'s `parseField` accepts — lists, ranges
    and steps — and deliberately no more: `L`, `W`, `#`, `?` and `~` fail to parse here and yield
    ``None``. ``None`` means *undecided*, and every caller treats undecided as "do not refuse":
    croniter and APScheduler remain the authorities on whether an expression is valid at all, and
    a validator that guessed would reject working schedules.
    """
    if not raw or not re.fullmatch(r"[0-9A-Za-z*/,-]+", raw):
        return None

    values: Set[int] = set()
    for part in raw.split(","):
        segments = part.split("/")
        if len(segments) > 2:
            return None
        spec = segments[0]
        step = 1
        if len(segments) == 2:
            if not segments[1].isdigit():
                return None
            step = int(segments[1])
            if step < 1:
                return None

        if spec == "*":
            low, high = minimum, maximum
        else:
            bounds = spec.split("-")
            if len(bounds) > 2:
                return None
            low_value = _cron_value(bounds[0], minimum, maximum, aliases)
            if low_value is None:
                return None
            if len(bounds) == 1:
                low = low_value
                # `5/15` means "from 5 to the end of the range, every 15" — the reading both
                # crontab and APScheduler give it. A bare `5` is just the one value.
                high = low_value if len(segments) == 1 else maximum
            else:
                high_value = _cron_value(bounds[1], minimum, maximum, aliases)
                # A wrapping range (`22-2`) is read differently by different implementations, so
                # it is declined rather than guessed at.
                if high_value is None or high_value < low_value:
                    return None
                low, high = low_value, high_value

        for candidate in range(low, high + 1, step):
            values.add(candidate)

    return values or None


def cron_day_ambiguity_reason(cron: str) -> Optional[str]:
    """Why *cron* cannot be scheduled unambiguously, or ``None`` when it can.

    The single caller-facing entry point for the module comment above. Returns a sentence written
    for whoever typed the expression — operator or agent — naming both restricted fields and the
    remedy, because "invalid cron" alone would read as a typo in a string that is valid everywhere
    else.
    """
    fields = cron.strip().split()
    if len(fields) != 5:
        # `add_job` refuses anything but five fields outright, and croniter's own validation runs
        # first at both write sites; nothing is added by a second opinion here.
        return None

    day_of_month = _cron_field_values(fields[2], 1, 31)
    day_of_week = _cron_field_values(fields[4], 0, 7, _CRON_DAY_ALIASES)
    if day_of_month is None or day_of_week is None:
        return None
    if len(day_of_month) == 31:
        return None
    # Day-of-week accepts both 0 and 7 for Sunday, so eight accepted values are still seven days.
    if len({0 if v == 7 else v for v in day_of_week}) == 7:
        return None

    return (
        f"'{cron}' restricts both day-of-month ('{fields[2]}') and day-of-week ('{fields[4]}'), "
        "which has two incompatible meanings: standard cron fires when EITHER matches, this "
        "scheduler fires only when BOTH fall on the same day — for some expressions that is "
        "months apart. Leave one of the two as '*'. If you meant either day, create two jobs, "
        f"one with '{fields[2]}' as the day-of-month and one with '{fields[4]}' as the day-of-week."
    )


async def _job_agent_skip_reason(
    session: AsyncSession, project_id: str, agent: str
) -> Optional[str]:
    """Return why *agent*'s scheduled jobs should not auto-fire, or `None` if they should.

    Mirrors a guard the old watchdog message-trigger path used to enforce
    (`_trigger_agent_from_message`, removed from `src/agentweave/watchdog.py` in task 3.10):
    self-registered poll-mode agents manage their own inbox polling and would double-execute
    if the Hub also spawned them directly. Checked here, against the Hub's own `Agent` table,
    rather than ported into `trigger_agent_directly` itself — that function also backs the
    manual-trigger endpoint, which has never enforced this guard; adding it there would change
    manual trigger behavior too, which nothing asked for.
    """
    from sqlalchemy import select

    result = await session.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == agent)
    )
    agent_row = result.scalars().first()
    if agent_row is None:
        return None
    if agent_row.self_registered and agent_row.contact_mode == "poll":
        return f"{agent} is a self-registered poll agent and manages its own execution"
    return None


async def _loop_agent_busy_reason(
    session: AsyncSession, project_id: str, agent: str
) -> Optional[str]:
    """Return why *agent*'s loop should not fire right now, or `None` if it should.

    **`loop-notices-and-reacts` design D4.** A loop's agent runs one turn at a time. Until this
    existed, a firing during a live turn claimed a task and queued a briefing anyway;
    `schedule_agent` then refused to *start* a second turn (`turn_scheduler.py`), one step too late
    to prevent the work. Measured: five firings during one turn produced five queued entries and
    five `JobRun`s, which the agent drains afterwards as five separate turns all briefed on the
    same task. Turning the cron up multiplies it, which is why five-minute polling could not be
    the default before this landed.

    Reads the same fact `schedule_agent` reads -- a `Run` for this agent in `running` -- so the two
    cannot disagree about whether the agent is busy. Deliberately *not* imported from
    `turn_scheduler`: that function takes the per-agent lock and starts a turn, which is the
    opposite of what a guard wants.

    **Scoped to loops by its caller**, not by this function, which only answers the question it is
    asked. A plain scheduled job firing while its agent is busy is not the same problem: its
    message is a standing instruction still true when the agent frees up, so queuing it is the
    inbound queue working as designed. A loop's briefing re-briefs the task it just claimed, and a
    second copy is stale before it is read.
    """
    from sqlalchemy import select

    running = await session.execute(
        select(Run.id)
        .where(Run.project_id == project_id, Run.agent == agent, Run.status == "running")
        .limit(1)
    )
    if running.scalar_one_or_none() is not None:
        return f"{agent} is already running a turn"
    return None


async def _loop_stop_reason(session: AsyncSession, job: AIJob) -> Optional[str]:
    """Return why *job*'s loop should stop firing, or `None` if it should proceed.

    Only ever prevents a fire the scheduler was already about to make on its own cron or a manual
    trigger (design D4, `2026-08-16-many-named-loops`) — never creates a firing, never decides what
    happens next. A job with no `Loop` row is not a loop at all and always proceeds.
    """
    result = await session.execute(select(Loop).where(Loop.job_id == job.id))
    loop = result.scalars().first()
    if loop is None:
        return None
    now = datetime.now(timezone.utc)
    stop_at = loop.stop_at
    if stop_at is not None:
        # SQLite round-trips `DateTime(timezone=True)` as naive (same trap `agent_status.py`'s
        # `heartbeat_is_stale` already guards against) — compare against an aware `now` only after
        # restoring the UTC tzinfo SQLite dropped, not the raw column value.
        if stop_at.tzinfo is None:
            stop_at = stop_at.replace(tzinfo=timezone.utc)
        if now >= stop_at:
            return f"loop stop time reached ({stop_at.isoformat()})"
    if loop.stop_when_queue_empties:
        open_count = await session.scalar(
            select(func.count(Task.id)).where(
                Task.loop_id == loop.id, Task.status.not_in(TERMINAL_FOR_BINDING)
            )
        )
        if not open_count:
            # "Empty" means *drained*, not *never filled*. A loop is created before its work
            # exists — that is the order "shorter dev loops that keep developing" implies, and
            # arming this condition at creation would disable the loop on its first tick, before
            # it had ever run anything, permanently (`job.enabled = False` below).
            #
            # Derived from the task rows rather than a flag on `Loop`: a task that has reached a
            # terminal status still carries its `loop_id`, so the queue's whole history is already
            # recorded and a column saying the same thing would be a second copy that can drift.
            ever_count = await session.scalar(
                select(func.count(Task.id)).where(Task.loop_id == loop.id)
            )
            if ever_count:
                return "loop queue is empty"
    return None


_LOOP_PENDING_REQUEST_REASON_CHARS = 300


async def _pending_loop_request(
    session: AsyncSession, job: AIJob, loop: Loop, exclude_run_id: str
) -> Optional[dict]:
    """What the loop's executor was waiting on when its queue drained (design D6).

    A loop job never resumes a conversation — task 8.1 refuses `session_mode="resume"` for one,
    for the entire lifetime of the job, not just at creation — so every firing, including the one
    that just discovered the empty queue, gets a brand-new, still-empty `Conversation`
    (`_do_fire_job` creates it before `_loop_stop_reason` runs, unconditionally). An unanswered
    `Question` this firing's OWN conversation could hold is therefore always none; "the firing's
    conversation" D6 names has to mean the most recent EARLIER firing's conversation — the one an
    `ask_user` call would actually have been asked in, if one was ever asked and never answered.
    Found via the most recent prior `JobRun` for this job that recorded one, excluding this firing
    itself (`exclude_run_id`).

    Checked before the `Message` case: an unanswered `ask_user` is a hard block on the run that
    asked it, closer to "the thing this loop was actually waiting on" than mail sitting unread in
    an inbox nobody has to check. D6 does not state a tiebreak when both exist.
    """
    prior_run_result = await session.execute(
        select(JobRun.conversation_id)
        .where(
            JobRun.job_id == job.id,
            JobRun.id != exclude_run_id,
            JobRun.conversation_id.is_not(None),
        )
        .order_by(JobRun.fired_at.desc())
        .limit(1)
    )
    prior_conversation_id = prior_run_result.scalar_one_or_none()
    if prior_conversation_id is not None:
        question_result = await session.execute(
            select(Question)
            .where(
                Question.conversation_id == prior_conversation_id,
                Question.answered == False,  # noqa: E712
            )
            .order_by(Question.created_at.desc())
        )
        question = question_result.scalars().first()
        if question is not None:
            reason = question.question
            if len(reason) > _LOOP_PENDING_REQUEST_REASON_CHARS:
                reason = reason[:_LOOP_PENDING_REQUEST_REASON_CHARS]
            return {
                "kind": "question",
                # A `Question` has no recipient field of its own — it is addressed to whichever
                # human is watching the operator UI, not to a named agent, so `to` stays null.
                "to": None,
                "reason": reason,
                "created_at": question.created_at.isoformat(),
            }

    # "addressed to the creator" is the Message model's own `recipient` field — the thing that
    # actually decides whose inbox it lands in — not a conversation match; only the Question half
    # of D6's sentence carries the "in the firing's conversation" qualifier grammatically.
    creator_agent: Optional[str] = None
    if loop.created_by_run_id:
        # Same `created_by_run_id` -> `Run.agent` resolution `questions.py`'s
        # `_asking_run_has_ended` already uses for a different row's creator — cited as precedent
        # rather than a second pattern.
        creator_run = await session.get(Run, loop.created_by_run_id)
        if creator_run is not None:
            creator_agent = creator_run.agent
    if creator_agent is not None:
        message_result = await session.execute(
            select(Message)
            .where(
                Message.sender == job.agent,
                Message.recipient == creator_agent,
                Message.read == False,  # noqa: E712
            )
            .order_by(Message.timestamp.desc())
        )
        message = message_result.scalars().first()
        if message is not None:
            reason = message.subject or message.content
            if len(reason) > _LOOP_PENDING_REQUEST_REASON_CHARS:
                reason = reason[:_LOOP_PENDING_REQUEST_REASON_CHARS]
            return {
                "kind": "message",
                "to": message.recipient,
                "reason": reason,
                "created_at": message.timestamp.isoformat(),
            }

    return None


def _loop_queue_order() -> tuple:
    """How a loop's queue is ordered when picking the current item (design D3).

    An active task, most recently touched, beats an untouched pending one; among pending tasks the
    **oldest** wins. Shared with `api/v1/jobs.py`'s `_batch_loop_summaries` so the board and the
    firing cannot disagree about which item is current — they are the two halves of human-only
    check 13.1, and a shared helper is the only way that check means anything.

    `Task.updated` is deliberately scoped to non-pending rows. It used to apply to every candidate,
    which silently inverted the pending order: two untouched pending tasks have `updated` values as
    far apart as their creation times, so `updated.desc()` picked the *newest* and the
    `created_at.asc()` tiebreak below was never reached. Found on 2026-08-19 by driving 13.1
    against a live agent — the queue claimed BRAVO (newer) while ALPHA (older) sat pending.

    The unit test did not catch it because it inserted both tasks in one transaction with only
    `created_at` set, so their `updated` values tied exactly and the tiebreak did apply. Production
    creates tasks in separate requests, where they never tie. Both derivations shared the flaw, so
    the board and the firing agreed on the wrong task — two consistent wrong answers read as a
    match, which is how it survived review.
    """
    return (
        (Task.status != "pending").desc(),
        case((Task.status != "pending", Task.updated), else_=None).desc(),
        Task.created_at.asc(),
    )


#: The statuses a loop's queue item can be in and still be the thing a firing works on.
#: Shared with `_batch_loop_summaries` (`api/v1/jobs.py`) so the board and the firing cannot
#: disagree about which item is current -- see `_loop_queue_order` for what happened the last time
#: they did.
#:
#: `assigned` is in this set as of 2026-08-19, by operator decision, and its absence was a
#: deadlock rather than an oversight. A firing claims a task by moving it `pending -> assigned`;
#: reaching `in_progress` needs the agent to call `update_task` itself, which it may simply not do.
#: With `assigned` excluded here, that task became invisible to every later firing -- while
#: `_loop_stop_reason` still counted it as open, because `TERMINAL_FOR_BINDING` is only
#: `("approved", "rejected")`. So the loop could neither claim it nor stop because of it, and fired
#: forever doing nothing. Demonstrated live on the trial Hub (`loop-33deddaf`: three firings,
#: nothing claimed, `stopped_at` still null) before this changed.
#:
#: The accepted cost is the mirror image: a task the agent genuinely cannot start is now re-claimed
#: every firing, so the loop repeats one item instead of spinning on none. That is the more visible
#: and more fixable of the two failures, which is why it was chosen.
#:
#: `revision_needed` joined on 2026-08-20, and its absence was the same shape of omission as
#: `assigned`'s: a reviewer who did everything right -- reviewed promptly and sent the work back --
#: left the loop unable to act on the outcome, because the status was in neither this tuple nor
#: `TERMINAL_FOR_BINDING`. `revision_needed -> in_progress` is `_BOTH` (`task_transitions.py`), so
#: the loop's own agent is exactly who should resume it. Two other status sets already agreed it is
#: live work -- `_ACTIVE_TASK_STATUSES` (`api/v1/agents.py`) and `_LIVE_TASK_STATUSES`
#: (`checkpoints.py`) -- and only this one dissented, which is what marks it as an oversight rather
#: than a policy. Resumed, not re-entered: like `assigned`, it is non-pending, so `_do_fire_job`
#: leaves its status alone and the agent takes it back to `in_progress` itself.
#:
#: `blocked` LEFT this tuple on 2026-08-21, and it is the one status here that moved outwards. The
#: three above were omissions -- work the loop's own agent could resume, invisible to the claim. This
#: is the opposite: `park_task_for_question` (`run_task_binding.py`) is the only way into `blocked`,
#: and `release_block_for_question` moves the task straight to `in_progress` the moment the question
#: is answered *or declined*. So a task sitting in `blocked` provably has an **unanswered** question,
#: and no agent this loop can fire is able to answer it -- the answer is what resumes the work, and
#: it arrives from a person. That puts it with `completed` and `under_review` in the stall gap:
#: someone else's turn.
#:
#: The test that separates it from `revision_needed`, which went the other way the day before, is
#: whether firing an agent makes progress *possible*. For `revision_needed` it does. For `blocked` it
#: cannot, and claiming it routed around the 2026-08-20 spin fix entirely: `_do_fire_job` consults
#: `_loop_stall_reason` only when the claim returned nothing, so a claimable `blocked` task meant an
#: agent spawned every tick against work that could not move -- while `_compose_loop_briefing` never
#: mentions `blocked_reason` or the open question, so that agent was handed a blocked task rendered
#: exactly like a fresh one. Reasoning and the second defect it caused:
#: `openspec/explorations/2026-08-21-which-band-blocked-belongs-to.md`.
CLAIMABLE_LOOP_TASK_STATUSES: tuple = (
    "in_progress",
    "assigned",
    "pending",
    "revision_needed",
)

#: The statuses that can be a loop's **current item** on the board. The claimable set plus
#: `blocked`, and the difference is not an oversight in either direction.
#:
#: **Fixed 2026-08-24. These were one constant, and that was a live defect.** `agent-loops` §85
#: says: *"WHEN a loop's queue holds a task that is in progress or blocked / THEN that task is the
#: loop's current item"*. When `blocked` left the claimable set on 2026-08-21 -- correctly, to stop
#: a firing spawning an agent every tick against work that cannot move -- `_batch_loop_summaries`
#: shared that constant for a different question and silently lost sight of blocked tasks with it.
#: A loop parked on an unanswered question then reported `queue: {blocked: 1}` and **no current
#: item**, so the surface that exists to say what a loop is waiting for said nothing was happening.
#: Reproduced before the fix; no test covered §85's blocked scenario, which is why it shipped.
#:
#: Two questions were sharing one answer: *may a firing claim this?* and *what is this loop
#: working on?* A blocked task is no to the first and yes to the second -- it is the loop's work,
#: and it is precisely what the operator needs to see. `loop-notices-and-reacts`' one-vocabulary
#: group exists for exactly this shape; this pair is the minimum correct split until it lands, and
#: should be derived from the bands rather than spelled out here once it does.
CURRENT_ITEM_TASK_STATUSES: tuple = CLAIMABLE_LOOP_TASK_STATUSES + ("blocked",)


async def candidate_is_startable(
    session: AsyncSession, task: Task
) -> "tuple[bool, Optional[dependency_gate.DependencyRefusal]]":
    """Whether one claimable-status candidate may actually be started, and the refusal if not.

    **The single statement of a rule that had two implementations.** The firing
    (`_first_startable_candidate`) and the board (`_batch_loop_summaries`) must never disagree
    about which queue item is current -- that agreement is human-only check 13.1 of
    `task-dependencies`, and until `loop-becomes-a-flow` task 1.4 it was maintained by two copies
    of this rule kept carefully in step, with a comment on the board's copy saying it "mirrors"
    the firing's. Mirroring is what drift looks like before it happens; this module's own
    `_loop_queue_order` comment records the same shape.

    The board cannot simply call `_first_startable_candidate`: that walks one loop's queue, and
    `_batch_loop_summaries` computes every job's block in six fixed queries and never one query
    per job (`jobs.py` design D7). So what is shared is the per-candidate *rule*, not the query --
    each side keeps its own traversal and both ask this the same question.

    `in_progress` is startable without a fresh gate check: it is already running, no
    `-> in_progress` transition is about to happen, and a prerequisite that regressed underneath
    it is `task-dependencies` D8's "flagged, not stopped" case rather than a reason to skip past
    it. Every other claimable status is one `apply_transition` away from `in_progress` -- the same
    edge `dependency_gate.evaluate` guards -- so it is tested against that gate here.

    `blocked` joins `in_progress` in skipping the check, for the same reason stated differently:
    nothing is about to transition it either -- it is waiting on a person. Gating it would be
    asking whether work that is not about to start is allowed to start, and a refusal would hide
    it from the board, which is the one place the operator can see that the loop is waiting on
    them. It never reaches the *claim* regardless, because `CLAIMABLE_LOOP_TASK_STATUSES` excludes
    it; only `CURRENT_ITEM_TASK_STATUSES` lets it through, so the sets do that gating and this
    rule stays single.
    """
    if task.status in ("in_progress", "blocked"):
        return True, None
    refusal = await dependency_gate.evaluate(session, task)
    return (not refusal.refuses), refusal


async def _first_startable_candidate(
    session: AsyncSession, loop: Loop
) -> "tuple[Optional[Task], list[tuple[Task, dependency_gate.DependencyRefusal]]]":
    """Walks the loop's claimable-status queue in order (design D10, `task-dependencies` section 9)
    and returns the first task the dependency gate would not refuse, plus every gated candidate
    skipped along the way -- so a firing that claims nothing can say why rather than only that it
    did not.

    `in_progress` needs no fresh gate check and is always returned immediately: it is already
    running, no `-> in_progress` transition is about to happen, and a prerequisite that regressed
    under it is D8's "flagged, not stopped" case, not a reason to skip past it. Every other
    claimable status (`pending`, `assigned`, `revision_needed`) is one `apply_transition` away from
    `in_progress` -- the same edge `dependency_gate.evaluate` guards -- so checking it here is what
    makes claimability and startability agree
    (design D10) instead of the loop re-claiming a task the gate will only refuse.

    Uses `dependency_gate.evaluate` directly rather than a second readiness computation -- two
    implementations of "are this task's dependencies met" is the exact drift shape
    `_loop_queue_order`'s own comment already records.
    """
    candidates = (
        (
            await session.execute(
                select(Task)
                .where(Task.loop_id == loop.id, Task.status.in_(CLAIMABLE_LOOP_TASK_STATUSES))
                .order_by(*_loop_queue_order())
            )
        )
        .scalars()
        .all()
    )
    gated: "list[tuple[Task, dependency_gate.DependencyRefusal]]" = []
    for task in candidates:
        startable, refusal = await candidate_is_startable(session, task)
        if not startable:
            assert refusal is not None  # only the gated branch reports not-startable
            gated.append((task, refusal))
            continue
        return task, gated
    return None, gated


async def _claim_loop_task(session: AsyncSession, loop: Loop) -> "list[Task]":
    """The queue items this firing works on (design D3): resume the loop's existing active task
    (`in_progress` or `assigned`) if one exists, else claim the oldest startable
    `pending` one -- skipping past a gated candidate in queue order rather than claiming it and
    letting the dependency gate refuse the transition (design D10, section 9).

    Shares both its candidate set (`CLAIMABLE_LOOP_TASK_STATUSES`) and its ordering
    (`_loop_queue_order`) with `_batch_loop_summaries`'s "current item" derivation, so the board
    and the firing answer the same question the same way -- they are the two halves of human-only
    check 13.1, and it only means anything if they cannot drift.

    **Set-valued, and still exactly one member** (`loop-becomes-a-flow` group 1). A flow may staff
    several tasks at once; a loop staffs one. Group 1 changes only the shape of the answer so that
    the widening in group 5 is a change to *how many* are selected rather than to every caller's
    signature at the same time. Until then this returns zero or one, and `[]` is the empty case --
    never `None`, so `if not claimed` keeps working while `len()` and iteration become safe.

    **A list, not a Python `set`.** `tasks.md` 1.3 says "set" in the sense of set-valued rather
    than scalar; read as the type it would be wrong. Iteration over a `set` of ORM rows follows
    identity hashes, so once this holds more than one member a flow would pair tasks with agents
    in an order that varies between runs -- and the proposal requires a firing to select "a task
    and an agent, both deterministically". `_loop_queue_order` is where that determinism comes
    from, so the collection has to preserve it.
    """
    task, _gated = await _first_startable_candidate(session, loop)
    return [] if task is None else [task]


@dataclass(frozen=True)
class LoopSelection:
    """One thing a firing decided to do: a task, and the agent to do it.

    **`loop-becomes-a-flow` group 2, design D2.** Until this existed a firing selected a task and
    read the agent off `AIJob.agent`, so "who works this queue" was a property of the job rather
    than of the selection. A flow needs it to be a property of the selection — a reviewer is a
    different agent for the same queue — while `AIJob.agent` stays `NOT NULL` and keeps meaning
    *the agent this job fires when nothing says otherwise*.

    Frozen because a selection is a decision already taken. Anything that wants a different agent
    makes a different selection, which is also what makes design D6 ("one agent, one task, per
    firing") checkable: it is a property of a list of these, not of mutable state.
    """

    task: Task
    agent: str


async def _select_for_firing(
    session: AsyncSession, loop: Loop, *, default_agent: str
) -> "list[LoopSelection]":
    """What this firing will do: every claimed task paired with the agent that will work it.

    The seam between *which tasks* (`_claim_loop_task`, group 1) and *who works them* (group 4's
    reviewer ladder). Today every selection takes `default_agent` -- the job's own -- which is
    exactly D2's default and is why a loop with no document behaves identically to one before this
    change existed.

    Group 4 replaces the constant with the ladder, and group 5 lets the list grow past one. Both
    land here rather than in `_do_fire_job`, so the firing never has to know how the answer was
    reached.
    """
    return [
        LoopSelection(task=task, agent=default_agent)
        for task in await _claim_loop_task(session, loop)
    ]


async def _loop_stall_reason(session: AsyncSession, loop: Loop) -> Optional[str]:
    """Why a firing that claimed nothing should be skipped rather than spawned, or `None`.

    A loop's queue has three states, and until 2026-08-20 the firing distinguished none of them:

        nothing ready YET   open work, none claimable   -> skip this firing, keep polling
        nothing LEFT        every task terminal         -> `_loop_stop_reason`, stop for good
        never filled        no tasks at all             -> fire; the agent's job is to fill it

    Only the middle case had an answer. The first presented identically to the third, so a loop
    whose tasks had all reached `completed` with nothing reviewing them spawned an agent on every
    cron tick forever, claimed nothing, and never stopped -- a status in neither
    `CLAIMABLE_LOOP_TASK_STATUSES` nor `TERMINAL_FOR_BINDING` is invisible to the claim and counted
    as open by the stop condition at the same time. Reproduced before it was fixed, in
    `test_loop_whose_tasks_are_all_completed_but_unapproved_spins`.

    `completed`, `under_review` and `blocked` are what remain in that gap, and all three belong
    there: each means "someone else's turn". An earlier version of this docstring called the first
    two "the only two", which was wrong -- `revision_needed` was a third, and it did *not* belong, so
    it became claimable on 2026-08-20 rather than stalling here. `blocked` joined the gap from the
    other direction on 2026-08-21, leaving the claim rather than entering it: its "someone else" is a
    person holding an unanswered question, which is the most literal membership of the three.
    `test_a_stalled_loop_queue_is_neither_claimable_nor_drained`
    derives the gap from the transition map instead of restating it, so the next status added to the
    machine cannot fall into it unnoticed.

    A **fourth** case joined on 2026-08-21 (`task-dependencies` design D10, section 9): every
    claimable-status candidate exists but `dependency_gate` refuses all of them. Reported
    separately from the generic "no claimable task among N open" message, and split further into
    "still awaiting approval" versus "gated on a rejected prerequisite" -- the two remedies differ
    (wait/review, or reopen the document), the same distinction `dependency_gate.DependencyRefusal`
    itself keeps between `unmet` and `rejected`. A rejected-gated queue stalls rather than stops for
    the same reason as the `completed`/`under_review` case: `rejected -> pending` is operator-only
    and reversible, and stopping the loop (`job.enabled = False`, `remove_job`) would not come back
    on its own once reversed.

    Skipping rather than stopping is deliberate: stalled is not finished. `_loop_stop_reason`'s
    branch sets `job.enabled = False` and calls `remove_job`, which for a queue waiting on a review
    that has simply not happened yet would kill the loop permanently -- and approving the task
    afterwards would not bring it back. A skipped firing costs nothing and recovers by itself on the
    next tick.

    Returns `None` for a queue that has never been filled or is fully drained, so neither the
    create-then-populate order nor `_loop_stop_reason`'s own territory is disturbed.
    """
    rows = (
        await session.execute(
            select(Task.status, func.count(Task.id))
            .where(Task.loop_id == loop.id, Task.status.not_in(TERMINAL_FOR_BINDING))
            .group_by(Task.status)
        )
    ).all()
    if not rows:
        return None

    _, gated = await _first_startable_candidate(session, loop)
    if gated:
        unmet = [task for task, refusal in gated if refusal.unmet]
        rejected = [task for task, refusal in gated if refusal.rejected]
        parts = []
        if unmet:
            parts.append(f"{len(unmet)} still awaiting a prerequisite's approval")
        if rejected:
            parts.append(
                f"{len(rejected)} gated on a rejected prerequisite that will not clear on its own"
            )
        return "loop queue is stalled: " + "; ".join(parts)

    total = sum(count for _, count in rows)
    breakdown = ", ".join(f"{count} {status}" for status, count in sorted(rows))
    return f"loop queue is stalled: no claimable task among {total} open ({breakdown})"


async def finalize_job_run_for_conversation(
    session: AsyncSession, conversation_id: Optional[str], final_status: str
) -> None:
    """Flip a firing's `JobRun` out of "in progress" once its `Run` has ended (design D13,
    task A4.3). `conversation_id` is the only correlation `JobRun` and `Run` share — there is
    no direct foreign key (see `models.py`'s own comment on `JobRun.conversation_id`).

    Most runs are not job firings at all (a message or a delegation starts a `Run` too), so
    finding no matching row here is the common case, not an error. At most one `JobRun` should
    be "in_progress" for a given `conversation_id` at a time — a session-resuming job's earlier
    firings already reached a terminal status before this one was created — but the query still
    orders newest-first and takes one row rather than assuming that invariant holds.
    """
    if conversation_id is None:
        return
    result = await session.execute(
        select(JobRun)
        .where(JobRun.conversation_id == conversation_id, JobRun.status == "in_progress")
        .order_by(JobRun.fired_at.desc())
    )
    job_run = result.scalars().first()
    if job_run is not None:
        job_run.status = final_status


# Consumer-side cap on a rendered checkpoint's contribution to a briefing (design D5). A
# checkpoint body is already a bounded generator-side summary
# (`checkpoint_generation._TRANSCRIPT_CHAR_LIMIT`), so this budget is far smaller: 4,000
# characters comfortably fits one well-formed checkpoint in full, with room left for the claimed
# task and queue summary around it, and only ever truncates the pathological case (a checkpoint
# that failed to stay terse), never the common one.
_LOOP_BRIEFING_CHECKPOINT_CHARS = 4_000


def _stage_pending_loop_edit(loop: Loop) -> Optional[dict]:
    """Move a staged edit (design D11, task A2.2) from `loop`'s pending_* columns onto its live
    fields, in memory only — no commit, no event. Returns the audit payload for
    `_emit_loop_edit_applied` below, or `None` if nothing was staged.

    Applied once, at the very top of `_do_fire_job`'s handling of *loop* — before
    `_loop_stop_reason` and before `_compose_loop_briefing` are ever consulted, so both see the
    loop's current definition rather than one waiting on the firing after next. Deliberately does
    not commit or persist an event itself: `_do_fire_job` is about to mutate `run`'s status too,
    and a premature commit here would write that row to the database mid-update (transiently
    "fired" before a stop check turns it "skipped" moments later) — the caller commits everything
    together once its own branch knows the firing's final outcome, then calls
    `_emit_loop_edit_applied`.

    A firing already under way when the edit was staged (task A2.3) is unaffected by construction:
    `_do_fire_job` loads and applies pending edits exactly once, at the start of its own firing —
    nothing re-reads `loop.purpose`/`loop.stop_at`/`loop.stop_when_queue_empties` mid-turn, so a
    `PATCH` landing while an agent is still working on this firing only ever affects the *next*
    one.
    """
    if loop.pending_edit_at is None:
        return None

    changes: dict[str, Any] = {}
    if loop.pending_purpose is not None:
        changes["purpose"] = {"from": loop.purpose, "to": loop.pending_purpose}
        loop.purpose = loop.pending_purpose
    if loop.pending_stop_at is not None:
        changes["stop_at"] = {
            "from": loop.stop_at.isoformat() if loop.stop_at else None,
            "to": loop.pending_stop_at.isoformat(),
        }
        loop.stop_at = loop.pending_stop_at
    if loop.pending_stop_when_queue_empties is not None:
        changes["stop_when_queue_empties"] = {
            "from": loop.stop_when_queue_empties,
            "to": loop.pending_stop_when_queue_empties,
        }
        loop.stop_when_queue_empties = loop.pending_stop_when_queue_empties

    actor = loop.pending_edit_actor
    staged_at = loop.pending_edit_at

    loop.pending_purpose = None
    loop.pending_stop_at = None
    loop.pending_stop_when_queue_empties = None
    loop.pending_edit_actor = None
    loop.pending_edit_at = None

    return {
        "id": loop.id,
        "project_id": loop.project_id,
        "actor": actor,
        "staged_at": staged_at.isoformat() if staged_at else None,
        "changes": changes,
    }


async def _emit_loop_edit_applied(session: AsyncSession, payload: dict) -> None:
    """Persist and broadcast the audit event (task A2.5) for a pending edit
    `_stage_pending_loop_edit` already applied in memory. Called only after the caller's own
    commit has landed `run`'s final status, so this never forces an early, partial commit."""
    actor = payload["actor"]
    await persist_event(
        session,
        payload["project_id"],
        "loop_edit_applied",
        payload,
        agent=None if actor in (None, "operator") else actor,
        loop_id=payload["id"],
    )
    await sse_manager.broadcast(payload["project_id"], "loop_edit_applied", payload)


async def _compose_loop_briefing(
    session: AsyncSession,
    loop: Loop,
    claimed_task: Optional[Task],
    prior_checkpoint: Optional[Checkpoint],
) -> str:
    """The context a loop firing gets ahead of the operator's own message (design D5): purpose,
    the claimed queue item, the prior firing's checkpoint if one exists, and a one-line queue
    summary — in that order. A prefix, never a replacement: `_do_fire_job` puts `job.message`
    after this unchanged, so the operator's own message template still reads exactly as authored.
    """
    lines: list[str] = ["# Loop briefing", ""]

    if loop.purpose:
        lines.append(f"Purpose: {loop.purpose}")
        lines.append("")

    if claimed_task is not None:
        lines.append(f"## Current task: {claimed_task.title}")
        lines.append("")
        if claimed_task.description:
            lines.append(claimed_task.description)
            lines.append("")
        criteria = claimed_task.acceptance_criteria or []
        if criteria:
            lines.append("Acceptance criteria:")
            lines.extend(f"- {criterion}" for criterion in criteria)
            lines.append("")

    if prior_checkpoint is not None:
        # Reuses the same rendering a human reader gets (`render_checkpoint`) rather than
        # inventing a second serialisation of the same data (design D5). Truncated from the end
        # on overflow — re-ordering `render_checkpoint`'s own section order to drop the oldest
        # content first would only matter for the rare pathological case this cap exists to
        # bound, not worth the complexity for it.
        rendered = render_checkpoint(prior_checkpoint)
        if len(rendered) > _LOOP_BRIEFING_CHECKPOINT_CHARS:
            rendered = rendered[:_LOOP_BRIEFING_CHECKPOINT_CHARS]
        lines.append("## Prior checkpoint")
        lines.append("")
        lines.append(rendered)
        lines.append("")

    # Same per-status group-by `_batch_loop_summaries` already computes (`api/v1/jobs.py:136-143`)
    # recomputed directly here rather than imported — L6's own precedent already rejected an
    # api-layer-to-scheduler cross-import for a similarly small query. Bucketed into open/done
    # using the same `TERMINAL_FOR_BINDING` split `_loop_stop_reason` above already uses to decide
    # whether this loop's queue is empty, rather than a second, differently-drawn line.
    counts_result = await session.execute(
        select(Task.status, func.count()).where(Task.loop_id == loop.id).group_by(Task.status)
    )
    open_count = 0
    done_count = 0
    for task_status, count in counts_result.all():
        if task_status in TERMINAL_FOR_BINDING:
            done_count += count
        else:
            open_count += count
    lines.append(f"Queue: {open_count} open, {done_count} done")
    lines.append("")

    return "\n".join(lines)


# Singleton scheduler instance
_scheduler_instance: Optional["JobScheduler"] = None


def get_scheduler() -> Optional["JobScheduler"]:
    """Get the global scheduler instance."""
    return _scheduler_instance


async def _scheduled_job_runner(job_id: str) -> None:
    """Module-level function so APScheduler can pickle it for the job store."""
    scheduler = get_scheduler()
    if scheduler:
        await scheduler._fire_job_by_id(job_id)


class JobScheduler:
    """Wraps APScheduler for AI Job execution."""

    def __init__(self) -> None:
        self.scheduler: Optional[Any] = None
        self._job_id_map: dict = {}  # job_id -> apscheduler_job_id

    async def start(self) -> None:
        """Start the scheduler and load all enabled jobs from DB."""
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        # Create job store using our database
        job_store = SQLAlchemyJobStore(
            engine=self._get_sync_engine(),
            tablename="apscheduler_jobs",
        )

        self.scheduler = AsyncIOScheduler(
            jobstores={"default": job_store},
            job_defaults={
                "misfire_grace_time": 60,
                "coalesce": True,
            },
            timezone="UTC",  # Use UTC for consistent scheduling
        )

        self.scheduler.start()

        # Load enabled jobs from DB
        async with async_session_factory() as session:
            q = select(AIJob).where(AIJob.enabled == True)  # noqa: E712
            result = await session.execute(q)
            jobs = result.scalars().all()

            for job in jobs:
                await self.add_job(job)

        logger.info(f"JobScheduler started with {len(jobs)} job(s)")

    def _get_sync_engine(self) -> Any:
        """Get a sync SQLAlchemy engine for APScheduler jobstore."""
        from sqlalchemy import create_engine

        from .config import settings

        # Convert async URL to sync URL
        url = settings.database_url
        if url.startswith("sqlite+aiosqlite"):
            url = url.replace("sqlite+aiosqlite", "sqlite")
        elif url.startswith("postgresql+asyncpg"):
            url = url.replace("postgresql+asyncpg", "postgresql")

        return create_engine(url)

    async def shutdown(self) -> None:
        """Shutdown the scheduler."""
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
            logger.info("JobScheduler shutdown")

    async def add_job(self, job: AIJob) -> bool:
        """Add a job to the scheduler."""
        if not self.scheduler:
            return False

        try:
            from apscheduler.triggers.cron import CronTrigger

            # Parse cron expression
            cron_parts = job.cron.split()
            if len(cron_parts) != 5:
                logger.error(f"Invalid cron expression for job {job.id}: {job.cron}")
                return False

            trigger = CronTrigger(
                minute=cron_parts[0],
                hour=cron_parts[1],
                day=cron_parts[2],
                month=cron_parts[3],
                day_of_week=cron_parts[4],
                timezone="UTC",  # Use UTC for consistent scheduling
            )

            # Add job to scheduler
            aps_job = self.scheduler.add_job(
                func=_scheduled_job_runner,
                trigger=trigger,
                id=job.id,
                args=[job.id],
                replace_existing=True,
            )

            self._job_id_map[job.id] = aps_job.id
            logger.debug(f"Added job {job.id} to scheduler")
            return True

        except Exception as e:
            logger.error(f"Failed to add job {job.id} to scheduler: {e}")
            return False

    async def update_job(self, job: AIJob) -> bool:
        """Update a job in the scheduler (re-add with new cron)."""
        # Remove and re-add to update trigger
        await self.remove_job(job.id)
        if job.enabled:
            return await self.add_job(job)
        return True

    async def remove_job(self, job_id: str) -> bool:
        """Remove a job from the scheduler."""
        if not self.scheduler:
            return False

        try:
            self.scheduler.remove_job(job_id)
            self._job_id_map.pop(job_id, None)
            logger.debug(f"Removed job {job_id} from scheduler")
            return True
        except Exception:
            # Job might not exist in scheduler
            return False

    async def _prune_job_history(self, session: AsyncSession, job_id: str, keep: int = 100) -> None:
        """Prune old job runs, keeping only the most recent `keep` entries.

        Called automatically after each job fire to maintain history size.
        """
        from sqlalchemy import delete, select

        from .db.models import JobRun

        try:
            # Get IDs of runs to delete (all but the most recent `keep`)
            subq = (
                select(JobRun.id)
                .where(JobRun.job_id == job_id)
                .order_by(JobRun.fired_at.desc())
                .offset(keep)
                .subquery()
            )
            delete_stmt = delete(JobRun).where(JobRun.id.in_(select(subq.c.id)))
            result = await session.execute(delete_stmt)
            if result.rowcount:
                logger.debug(f"Pruned {result.rowcount} old runs for job {job_id}")
        except Exception as e:
            # Log but don't fail the job fire if pruning fails
            logger.warning(f"Failed to prune job history for {job_id}: {e}")

    async def _fire_job_by_id(self, job_id: str) -> None:
        """Fire a job by ID (lookup from DB)."""
        async with async_session_factory() as session:
            job = await session.get(AIJob, job_id)
            if job and job.enabled:
                await self._fire_job_internal(job, trigger="scheduled", session=session)

    async def _fire_job_internal(
        self,
        job: AIJob,
        trigger: str = "scheduled",
        session: Optional[AsyncSession] = None,
    ) -> bool:
        """Fire a job through the Hub's direct execution path (task 3.10).

        Delegates to `_do_fire_job`, which spawns the agent directly — no synthetic
        `Message` for the watchdog to detect and re-trigger.
        """
        # If session provided, use it; otherwise create our own
        if session is not None:
            return await self._do_fire_job(job, trigger, session)

        async with async_session_factory() as new_session:
            return await self._do_fire_job(job, trigger, new_session)

    async def _do_fire_job(
        self,
        job: AIJob,
        trigger: str,
        session: AsyncSession,
    ) -> bool:
        """Fire *job* through the Hub's direct execution path (task 3.10).

        No synthetic `Message`, no watchdog message-scanning round trip — the outcome
        (fired, skipped, or a concrete failure reason) is known synchronously, unlike the
        old message-based protocol, which could only ever record "fired" and never learned
        whether the watchdog actually managed to trigger anything.
        """
        from .inbound_queue import new_entry
        from .turn_scheduler import schedule_agent

        try:
            fired_at = datetime.now(timezone.utc)

            # `job.last_run`/`job.run_count` are NOT stamped here (finding F11). Every skip branch
            # below returns after this point, so a counter incremented here would describe "the
            # scheduler considered this job", not "this job ran" — measured on 2026-08-23 as
            # `run_count` 9 for 4 firings that actually spawned an agent, with `last_run` pointing
            # at a skip. Both are stamped once, further down, at the same point `run.status`
            # becomes `in_progress`: the firing reached a queued entry. `next_run` below is
            # different and stays here — the schedule advances whether or not the firing did work,
            # and a `next_run` left in the past would be its own lie.

            # Recompute next run
            try:
                from croniter import croniter

                itr = croniter(job.cron, fired_at)
                job.next_run = itr.get_next(datetime)
            except Exception:
                job.next_run = None

            resume_session_id = job.last_session_id if job.session_mode == "resume" else None
            conversation = None
            if resume_session_id:
                conversation = await conversation_for_provider_session(
                    session,
                    project_id=job.project_id,
                    agent=job.agent,
                    provider_session_id=resume_session_id,
                )
            # Loaded before the `JobRun` exists, because the busy guard below must be able to
            # return without writing one at all (design D4, task 1.4) and it only applies to loops.
            loop_result = await session.execute(select(Loop).where(Loop.job_id == job.id))
            loop = loop_result.scalars().first()

            if loop is not None:
                busy_reason = await _loop_agent_busy_reason(session, job.project_id, job.agent)
                if busy_reason:
                    # **Records nothing.** No `JobRun`, and no event either: the agent's own
                    # running `Run` already carries the fact that it is working, and
                    # `_batch_loop_summaries` reads exactly that row to report the loop as firing.
                    # A row here would duplicate it and, at a five-minute tick, evict real history
                    # through `_prune_job_history`'s 100-row window -- which is the problem this
                    # guard exists to prevent, reintroduced by its own bookkeeping.
                    #
                    # The commit is still needed: `job.next_run` was advanced above, and a refused
                    # firing that left it in the past would be its own lie. Nothing else is dirty
                    # at this point, so this persists the schedule and no more.
                    await session.commit()
                    logger.debug(f"Job {job.id} fire refused: {busy_reason}")
                    return False

            # Create run record
            run_id = f"run-{short_id()}"
            run = JobRun(
                id=run_id,
                job_id=job.id,
                project_id=job.project_id,
                fired_at=fired_at,
                status="fired",
                trigger=trigger,
                session_id=resume_session_id,
                conversation_id=conversation.id if conversation is not None else None,
            )
            session.add(run)

            # Prune old history (keep last 100 runs per job)
            await self._prune_job_history(session, job.id)

            skip_reason = await _job_agent_skip_reason(session, job.project_id, job.agent)
            if skip_reason:
                run.status = "skipped"
                run.error_summary = skip_reason
                await session.commit()
                await persist_event(
                    session,
                    job.project_id,
                    "job_run_skipped",
                    {
                        "job_id": job.id,
                        "job_name": job.name,
                        "agent": job.agent,
                        "trigger": trigger,
                        "run_id": run_id,
                        "reason": skip_reason,
                    },
                    agent=job.agent,
                )
                logger.info(f"Job {job.id} fire skipped: {skip_reason}")
                return False

            # Design D11 (task A2.2): stage-apply any pending edit in memory before the stop check
            # below and before the briefing is composed further down — both must see this loop's
            # current definition, not one still waiting on the firing after next. The audit event
            # is emitted only after this branch's own commit lands `run`'s final status (below),
            # not here — see `_stage_pending_loop_edit`'s own comment for why.
            pending_edit_payload = _stage_pending_loop_edit(loop) if loop is not None else None

            loop_stop_reason = await _loop_stop_reason(session, job)
            if loop_stop_reason:
                run.status = "skipped"
                run.error_summary = loop_stop_reason
                if loop is not None:
                    loop.stop_reason = loop_stop_reason
                    loop.stopped_at = fired_at
                    # D17/B2.5: the same string `_loop_stop_reason` returns for a drained queue,
                    # already the trigger for `loop_queue_exhausted` below — the one place this
                    # value is known, so it is set here rather than re-derived by a reader later.
                    loop.ending_state = (
                        "completed" if loop_stop_reason == "loop queue is empty" else "stopped"
                    )
                job.enabled = False
                await session.commit()
                if pending_edit_payload is not None:
                    await _emit_loop_edit_applied(session, pending_edit_payload)
                await persist_event(
                    session,
                    job.project_id,
                    "job_run_skipped",
                    {
                        "job_id": job.id,
                        "job_name": job.name,
                        "agent": job.agent,
                        "trigger": trigger,
                        "run_id": run_id,
                        "reason": loop_stop_reason,
                    },
                    agent=job.agent,
                )
                loop_stopped_payload = {
                    "job_id": job.id,
                    "loop_id": loop.id if loop is not None else None,
                    "reason": loop_stop_reason,
                }
                await persist_event(
                    session,
                    job.project_id,
                    "loop_stopped",
                    loop_stopped_payload,
                    agent=job.agent,
                    loop_id=loop.id if loop is not None else None,
                )
                await sse_manager.broadcast(job.project_id, "loop_stopped", loop_stopped_payload)
                if loop is not None and loop_stop_reason == "loop queue is empty":
                    # A second, independent event (design D6) — "the queue is empty" and "was a
                    # request in flight when it emptied" are two facts a reader should not have to
                    # parse out of one payload. `loop_stopped` above is unchanged by this branch.
                    pending_request = await _pending_loop_request(
                        session, job, loop, exclude_run_id=run_id
                    )
                    loop_queue_exhausted_payload = {
                        "job_id": job.id,
                        "loop_id": loop.id,
                        "pending_request": pending_request,
                    }
                    await persist_event(
                        session,
                        job.project_id,
                        "loop_queue_exhausted",
                        loop_queue_exhausted_payload,
                        agent=job.agent,
                        loop_id=loop.id,
                    )
                    await sse_manager.broadcast(
                        job.project_id, "loop_queue_exhausted", loop_queue_exhausted_payload
                    )
                # Remove from the live scheduler so it does not fire again next cron tick only to be
                # skipped again — the same call `remove_job` already makes for a job an operator
                # disables by hand.
                await self.remove_job(job.id)
                logger.info(f"Job {job.id} loop stopped: {loop_stop_reason}")
                return False

            content = job.message
            # Who this firing is actually for. `job.agent` until a selection says otherwise
            # (design D2) — a job with no loop has no selection to say anything, so it stays the
            # job's own agent and this variable changes nothing for it.
            acting_agent = job.agent
            if loop is not None:
                # Set-valued as of `loop-becomes-a-flow` group 1, and carrying its own agent as
                # of group 2 (design D2). Still at most one member until group 5 widens it, so the
                # firing keeps its single-selection shape and unwraps at this boundary.
                selections = await _select_for_firing(session, loop, default_agent=job.agent)
                selection = selections[0] if selections else None
                claimed_task = selection.task if selection is not None else None
                if claimed_task is None:
                    stall_reason = await _loop_stall_reason(session, loop)
                    if stall_reason:
                        # Skipped, not stopped: the job stays enabled and stays in the live
                        # scheduler, so the next tick picks the queue up the moment something
                        # becomes claimable again. See `_loop_stall_reason` for why this is not
                        # the `_loop_stop_reason` branch above.
                        run.status = "skipped"
                        run.error_summary = stall_reason
                        await session.commit()
                        if pending_edit_payload is not None:
                            await _emit_loop_edit_applied(session, pending_edit_payload)
                        await persist_event(
                            session,
                            job.project_id,
                            "job_run_skipped",
                            {
                                "job_id": job.id,
                                "job_name": job.name,
                                "agent": job.agent,
                                "trigger": trigger,
                                "run_id": run_id,
                                "reason": stall_reason,
                            },
                            agent=job.agent,
                            loop_id=loop.id,
                        )
                        logger.info(f"Job {job.id} fire skipped: {stall_reason}")
                        return False
                if claimed_task is not None:
                    # Only a `pending` task is *entered*; `assigned`/`in_progress` are being
                    # resumed, so their status stays untouched (design D3). `assigned` became
                    # reachable here on 2026-08-19 — see CLAIMABLE_LOOP_TASK_STATUSES — which is
                    # exactly the resume case this branch already guarded for.
                    if claimed_task.status == "pending":
                        await apply_transition(session, claimed_task, "assigned", operator())
                    # The selection's agent, not the job's: from group 2 these differ whenever a
                    # flow staffs a task with someone other than the job's own agent, and a task
                    # assigned to the job's agent while another works it is the first place that
                    # divergence would become a lie the board repeats.
                    claimed_task.assignee = selection.agent
                # `selection` is None on the "never filled" queue — no task, but the firing still
                # proceeds, because filling the queue is the agent's job (`_loop_stall_reason`).
                # That firing is for the job's own agent, which `acting_agent` already holds.
                if selection is not None and selection.agent != job.agent:
                    acting_agent = selection.agent
                    # A conversation found above was looked up for *the job's* agent, before this
                    # firing knew who it was for. Reusing it would put one agent's turn in another
                    # agent's thread. A fresh conversation for the acting agent is the only
                    # correct answer here; resuming a provider session across a change of agent is
                    # not a thing this product does.
                    #
                    # The deeper fix is ordering: `_job_agent_skip_reason` and the resume lookup
                    # both run before the claim and both take `job.agent`, so they answer about
                    # the wrong agent whenever a selection diverges. Restructuring that region is
                    # `loop-notices-and-reacts`' firing-decision work, not this group's — until
                    # then this guard keeps the divergence from producing a wrong thread.
                    conversation = None
                    resume_session_id = None
                prior_checkpoint = await latest_checkpoint_for_loop(session, loop.id)
                briefing = await _compose_loop_briefing(
                    session, loop, claimed_task, prior_checkpoint
                )
                content = f"{briefing}\n{job.message}"

            # Refused firings leave no conversation implying work happened. Resume lookup stays
            # above the refusal points so an existing conversation is still reused, but a new row
            # is created only once the firing is known to proceed.
            if conversation is None:
                conversation = new_conversation(
                    project_id=job.project_id, agent=acting_agent, origin="job"
                )
                if resume_session_id:
                    conversation.provider_session_id = resume_session_id
                session.add(conversation)
                await inherit_runtime_overrides(session, conversation)
            # Named from the job, not its message: a schedule fires the same message repeatedly,
            # and the job's name is what the operator recognises the thread by.
            name_conversation(conversation, job.name)
            run.conversation_id = conversation.id

            entry = new_entry(
                project_id=job.project_id,
                agent=acting_agent,
                origin_type="job",
                content=content,
                hop_depth=0,
                session_mode=job.session_mode,
                session_id=resume_session_id,
                conversation_id=conversation.id,
            )
            session.add(entry)
            # The firing genuinely becomes "in progress" here, not at `JobRun` creation above —
            # `status="fired"` there only means "successfully enqueued"; every early-return
            # above this point (skip, loop-stopped) overwrites it with `"skipped"` first, so
            # only a firing that actually reaches a queued entry ever becomes "in_progress"
            # (design D13, task A4.3). `finalize_job_run_for_conversation` flips it to a
            # terminal status once the agent's own `Run` ends (`agent_trigger.py`).
            run.status = "in_progress"
            # F11: the job's own counters are stamped at exactly this boundary, for exactly the
            # reason the paragraph above gives for `in_progress` — this is where a firing stops
            # being a consideration and becomes work. A `schedule_agent` failure below still
            # counts: the entry is queued and the job did fire; only the turn did not start.
            job.last_run = fired_at
            job.run_count += 1
            await session.commit()

            if pending_edit_payload is not None:
                await _emit_loop_edit_applied(session, pending_edit_payload)

            queue_payload = {
                "entry_id": entry.id,
                "agent": acting_agent,
                "origin_type": "job",
                "hop_depth": 0,
                "job_id": job.id,
                "conversation_id": conversation.id,
            }
            await persist_event(
                session, job.project_id, "queue_entry_queued", queue_payload, agent=acting_agent
            )
            await sse_manager.broadcast(job.project_id, "queue_entry_queued", queue_payload)
            schedule_result = await schedule_agent(job.project_id, acting_agent)
            if schedule_result.waiting_reason and schedule_result.terminal_failure:
                # This is the same terminal outcome startup reconciliation would eventually
                # record, reached honestly at the moment the Hub knows no turn began. Reusing
                # `failed` also keeps JobCard's existing error-summary presentation.
                run.status = "failed"
                run.error_summary = schedule_result.waiting_reason
                await session.commit()

            await sse_manager.broadcast(
                job.project_id,
                "job_fired",
                {
                    "id": job.id,
                    "name": job.name,
                    "agent": acting_agent,
                    "trigger": trigger,
                    "run_id": run_id,
                },
            )

            await persist_event(
                session,
                job.project_id,
                "job_fired",
                {
                    "job_id": job.id,
                    "job_name": job.name,
                    "agent": acting_agent,
                    "trigger": trigger,
                    "run_id": run_id,
                },
                agent=acting_agent,
            )

            logger.info(f"Job {job.id} fired (trigger: {trigger})")
            return True

        except Exception as e:
            error_summary = _safe_error_summary(e)
            logger.error(f"Failed to fire job {job.id}: {error_summary}")
            # Mark run as failed
            if "run" in locals():
                run.status = "failed"
                run.error_summary = error_summary
                await persist_event(
                    session,
                    job.project_id,
                    "job_run_failed",
                    {
                        "job_id": job.id,
                        "job_name": job.name,
                        "agent": acting_agent,
                        "trigger": trigger,
                        "run_id": run.id,
                        "error_summary": error_summary,
                    },
                    agent=acting_agent,
                    severity="error",
                )
                await session.commit()
            return False


async def init_scheduler() -> JobScheduler:
    """Initialize and start the global scheduler."""
    global _scheduler_instance
    _scheduler_instance = JobScheduler()
    await _scheduler_instance.start()
    return _scheduler_instance


async def shutdown_scheduler() -> None:
    """Shutdown the global scheduler."""
    global _scheduler_instance
    if _scheduler_instance:
        await _scheduler_instance.shutdown()
        _scheduler_instance = None
