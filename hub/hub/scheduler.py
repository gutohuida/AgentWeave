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

from . import dependency_gate, requirement_evidence
from .checkpoint_generation import render_checkpoint
from .checkpoints import checkpoint_by_task_author, latest_checkpoint_for_loop
from .conversations import (
    conversation_for_provider_session,
    inherit_runtime_overrides,
    name_conversation,
    new_conversation,
)
from .db.engine import async_session_factory
from .db.models import Agent, AIJob, Checkpoint, JobRun, Loop, Message, Question, Run, Task
from .loop_ending import QUEUE_DRAINED_REASON, end_loop
from .run_task_binding import TERMINAL_FOR_BINDING, tasks_held_by_a_running_turn
from .sse import sse_manager
from .task_transition_service import apply_transition
from .task_transitions import (
    CLAIMABLE_STATUSES,
    CURRENT_ITEM_STATUSES,
    REVIEWABLE_STATUSES,
    WITH_REVIEWER_STATUSES,
    operator,
)
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


async def _agents_running_a_turn(session: AsyncSession, project_id: str) -> "Set[str]":
    """Every agent in this project with a `Run` in `running`.

    The set-valued form of the fact `_loop_agent_busy_reason` and `schedule_agent` both read, added
    for `loop-becomes-a-flow` design D12. A wide firing asks the question about several agents in
    one walk, and asking it one agent at a time would be one query per candidate; more importantly
    it would be a *third* place the question is asked, which is the drift shape this module's own
    comments record going wrong twice.
    """
    return set(
        (
            await session.execute(
                select(Run.agent).where(Run.project_id == project_id, Run.status == "running")
            )
        )
        .scalars()
        .all()
    )


async def _loop_flow_busy_reason(
    session: AsyncSession, project_id: str, agent: str
) -> Optional[str]:
    """Why a firing should be refused outright, recording nothing — or `None` to proceed.

    **This is `_loop_agent_busy_reason` narrowed for a flow (design D12).** That guard refuses the
    whole firing when the *job's* agent is running, on the stated grounds that "a loop's agent runs
    one turn at a time". True of a loop; false of a flow, where `job.agent` is only D2's default.
    Left as it was, the moment a flow staffed its own job's agent, every tick for the length of
    that turn refused to staff any *other* free agent on any *other* independent task — so width
    was reachable only inside a tick that happened to find the job's agent idle, which is the one
    state a working flow is least often in.

    So the refusal now needs both halves: the job's agent is busy **and** nobody else could be
    staffed instead. A single-agent loop reaches that by the general rule with no branch of its own
    — its one agent is the busy one and the free list is empty — which is what keeps this exactly
    as strict as before for every loop that exists today, including the "records nothing" property
    the old guard's docstring argues for at length. A firing that proceeds past this and then
    resolves nobody falls into the ordinary stall path instead, which is the right place for it:
    something was staffable in principle and was not staffed, and that is a fact about the queue.
    """
    busy_reason = await _loop_agent_busy_reason(session, project_id, agent)
    if busy_reason is None:
        return None
    if await _agents_that_are_free(session, project_id):
        return None
    return busy_reason


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
                return QUEUE_DRAINED_REASON
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
CLAIMABLE_LOOP_TASK_STATUSES: tuple = tuple(sorted(CLAIMABLE_STATUSES))

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
CURRENT_ITEM_TASK_STATUSES: tuple = tuple(sorted(CURRENT_ITEM_STATUSES))

#: The statuses a firing may claim **only after asking who is claiming** (`loop-becomes-a-flow`
#: design D3). `completed`, and nothing else today.
#:
#: Kept separate from `CLAIMABLE_LOOP_TASK_STATUSES` rather than added to it, which task 3.3 names
#: as the obvious wrong fix: that tuple answers a question about a status alone, and this one has
#: no answer without an actor. Widening it would say "any agent may claim finished work", which is
#: false for exactly one agent -- the one that finished it -- and that agent is the only one the
#: rule exists to stop.
REVIEWABLE_LOOP_TASK_STATUSES: tuple = tuple(sorted(REVIEWABLE_STATUSES))

#: The statuses meaning a reviewer already holds the task, claimable by nobody (finding F45).
#:
#: A firing that staffs a review moves the task here in the same commit that queues the turn --
#: `enter_selected_task` -- which is what takes it out of `REVIEWABLE_LOOP_TASK_STATUSES` and
#: stops the next tick offering the same finished work to the same reviewer again.
WITH_REVIEWER_LOOP_TASK_STATUSES: tuple = tuple(sorted(WITH_REVIEWER_STATUSES))


async def task_is_claimable_by(session: AsyncSession, task: Task, agent: str) -> bool:
    """Whether *agent* may be fired for *task* (`loop-becomes-a-flow` design D3).

    Claimability stopped being a property of a status here and became a question about a *(task,
    agent)* pair. Only one band needs the actor: a task in `completed` is claimable by anybody
    except the agent recorded as completing it, which is the whole review mechanism -- no handoff
    message, no review task row, nothing asked of the finishing agent that could be omitted.

    **`_agent_that_completed` is called rather than reimplemented, and that is the correctness
    property rather than tidiness.** It is the same determination `_guard_author_is_not_reviewer`
    reads for `-> approved`/`rejected`/`revision_needed`, so a task this function offers an agent
    can never be one that agent is then refused for approving. Two implementations of "who finished
    this" would be free to drift into exactly that contradiction, and the loop would fire an agent
    at work it is structurally unable to sign off -- forever, since the refusal changes nothing
    about the queue.

    A `completed` task with **no recorded completer** is claimable by nobody, and this is the one
    place the two functions deliberately diverge. `_guard_author_is_not_reviewer` treats an unknown
    completer as *permitting*, which is right for a refusal: a guard that blocked every move it
    could not attribute would stop legitimate work over a missing history row. It is exactly wrong
    for an **offer**. Handing finished work to an agent the Hub cannot rule out as its author, when
    the guard will then also fail to rule it out, is self-approval reached by two permissive
    defaults agreeing -- the guard bypassed entirely, for precisely the tasks whose provenance is
    unknown.

    So the asymmetry is the safe direction of each: refuse to offer, permit to act. The cost is a
    task completed before the transition table existed, or written straight into the status, which
    the flow will not staff for review; it stalls the queue and the operator reviews it, which is
    what happens today and is a state the operator can see and resolve. Every task that reaches
    `completed` through `apply_transition` records its completer, so this is the legacy and
    hand-written case only.

    **Found by a hang, not by reasoning.** The first version of this returned `completed_by !=
    agent`, which for `None` is `True`; `test_scheduler.py`'s spin test constructs its completed
    tasks directly, so the firing claimed one and spawned an agent the fixture had no reads queued
    for. Chasing that back is what surfaced the self-approval route above.
    """
    if task.status in CLAIMABLE_LOOP_TASK_STATUSES:
        return True
    if task.status not in REVIEWABLE_LOOP_TASK_STATUSES:
        return False
    from .task_transition_service import _agent_that_completed

    completed_by = await _agent_that_completed(session, task.id)
    if completed_by is None:
        return False
    return completed_by != agent


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

    **`completed` joins them in `loop-becomes-a-flow` group 3, and this was caught by reviewing the
    spec against this function rather than by a failing test.** A `completed` task claimed for
    review is not one `apply_transition` away from `in_progress` -- it is one away from a review
    outcome, which `dependency_gate.evaluate` does not guard. Asking the gate about it would refuse
    finished work its *own* prerequisite had not cleared, and whether a prerequisite is approved
    has nothing whatever to do with whether the work may be looked at. The consequence of getting
    it wrong is quiet: the task is skipped from review, the queue stalls citing a gate, and the
    remedy the stall names is one nobody can act on.

    **`under_review` joins them for finding F45**, and the reason is the previous paragraph's,
    one step later: a task a reviewer already holds is not one `apply_transition` away from
    `in_progress` either -- it is one away from `approved` or `revision_needed`. The gate has no
    question to answer about it, and asking would produce the same unactionable stall.
    """
    if (
        task.status in ("in_progress", "blocked")
        or task.status in REVIEWABLE_LOOP_TASK_STATUSES
        or task.status in WITH_REVIEWER_LOOP_TASK_STATUSES
    ):
        return True, None
    refusal = await dependency_gate.evaluate(session, task)
    return (not refusal.refuses), refusal


async def _loop_candidates(session: AsyncSession, loop: Loop) -> "list[Task]":
    """This loop's queue, in the order a firing considers it.

    One query, in one place, because there are now two walkers over it: `_first_startable_candidate`
    asks what *one named agent* may take, and `decide_firing` asks what *anyone* may take and who.
    Both must see the same rows in the same order or the board and the firing part company -- which
    is what `_loop_queue_order`'s own comment records happening the last time a derivation was
    duplicated here.

    The reviewable statuses are in the set as of `loop-becomes-a-flow` group 3. They are not
    claimable by status alone; whether any given one may be taken is answered per agent, further
    down.

    **The with-reviewer statuses joined them for finding F45, and not because a firing may claim
    one — it may not.** They are here so the walk can *see* them and record them as in-flight. A
    query that excluded them would leave `decide_firing` unable to distinguish a loop whose reviews
    are all running from a loop with nothing to do, and it would report the second: measured on the
    unfixed code, a queue holding one dispatched review returned `stalled` with the reason "no
    claimable task among 1 open (1 under_review)". That is finding F23 exactly, one band over.
    """
    return list(
        (
            await session.execute(
                select(Task)
                .where(
                    Task.loop_id == loop.id,
                    Task.status.in_(
                        CLAIMABLE_LOOP_TASK_STATUSES
                        + REVIEWABLE_LOOP_TASK_STATUSES
                        + WITH_REVIEWER_LOOP_TASK_STATUSES
                    ),
                )
                .order_by(*_loop_queue_order())
            )
        )
        .scalars()
        .all()
    )


async def _first_startable_candidate(
    session: AsyncSession, loop: Loop, *, agent: str
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

    **Takes the acting agent as of `loop-becomes-a-flow` group 3.** The candidate set widened to
    include the reviewable statuses, whose claimability has no answer without knowing who is
    asking, so this walk now filters each candidate through `task_is_claimable_by` before testing
    whether it is startable. A queue whose only finished task was finished by *this* agent
    therefore walks past it and reports nothing claimable, exactly as it did before the widening --
    which is what keeps a single-agent loop's behaviour unchanged by this group.
    """
    candidates = await _loop_candidates(session, loop)
    gated: "list[tuple[Task, dependency_gate.DependencyRefusal]]" = []
    for task in candidates:
        if not await task_is_claimable_by(session, task, agent):
            # Not gated -- gating is a statement about prerequisites, and this is a statement about
            # who is asking. Putting it in `gated` would make the stall reason say the queue was
            # waiting on an approval when it is waiting on a second agent.
            continue
        startable, refusal = await candidate_is_startable(session, task)
        if not startable:
            assert refusal is not None  # only the gated branch reports not-startable
            gated.append((task, refusal))
            continue
        return task, gated
    return None, gated


async def enter_selected_task(
    session: AsyncSession, task: Task, *, agent: str, is_review: bool
) -> None:
    """Move *task* into the status its selection implies, and record who holds it.

    **What dispatching a review does to a task, stated once.** Three callers: this module's
    `_do_fire_job` and `_stage_selection`, which stage a flow's own selection, and
    `agent_trigger.trigger_agent_directly`, which staffs a review the operator started by hand
    (finding F76). Public, and named without a leading underscore, because that third caller lives
    in another module: a review dispatched by hand used to provision the reviewer's checkout and
    staff nothing, so the reviewer could not move the task, and the repair was to give this
    statement a third caller rather than a second copy.

    The two halves are symmetric and only one of them existed until finding F45:

    * ordinary work enters at `pending -> assigned`, and a task already `assigned` or
      `in_progress` is being *resumed*, so its status is left alone (design D3);
    * a review enters at `completed -> under_review`, which is the same statement one band over --
      the task is no longer awaiting a handoff, somebody has it.

    **The review half is what closes F45.** Without it a dispatched review left the task in
    `completed`, which is precisely `REVIEWABLE_STATUSES`, so the ladder resolved the same reviewer
    for the same finished work on every subsequent tick. `stop_when_queue_empties` could not end it
    -- `completed` is not terminal -- so with no token budget the only bound was the operator
    noticing, and nothing on the board said anything was wrong.

    It also makes the reviewer's own instructions true. The turn context tells a reviewer to report
    through `revision_needed`, and `TRANSITIONS` does not offer that edge from `completed` --
    `completed` reaches only `under_review`. A reviewer that followed the instruction literally was
    refused, and one that found the work correct had no legal exit at all; measured across this
    Hub's history, no flow-dispatched reviewer had ever recorded a transition. Entering the review
    at `under_review` puts both `approved` and `revision_needed` one legal edge away.

    Extracted rather than written twice. Both `_do_fire_job` and `_stage_selection` stage a
    selection, ~330 lines apart, and each carried its own copy of the `pending -> assigned` move;
    adding the review half to one and not the other is exactly the drift this module's own
    `_loop_queue_order` comment warns about.
    """
    # The selection's agent, not the job's: from group 2 these differ whenever a flow staffs a task
    # with someone other than the job's own agent, and a task assigned to the job's agent while
    # another works it is the first place that divergence would become a lie the board repeats.
    #
    # **Written before the transition, not after** (finding F70). `_guard_reviewer_is_not_the_author`
    # refuses `-> under_review` while the task still names the agent that completed it, which is
    # exactly what `assignee` holds at this moment on a flow-staffed review. Assigning afterwards
    # left the guard reading the author and refusing the flow's own correct staffing. Both writes
    # are staged and the caller commits them together, so this is an ordering change within one
    # transaction and nothing observes the intermediate state.
    task.assignee = agent
    if is_review:
        if task.status in WITH_REVIEWER_LOOP_TASK_STATUSES:
            # Already with a reviewer. Reachable when a firing re-stages a selection whose entry
            # was queued but whose turn never started; moving again would be an illegal edge.
            #
            # Also how an F70-wedged row recovers: the walk below routes a task whose reviewer is
            # its own author back through the ladder, and it arrives here already in
            # `under_review`. The assignment above is the whole repair -- a real reviewer replaces
            # the author, and no edge is travelled.
            pass
        elif task.status in REVIEWABLE_LOOP_TASK_STATUSES:
            await apply_transition(session, task, "under_review", operator())
    elif task.status == "pending":
        await apply_transition(session, task, "assigned", operator())


async def _claim_loop_task(session: AsyncSession, loop: Loop, *, agent: str) -> "list[Task]":
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
    task, _gated = await _first_startable_candidate(session, loop, agent=agent)
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
    #: Whether this selection is a *review* of finished work rather than ordinary work on it
    #: (`loop-becomes-a-flow` design D9). Carried on the selection rather than re-derived from the
    #: task's status at the point of use, because by then the status may have moved and because the
    #: one consumer that matters -- `new_entry`'s `review_task_id` -- is three call layers away.
    is_review: bool = False


async def _stall_run_to_increment(
    session: AsyncSession, job_id: str, stall_reason: str, exclude_run_id: str
) -> "Optional[JobRun]":
    """The `JobRun` this stall should count against, or `None` to write a new row.

    **`loop-notices-and-reacts` design D6.** A loop ticking against a stalled queue writes one row
    per tick saying the same thing, and `JobRun` is what the last-ten-runs view and the "is this
    loop running" check both read -- so at a five-minute cadence a stall buries the firings that
    did work under twelve identical rows an hour and a healthy loop reads as dead.

    "The same stall" is deliberately narrow: the **most recent** run for this job is itself a stall
    record *and* its reason is unchanged. Narrow in both directions on purpose --

    * Most recent, so a stall that resumed and stalled again gets its own row rather than
      resurrecting a count from before the work happened.
    * Same reason, so a stall that changes shape stays visible instead of hiding inside a growing
      number. The reason names how many tasks are open and in which statuses, so it moves whenever
      the queue does.

    `exclude_run_id` is the run this firing has already constructed. Without it the newest row is
    always this firing's own and nothing ever matches.
    """
    from sqlalchemy import select

    latest = (
        (
            await session.execute(
                select(JobRun)
                .where(JobRun.job_id == job_id, JobRun.id != exclude_run_id)
                .order_by(JobRun.fired_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if latest is None:
        return None
    if latest.status != "skipped" or latest.error_summary != stall_reason:
        return None
    return latest


async def _discard_unused_run(session: AsyncSession, run: JobRun) -> None:
    """Drop a `JobRun` this firing built but must not persist (design D6).

    `session.add` has already been called by the time a firing knows it will not record a row.
    Which disposal applies depends on whether an intervening query autoflushed it -- `delete`
    refuses an object that was never flushed, and `expunge` alone would leave a flushed row in the
    database. Both are handled rather than assumed, because the autoflush depends on what else the
    firing happened to query first.
    """
    if run in session.new:
        session.expunge(run)
    else:
        await session.delete(run)


#: What a firing decided to do. The fourth is the flow's, and arrived with it (finding F23).
DECISION_CLAIM = "claim"
DECISION_STALLED = "stalled"
DECISION_PROCEED_EMPTY = "proceed_empty"
#: Every candidate is already being worked by an agent mid-turn. Distinct from `DECISION_STALLED`,
#: which means the queue is *waiting* on something, and from `DECISION_PROCEED_EMPTY`, which fires
#: an agent to fill a queue that has nothing in it. Here the queue is full and moving, and the right
#: thing for this firing to do is nothing at all -- see `FiringDecision._cannot_staff`.
DECISION_IN_FLIGHT = "in_flight"


@dataclass(frozen=True)
class ReviewerChoice:
    """The outcome of `resolve_reviewer` — one rung of design D4's ladder, and which one.

    Carries the rung rather than only the answer, because rung 1b and rung 3 are both "no agent"
    and mean opposite things to an operator. 1b is *a name was given and it is wrong*, which the
    operator fixes by correcting the document. 3 is *nobody was named and nobody is free*, which
    they fix by adding an agent or waiting. A single `Optional[str]` would collapse them, and the
    surfacing that D4 asks for would have nothing to say.
    """

    #: The agent to fire, or `None` when no rung produced one.
    agent: Optional[str] = None
    #: Which rung answered: "declared", "unresolved", "available", "deferred", or "unstaffed".
    #: "deferred" is not a rung of D4's ladder — it is design D6 interrupting one, and it is kept
    #: distinct from "unstaffed" because the two ask opposite things of the operator. Unstaffed
    #: needs them (add an agent, free one, fix a name); deferred needs nothing at all, since the
    #: agent is merely taken by this same firing and the next tick will find them again.
    rung: str = "unstaffed"
    #: Operator-facing explanation. Set on every rung that produced no agent.
    reason: Optional[str] = None


async def _agents_that_are_free(session: AsyncSession, project_id: str) -> "list[str]":
    """Design D4 rung 2's "free": **not running** *and* **holding no active task**, in queue-stable
    order.

    Both facts already existed and neither alone is enough. Not-running by itself was rejected in
    D4 because an agent can hold three assigned tasks and be idle between turns, which is the
    pile-up the operator named as the thing to avoid; holding-no-task by itself would pick an agent
    mid-turn and `schedule_agent` would refuse the second start.

    Reads the same running query `schedule_agent` and `_loop_agent_busy_reason` read, and the same
    `LIVE_STATUSES` the roster's own "active task" derivation reads, so a third opinion about
    whether an agent is busy cannot appear here.

    Archived agents are excluded for the reason `trigger_agent_directly` refuses one: nothing runs
    an archived agent. **Agents with no bound runner are excluded for the same reason and are the
    same kind of fact** (task 4.3): `trigger_agent_directly` refuses to spawn one, so selecting it
    would turn a staffing question into a launch failure one step later -- a firing that reports
    "could not staff this step" is telling the operator something they can act on, and a firing that
    dies trying to spawn a runnerless agent is not. Unavailable, never an error path.

    Ordered by name so a project with two free agents picks the same one twice. The proposal
    requires a firing to select "a task and an agent, both deterministically", and "whichever row
    the database returned first" is not that.
    """
    from .task_transitions import LIVE_STATUSES

    running = set(
        (
            await session.execute(
                select(Run.agent).where(Run.project_id == project_id, Run.status == "running")
            )
        )
        .scalars()
        .all()
    )
    holding = set(
        (
            await session.execute(
                select(Task.assignee).where(
                    Task.project_id == project_id,
                    Task.assignee.isnot(None),
                    Task.status.in_(tuple(sorted(LIVE_STATUSES))),
                )
            )
        )
        .scalars()
        .all()
    )
    roster = (
        (
            await session.execute(
                select(Agent.name)
                .where(
                    Agent.project_id == project_id,
                    Agent.lifecycle != "archived",
                    Agent.runner_id.isnot(None),
                )
                .order_by(Agent.name)
            )
        )
        .scalars()
        .all()
    )
    return [name for name in roster if name not in running and name not in holding]


async def resolve_reviewer(
    session: AsyncSession,
    task: Task,
    *,
    project_id: str,
    exclude: "set[str]",
    unavailable: "Optional[set[str]]" = None,
) -> ReviewerChoice:
    """Who should take *task*, walking design D4's ladder. `exclude` is who may not (the author).

    ```
       1.  the task's declared reviewer, if it resolves
       1b. a declaration that does NOT resolve  -> surface it; never substitute
       2.  no declaration: any agent not running and holding no active task
       3.  surface: "could not staff this step"
    ```

    **Rung 1b is the rung with an argument behind it.** Silence and a failed declaration are
    different facts. Nobody named a reviewer means the flow may choose freely, and rung 2 runs the
    whole thing with nothing configured -- which is the operator's objection to squad-before-work
    answered. Somebody named a reviewer and the name did not resolve means substituting would tell
    the operator something false about who checked the work, and they are the one who can fix the
    name. `review_turn.resolve_declared_reviewer` shipped taking exactly this position on
    2026-08-24, with the reasoning in its docstring; this **calls it** rather than resolving the
    declaration a second time.

    A declared reviewer that resolves to an excluded agent is rung 1b, not rung 2. The declaration
    named somebody who may not do it, which is a fact about the document rather than about
    availability, and quietly staffing somebody else is the substitution 1b exists to refuse.

    **A single-agent project reaches rung 3 by the general rule**, with no branch of its own: its
    only agent is the author, so it is excluded, rung 2's list comes back empty and rung 3
    surfaces. That was D4's own stated test of whether the ladder was right.

    **`unavailable` is separate from `exclude`, and the separation is the point** (added for group
    5, design D6). Both mean "not this agent", but for opposite reasons and to opposite effect.
    `exclude` is the author: a permanent fact about this task, and a declaration resolving into it
    is rung 1b — the document named somebody who may not do it, and the operator has to fix the
    name. `unavailable` is an agent this same firing has already selected for other work: a fact
    about *this tick* and nothing else. Collapsing the two would tell an operator their document
    named the author when it named a perfectly good reviewer who happened to be busy for ten
    minutes, which is a false statement about the work that outlives the tick that produced it.
    So a declaration resolving into `unavailable` is `rung="deferred"` instead, and rung 2 simply
    walks past those candidates.
    """
    from . import review_turn

    unavailable = unavailable or set()

    resolution = await review_turn.resolve_declared_reviewer(
        session, project_id=project_id, task=task
    )
    if resolution.declared:
        if resolution.agent and resolution.agent in unavailable and resolution.agent not in exclude:
            return ReviewerChoice(
                rung="deferred",
                reason=(
                    f"{resolution.agent} is this task's declared reviewer and is already taken by "
                    f"this firing. Nothing is wrong and nothing needs doing -- the next firing "
                    f"picks it up."
                ),
            )
        if resolution.agent and resolution.agent not in exclude:
            return ReviewerChoice(agent=resolution.agent, rung="declared")
        if resolution.agent:
            return ReviewerChoice(
                rung="unresolved",
                reason=(
                    f"this task names {resolution.declared!r} as its reviewer, and that agent is "
                    f"the one that completed the work. Naming a different reviewer, or reviewing "
                    f"it yourself, is the way forward -- the flow will not substitute somebody "
                    f"else for a named reviewer."
                ),
            )
        return ReviewerChoice(rung="unresolved", reason=resolution.unresolved)

    only_taken = False
    for candidate in await _agents_that_are_free(session, project_id):
        if candidate in exclude:
            continue
        if candidate in unavailable:
            # Eligible in every way that lasts, and merely spoken for by this same firing. Held so
            # rung 3 below can tell the difference.
            only_taken = True
            continue
        return ReviewerChoice(agent=candidate, rung="available")

    if only_taken:
        # **Not rung 3.** Rung 3 tells the operator to add an agent, free one, or fix a name --
        # remedies for a queue that cannot be staffed. A firing that simply used up the free agents
        # on earlier selections has none of those problems, and surfacing one would be a false
        # alarm on exactly the flows that are working hardest: the wider the firing, the more often
        # it would fire. The next tick finds these agents again.
        return ReviewerChoice(
            rung="deferred",
            reason=(
                "every agent that could review this is already taken by this firing. Nothing is "
                "wrong and nothing needs doing -- the next firing picks it up."
            ),
        )

    return ReviewerChoice(
        rung="unstaffed",
        reason=(
            "could not staff this step: no agent is free to take it. Every agent on the roster is "
            "either running a turn, already holding active work, or is the one that completed this "
            "task and so may not review it."
        ),
    )


@dataclass(frozen=True)
class FiringDecision:
    """The single answer to *what should this firing do* (`loop-notices-and-reacts` design D3).

    Before this, that answer was spread across `_do_fire_job` in a shape only it could read, and
    the board re-derived what it needed. Two derivations read by two callers is the drift the
    codebase has been bitten by three times -- and the board must be able to say *why* a loop is
    doing nothing from the same computation that decided it, rather than from a guess about it.

    **Room for a fourth answer is left deliberately** (D3). The flow adds *"fire a different agent
    for this task"*, and it needs no new `kind`: group 2 made the agent a property of each
    `LoopSelection`, so a reviewer is a selection whose agent differs from the job's. The fourth
    answer is therefore already expressible here, which is most of what
    `loop-becomes-a-flow` needs from this change.
    """

    kind: str
    #: What to run. Non-empty exactly when `kind` is `DECISION_CLAIM`.
    selections: "tuple[LoopSelection, ...]" = ()
    #: Why the firing is refused, naming what is being waited on. Set exactly when `kind` is
    #: `DECISION_STALLED`, and carried to the board so its label can say the same thing.
    stall_reason: Optional[str] = None
    #: `(task_id, reason)` for every reviewable candidate this firing could not staff (design D4
    #: rung 3). Independent of `kind`: a firing that goes on to claim other work still has to
    #: surface a review it could not staff, or the operator never learns that the queue has
    #: finished work nobody can take.
    unstaffed: "tuple[tuple[str, str], ...]" = ()
    #: `(task_id, agent)` for every candidate **this firing cannot staff anybody onto**, because
    #: that agent already holds it (finding F23). Not selectable by this firing -- `schedule_agent`
    #: would refuse a second turn for that agent -- and still the loop's current work, which is the
    #: distinction that made this a defect.
    #:
    #: `decide_firing` has two callers asking two different questions: the firing asks *"what can I
    #: start"* and the board asks *"what is this loop working on"*. Skipping a busy agent's task
    #: answers only the first, and answering only the first made a flow running three agents report
    #: `current_tasks: []` and `"loop queue is stalled"` -- measured live, on the first firing of a
    #: real flow. The busier the flow, the more certainly it reported as stalled.
    #:
    #: **Private, and named for what it means** (`one-answer-to-what-is-happening`, D9). It was
    #: `in_flight`, a public field on a frozen dataclass, and "in flight" reads as *"this is
    #: running"* -- which it is not. An `under_review` task with an assignee is appended here
    #: unconditionally and deliberately (F23, F45), so a verdict-less review stays visible; the
    #: board then rendered it as its reviewer being mid-turn, with no run anywhere in the database
    #: (F63). One word carrying two meanings, and any consumer could pick it up and read it as
    #: either. `task_attribution.staffing_from_decision` is now its only reader outside this
    #: module, and `test_task_attribution.py` scans the source to keep that true.
    _cannot_staff: "tuple[tuple[str, str], ...]" = ()
    #: `(task_id, reason)` for every candidate whose agent resolved but was **already selected by
    #: this same firing** (design D6). Recorded rather than dropped silently, which is the whole of
    #: what D6 asks for: without it the second selection would reach `schedule_agent`, be refused
    #: with *"agent is already running"*, and vanish with no record that the firing ever wanted it.
    #:
    #: **Deliberately not an event, and not a stall.** A flow with more ready work than agents
    #: defers on every tick forever by design, and emitting for that would bury `review_unstaffed`
    #: — the one that genuinely needs the operator — under the healthy case, which is precisely the
    #: burying `loop-notices-and-reacts` design D6 exists to stop. Nothing is wrong here and the
    #: next tick resolves it, so this is carried for tests and the log and no further.
    deferred: "tuple[tuple[str, str], ...]" = ()


async def decide_firing(session: AsyncSession, loop: Loop, *, default_agent: str) -> FiringDecision:
    """Decide what this firing does, in one walk of the queue.

    **Set-valued as of `loop-becomes-a-flow` group 5 (design D5).** The walk used to return on its
    first staffable candidate; it now runs to the end of the queue and accumulates, so a firing
    starts every task whose dependencies are met and for which an agent resolved. There is no cap
    and no setting — the bound is the graph the operator approved and the agents they have, which
    is D5's whole position: the operator starts parallelism at spec time, by decomposing into
    independent work, not by turning a dial afterwards.

    Two invariants the accumulation has to keep, and one it deliberately does not. It keeps
    `_loop_queue_order`'s ordering, so a rerun pairs the same tasks with the same agents; and it
    keeps design D6, one agent to one task per firing, in `taken`. It does **not** promise that a
    ready task is started — running out of free agents is the bound working, not a failure, and
    such a task is simply left untouched for the next tick.

    Replaces a real inefficiency as well as a structural one: `_do_fire_job` used to call
    `_first_startable_candidate` **twice** on a stalled queue -- once through `_claim_loop_task`
    to find nothing, then again inside `_loop_stall_reason` to find out why -- so the whole
    dependency-gate walk ran a second time to produce a sentence.

    **This is also the seam `loop-becomes-a-flow` group 4 extends.** Group 2 of that change put a
    short-lived `_select_for_firing` here to pair each claimed task with an agent; this function
    absorbed it rather than wrapping it, because "which tasks" and "who works them" are two halves
    of one decision and splitting them would leave the reviewer ladder deciding in a place the
    firing decision could not see. `default_agent` is design D2's default — the job's own agent,
    used when nothing says otherwise.

    The three answers are `agent-loops`' own three queue states, and the order matters. A queue
    that has never been filled and one that has drained both reach `DECISION_PROCEED_EMPTY`: the
    agent's job is to fill it, and whether a *drained* queue should stop firing at all is
    `_loop_stop_reason`'s question, asked earlier and separately.
    """
    from .task_transition_service import _agent_that_completed

    gated: "list[tuple[Task, dependency_gate.DependencyRefusal]]" = []
    unstaffed: "list[tuple[str, str]]" = []
    deferred: "list[tuple[str, str]]" = []
    in_flight: "list[tuple[str, str]]" = []
    selections: "list[LoopSelection]" = []
    # Design D6, and the only mutable state the walk carries. An agent selected twice in one firing
    # would be started twice concurrently; `schedule_agent` refuses the second and drops it without
    # a word, so the collision is decided here where it can be recorded instead.
    taken: "Set[str]" = set()

    # Both asked once, before the walk. `_agents_that_are_free` excludes agents that are running a
    # turn *or* holding active work, which is right for staffing something new and wrong for
    # resuming something already staffed: a task's own assignee is, by construction, holding active
    # work — itself. So resumption consults `running` directly (design D12 step 1) and only fresh
    # work draws from `free`.
    free = await _agents_that_are_free(session, loop.project_id)
    running = await _agents_running_a_turn(session, loop.project_id)
    # The per-task counterpart of `running`, for design D8's refusal. Asked once before the walk
    # for the same two reasons the line above is: a wide firing asks it about several candidates,
    # and asking it per candidate would make this a third place the question is asked.
    held = await tasks_held_by_a_running_turn(session, loop.project_id)
    default_taken = False

    for task in await _loop_candidates(session, loop):
        # Set by the `WITH_REVIEWER` branch only; declared here so the arms below can read it
        # unconditionally rather than each guarding on which branch ran.
        wedged_review = False
        startable, refusal = await candidate_is_startable(session, task)
        if not startable:
            assert refusal is not None  # only the gated branch reports not-startable
            gated.append((task, refusal))
            continue

        if task.status in WITH_REVIEWER_LOOP_TASK_STATUSES:
            # A reviewer already holds this (finding F45). Staffable by nobody: the reviewer
            # finishes it, or the operator resolves it from `under_review`'s three exits.
            #
            # **Tested before the ordinary/review split, not inside it, because it belongs to
            # neither.** `under_review` is absent from `REVIEWABLE_LOOP_TASK_STATUSES`, so without
            # this branch the walk would fall into the *ordinary work* arm below, find the
            # reviewer sitting in `assignee`, and re-staff the review as though it were
            # implementation -- firing the reviewer into its own worktree with no checkout of the
            # commit under review, which is finding F10 arriving by a new route.
            #
            # Recorded as in-flight rather than skipped, for finding F23's reason: a bare
            # `continue` removes the row from the board, and a flow whose reviews are all running
            # would read as having nothing to do. It is also what makes a review that ended
            # without a verdict *visible* -- the task stays here with its reviewer named, which is
            # a stall the operator can see and act on, where F45 was a spend loop they could not.
            #
            # **Unless the reviewer it names is the author** (finding F70). A task moved into
            # `under_review` without being reassigned satisfies every word above and none of its
            # meaning: nobody is reviewing it, the exits are offered to nobody, and
            # `_agents_that_are_free` counts the author busy on it forever -- costing the project a
            # reviewer for every *other* task too, silently. `_guard_reviewer_is_not_the_author`
            # now refuses the edge that creates this, so no new row can arrive here; rows already
            # wedged before that guard existed, or written straight into the status, still can.
            #
            # Recovered rather than merely reported, and through the ladder rather than by falling
            # through to the ordinary-work arm below -- that arm would find the author in
            # `assignee` and re-staff the review as implementation, which is F10 arriving by the
            # new route this branch's own comment warns about. `wedged_review` carries the decision
            # past that arm to the ladder, which excludes the author by construction.
            if task.assignee:
                wedged_author = await _agent_that_completed(session, task.id)
                if wedged_author is not None and wedged_author == task.assignee:
                    wedged_review = True
                else:
                    in_flight.append((task.id, task.assignee))
            if not wedged_review:
                continue

        if not wedged_review and task.status not in REVIEWABLE_LOOP_TASK_STATUSES:
            # Ordinary work, resolved per design D12.
            #
            # **Before anybody is resolved for it**, because a task another agent's turn already
            # holds cannot be staffed onto *anyone*: `trigger_agent_directly` refuses a second
            # writing turn on one task's checkout outright (design D8). Asked here rather than
            # below the resolution so the firing does not spend its default agent on a selection
            # it is about to drop -- `default_taken` is set by the branch below and would leave
            # the job's own agent idle for the rest of the walk.
            #
            # Two ways to arrive here, and the per-agent view sees neither: two flows racing on
            # one task, and a task left `in_progress` with its `assignee` cleared or never set,
            # where the `agent in running` branch below finds nobody to recognise as busy.
            #
            # **Recorded rather than skipped, for finding F23's reason** -- the same reason the
            # `agent in running` branch below records rather than skipping. A bare `continue` drops
            # the row from the walk, and the board reads this same walk to ask what the loop is
            # working on, so a flow whose work is being done reports itself stalled with
            # `current_tasks: []`. The pair is `(task, the agent that holds it)`: the turn actually
            # running, not the one this firing wanted to start.
            holder = held.get(task.id)
            if holder is not None:
                in_flight.append((task.id, holder))
                continue
            if task.assignee:
                # Already staffed; this firing is *resuming* it, not staffing it. Overwriting the
                # assignee with the job's default here is the defect group 5's spec review found:
                # under width it hands one agent's running task to another and briefs them for it.
                agent = task.assignee
                if agent in running:
                    # That agent's turn is still going, so this firing cannot start it -- the old
                    # whole-firing busy guard, scoped to the one selection it is actually about.
                    #
                    # **Recorded rather than skipped** (finding F23). A bare `continue` here removed
                    # the task from the walk entirely, so the board -- which reads this same
                    # function to ask what the loop is *working on* -- saw no current item and then
                    # reported a stall, for a flow whose agents were all mid-turn.
                    in_flight.append((task.id, agent))
                    continue
                if agent in taken:
                    deferred.append(
                        (
                            task.id,
                            f"{agent} already holds another selection in this firing and may take "
                            f"only one at a time",
                        )
                    )
                    continue
            elif not default_taken and default_agent not in running and default_agent not in taken:
                # D2's default, still first in line for the first unstaffed task.
                #
                # Tested against `running`, deliberately **not** against `free`. `free` is the
                # recruitment pool — it additionally demands a roster row with a bound runner and
                # no active work, which is right for an agent the flow is choosing and wrong for
                # the one the operator already chose when they created the job. Requiring it here
                # made a loop whose agent holds any active task, or whose project has no roster
                # rows at all, resolve nobody and read as stalled — caught by
                # `test_the_board_summary_agrees_with_the_firing_for_a_gated_queue`, since the
                # board derives its current item from this same walk.
                agent = default_agent
                default_taken = True
            else:
                candidate = next((name for name in free if name not in taken), None)
                if candidate is None:
                    # Width is bounded by available agents (design D5) and this is that bound
                    # being reached, not a fault. Nothing is recorded: the task keeps its status
                    # and its assignee, and the next firing considers it again.
                    continue
                agent = candidate
            selections.append(LoopSelection(task=task, agent=agent))
            taken.add(agent)
            continue

        # Finished work. **The ladder decides, always** — not "the job's agent if it happens to be
        # eligible". A declared reviewer that resolves outranks the job's own agent, or the
        # declaration would be advisory; and D4 is the one statement of who reviews.
        author = await _agent_that_completed(session, task.id)
        if author is None:
            # Unattributable, and therefore offered to nobody — see `task_is_claimable_by` for why
            # this is the safe direction. Not `unstaffed` either: nothing is waiting on staffing, the
            # task simply has no provenance, and the stall reason already counts it as open work.
            continue
        # **Can a review turn be provisioned for this at all?** Asked before a reviewer is
        # resolved, because a task with no commit to check out cannot be reviewed by anybody, and
        # `prepare_review_turn` is going to refuse it either way.
        #
        # Asked with the function the trigger itself uses, not a reimplementation of the rule, so
        # the gate and the refusal cannot come to different answers. Measured live: a loop claimed
        # a task, the agent completed it *without recording evidence*, and the next firing selected
        # it for review. `enter_selected_task` moved it `completed -> under_review` and named a
        # reviewer, and only then did the trigger refuse — leaving the task wedged with a reviewer
        # who never ran, and the firing recorded `failed`. Every firing after that repeated it.
        #
        # `unstaffed`, so the walk continues and the operator is told (D4's "surface the step, not
        # stop the flow", and F64's "say why, not merely that"). The remedy is the author's, and
        # the sentence has to name it: nothing here can conjure a commit.
        review_target = await requirement_evidence.commit_for_task_review(session, task.id)
        if not review_target.resolved:
            unstaffed.append(
                (
                    task.id,
                    f"{review_target.refusal or 'there is no commit to review'} Until the work "
                    f"that finished this task is recorded as evidence naming a commit, no "
                    f"reviewer can be given anything to look at.",
                )
            )
            continue

        choice = await resolve_reviewer(
            session, task, project_id=loop.project_id, exclude={author}, unavailable=taken
        )
        if choice.agent is not None:
            selections.append(LoopSelection(task=task, agent=choice.agent, is_review=True))
            taken.add(choice.agent)
            continue
        if choice.rung == "deferred":
            # D6 again, reached through the ladder rather than through resumption. Not `unstaffed`:
            # the declaration is fine and the operator has nothing to fix.
            deferred.append((task.id, choice.reason or "already taken by this firing"))
            continue
        # Rung 1b or rung 3. Surfaced, and the walk **continues**: D4 says surface the step, not
        # stop the flow, and a queue holding an unstaffable review behind ordinary work should do
        # the ordinary work rather than sit still. The operator learns about the review either way.
        unstaffed.append((task.id, choice.reason or "could not staff this step"))

    if selections:
        return FiringDecision(
            kind=DECISION_CLAIM,
            selections=tuple(selections),
            _cannot_staff=tuple(in_flight),
            unstaffed=tuple(unstaffed),
            deferred=tuple(deferred),
        )

    if in_flight:
        # **Checked before the stall, and that order is the fix** (finding F23). A queue whose work
        # is being done is not waiting on anything; asking `_stall_reason_from_walk` here would
        # count those very tasks as "open" and report the flow stalled at its busiest.
        return FiringDecision(
            kind=DECISION_IN_FLIGHT,
            _cannot_staff=tuple(in_flight),
            unstaffed=tuple(unstaffed),
            deferred=tuple(deferred),
        )

    stall_reason = await _stall_reason_from_walk(session, loop, gated)
    if stall_reason is None:
        return FiringDecision(
            kind=DECISION_PROCEED_EMPTY, unstaffed=tuple(unstaffed), deferred=tuple(deferred)
        )
    if unstaffed:
        # **Finding F64: say why, not merely that.** Reaching here means no selection and nothing
        # in flight, so nothing was claimable — and `_stall_reason_from_walk` describes that as a
        # property of the *queue* ("no claimable task among 2 open (2 completed)"). When `unstaffed`
        # is non-empty that attribution is wrong in the way that matters: the queue is holding work
        # which is ready this second, and what is missing is an agent permitted to take it. The two
        # remedies are opposite — add tasks, or add an agent — and the operator acts on whichever
        # the card names.
        #
        # The rung-3 sentence was already being computed on this very walk and emitted as a
        # `review_unstaffed` event; it simply never reached the surface an operator looks at. This
        # is not F23 returning: that fix put the `in_flight` branch *above* the stall check so a
        # busy flow stops calling itself stalled, and it works. This is the neighbouring case, a
        # flow that is neither busy nor short of work but short of eligible agents, which had no
        # branch of its own.
        #
        # The first reason, not a join of all of them: when a queue holds several unstaffable
        # reviews they are unstaffable for the same reason, and a card is a line rather than a
        # report. The event stream still carries one entry per task.
        stall_reason = unstaffed[0][1]
    return FiringDecision(
        kind=DECISION_STALLED,
        stall_reason=stall_reason,
        unstaffed=tuple(unstaffed),
        deferred=tuple(deferred),
    )


async def _loop_stall_reason(session: AsyncSession, loop: Loop, *, agent: str) -> Optional[str]:
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
    _, gated = await _first_startable_candidate(session, loop, agent=agent)
    return await _stall_reason_from_walk(session, loop, gated)


async def _stall_reason_from_walk(
    session: AsyncSession,
    loop: Loop,
    gated: "list[tuple[Task, dependency_gate.DependencyRefusal]]",
) -> Optional[str]:
    """`_loop_stall_reason`'s body, taking the walk's result instead of repeating it.

    Split out for `decide_firing`, which has already walked the queue to discover there was
    nothing to claim; asking `_first_startable_candidate` again purely to produce a sentence ran
    the entire dependency-gate walk a second time on exactly the firings that were doing no work.
    `_loop_stall_reason` is kept as the one-call form for callers that have not walked.
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


async def _emit_review_unstaffed(
    session: AsyncSession,
    job: AIJob,
    loop: Loop,
    task_id: str,
    reason: str,
) -> None:
    """Surface a review the ladder could not staff (`loop-becomes-a-flow` design D4 rung 3, and
    rung 1b).

    Follows the same persist-and-broadcast pattern the loop stop path uses, for the same reason: an
    operator watching the app should learn this without going to look for it, and the persisted row
    is what makes it survive a page they were not on.

    **It does not touch the job.** Not `enabled`, not the schedule, not `stop_reason`. This is the
    2026-08-20 skip-versus-stop reasoning applied to a third case: unstaffable is a condition the
    operator resolves — by adding an agent, freeing one, or fixing a name in a document — and every
    one of those is a change the *next* firing should pick up by itself. `remove_job` is not undone
    by any of them.

    Emitted whatever else the firing goes on to do, including when it claims other work. A review
    nobody can take is a fact about the queue rather than about this tick, and a firing that quietly
    did something else instead would leave the operator with a queue that never finishes and no
    indication why.
    """
    payload = {
        "job_id": job.id,
        "job_name": job.name,
        "loop_id": loop.id,
        "task_id": task_id,
        "reason": reason,
    }
    await persist_event(
        session,
        job.project_id,
        "review_unstaffed",
        payload,
        agent=job.agent,
        loop_id=loop.id,
    )
    await sse_manager.broadcast(job.project_id, "review_unstaffed", payload)


async def _briefing_checkpoint(
    session: AsyncSession, loop: Loop, task: Optional[Task], *, is_review: bool
) -> Optional[Checkpoint]:
    """The checkpoint a turn is briefed from.

    Two questions, not one (finding F44). An ordinary continuation turn asks "what did this loop
    last do", and `latest_checkpoint_for_loop` answers it -- that is what its docstring reasons
    about, and it stays correct here.

    A **review** turn asks something else: "what did the author of *this task* leave me". Those
    were the same row only while a loop ran one agent at a time, where the newest checkpoint is by
    construction the previous firing's. A flow running three agents concurrently breaks the
    identity, and the reviewer of task X would be briefed with whoever finished last -- measured on
    the live database as two firings in three carrying the wrong author's work.

    Falls back to the loop's latest when the author left no checkpoint, rather than briefing with
    nothing: an agent that recorded no notes generates no handover checkpoint by design (F43's
    gate), and the loop's own account of itself is still better context than an empty section. The
    fallback is what makes this no worse than the previous behaviour in the case it cannot improve.
    """
    if is_review and task is not None:
        by_author = await checkpoint_by_task_author(session, task.id, loop_id=loop.id)
        if by_author is not None:
            return by_author
    return await latest_checkpoint_for_loop(session, loop.id)


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

    **The tier statement leads, as of `loop-becomes-a-flow` group 8 (design D8).** An agent inside a
    flow did not choose to be there and has no reason to ask, so it is told here — the one place it
    reliably reads. D8 rejected a tool to ask with the reason that "an agent that does not know to
    ask never asks", which is how the self-messaging capability stayed invisible for a month.

    It sits *above* the checkpoint deliberately. §257's fixed bound applies to prior checkpoint
    content, and an oversized checkpoint is truncated in place; a statement placed after it would
    survive or not depending on how much the previous agent wrote, which is the one thing an
    instruction about stopping must not depend on.

    **What separates the two wordings is what is true, not which tool created the loop.** Nothing in
    `decide_firing` or `resolve_reviewer` consults `spec_document_id` — width and review by a
    non-author apply to every loop, and rung 2 of the ladder is written to work with nothing
    configured. So "finish and stop" is stated for *all* of them, because it is true of all of them,
    and only a flow is told its work comes from a document and will be reviewed by somebody else.
    Telling a single-agent loop that somebody will review its work is the false claim task 8.2
    exists to prevent, and it is false for a document-less loop that happens to be alone in its
    project. See `design.md`'s open question on whether the tier should gate behaviour at all.
    """
    lines: list[str] = ["# Loop briefing", ""]

    if loop.spec_document_id:
        lines.append(
            "This is a **flow**: the queue below was decomposed from a specification document, "
            "and its tasks are worked by whichever agents are free. Finished work is claimed for "
            "review by an agent other than the one that did it."
        )
        lines.append("")
        lines.append(
            "**Finish the task below and stop.** Do not pick up the next item and do not hand "
            "the work to anyone — routing is the flow's job, and the next firing decides who does "
            "what. Record what a reviewer will need (see `submit_checkpoint_notes`); somebody "
            "else reads it."
        )
        lines.append("")
    else:
        lines.append(
            "**Finish the task below and stop.** Do not pick up the next item — the next firing "
            "claims it."
        )
        lines.append("")

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
                # `_loop_flow_busy_reason`, not `_loop_agent_busy_reason`: refusing the whole
                # firing because *the job's* agent is mid-turn is right for a loop and wrong for a
                # flow, where another agent may be free for independent work (design D12). The
                # narrower question — busy *and* nobody else free — is identical for every
                # single-agent loop, so this branch behaves exactly as it did for all of them.
                busy_reason = await _loop_flow_busy_reason(session, job.project_id, job.agent)
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
                # D17/B2.5. One statement of what ending means, shared with the operator's own
                # stop in `api/v1/jobs.py` — which used to keep a partial copy of this and left
                # out the two halves that matter most, `stopped_at` and disabling the job.
                end_loop(job, loop, reason=loop_stop_reason, when=fired_at)
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
                if loop is not None and loop_stop_reason == QUEUE_DRAINED_REASON:
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
            # Bound before the branch because the queue entry below reads it, and that line is
            # outside it: a plain scheduled job has no loop, makes no selection, and must reach
            # `new_entry` with `review_task_id=None` rather than a `NameError`.
            selection: Optional[LoopSelection] = None
            extra_selections: "list[LoopSelection]" = []
            if loop is not None:
                # Set-valued as of `loop-becomes-a-flow` group 1, and carrying its own agent as
                # of group 2 (design D2). Still at most one member until group 5 widens it, so the
                # firing keeps its single-selection shape and unwraps at this boundary.
                # One decision, one walk (design D3). This used to claim, find nothing, and then
                # walk the whole dependency gate a *second* time inside `_loop_stall_reason` just
                # to produce the sentence explaining why — on exactly the firings doing no work.
                decision = await decide_firing(session, loop, default_agent=job.agent)
                # Design D4 rung 3, and rung 1b. Emitted before anything else this firing does,
                # including before a refusal returns below: a review nobody can take is a fact
                # about the queue that outlives this tick, and the operator is the only one who
                # can resolve it. Never disables the job -- same reasoning that chose *skip* over
                # *stop* on 2026-08-20, since `remove_job` is not undone by resolving anything.
                for unstaffed_task_id, unstaffed_reason in decision.unstaffed:
                    await _emit_review_unstaffed(
                        session, job, loop, unstaffed_task_id, unstaffed_reason
                    )
                for deferred_task_id, deferred_reason in decision.deferred:
                    # Design D6. Logged, never surfaced -- a flow with more ready work than agents
                    # defers on every tick by design, and an event for that would bury
                    # `review_unstaffed` under the healthy case. See `FiringDecision.deferred`.
                    logger.debug(f"Job {job.id} deferred {deferred_task_id}: {deferred_reason}")
                # The firing's own selection is the first; `extra_selections` are staged after this
                # one is fully away, each with its own `JobRun` and conversation (design D13). The
                # split keeps every path below -- stall, skip, resume, briefing -- exactly the shape
                # it had when at most one selection existed.
                if decision.kind == DECISION_IN_FLIGHT:
                    # Finding F23. Every candidate is being worked right now, so there is nothing
                    # for this firing to start and nothing wrong to report. **Records nothing** --
                    # the same reasoning `_loop_flow_busy_reason` gives for the whole-firing case:
                    # the agents' own running rows already carry the fact that they are working, and
                    # a row here would duplicate it and evict real history through
                    # `_prune_job_history`'s window at a five-minute cadence.
                    await _discard_unused_run(session, run)
                    await session.commit()
                    if pending_edit_payload is not None:
                        await _emit_loop_edit_applied(session, pending_edit_payload)
                    logger.debug(
                        f"Job {job.id} firing skipped: "
                        f"{len(decision._cannot_staff)} task(s) already in flight"
                    )
                    return False
                selection = decision.selections[0] if decision.selections else None
                extra_selections = list(decision.selections[1:])
                claimed_task = selection.task if selection is not None else None
                if claimed_task is None:
                    stall_reason = decision.stall_reason
                    if stall_reason:
                        # Skipped, not stopped: the job stays enabled and stays in the live
                        # scheduler, so the next tick picks the queue up the moment something
                        # becomes claimable again. See `_loop_stall_reason` for why this is not
                        # the `_loop_stop_reason` branch above.
                        #
                        # Design D6: a *continuing* stall counts in place rather than appending.
                        # The row this firing built is discarded in that case, so twenty refusals
                        # leave one row reading 20 instead of twenty rows reading the same thing.
                        counted = await _stall_run_to_increment(
                            session, job.id, stall_reason, exclude_run_id=run_id
                        )
                        if counted is not None:
                            counted.tick_count += 1
                            # `fired_at` is deliberately not moved. Kept at the first refusal, the
                            # row reads "this stall began then and has been re-checked N times",
                            # and genuine firings that happen later sort above it in a history view
                            # ordered by `fired_at`. Moving it would send a stalled loop's row back
                            # to the top of that list every five minutes — the same burying this
                            # decision exists to stop, by another route.
                            await _discard_unused_run(session, run)
                            await session.commit()
                            if pending_edit_payload is not None:
                                await _emit_loop_edit_applied(session, pending_edit_payload)
                            logger.debug(
                                f"Job {job.id} stall continues "
                                f"({counted.tick_count}): {stall_reason}"
                            )
                            return False
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
                    # Entering the task is `enter_selected_task`'s single statement, shared with
                    # `_stage_selection` (finding F45): `pending -> assigned` for ordinary work,
                    # `completed -> under_review` for a review, and the assignee either way.
                    #
                    # From group 5 the assignee write is a no-op for a resumption rather than an
                    # overwrite: `decide_firing` resolves an already-assigned task to its own
                    # assignee (design D12 step 1), so the value written back is the one already
                    # there. It used to be `default_agent` unconditionally, which under width
                    # silently reassigned another agent's running task to the job's own.
                    await enter_selected_task(
                        session,
                        claimed_task,
                        agent=selection.agent,
                        is_review=selection.is_review,
                    )
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
                prior_checkpoint = await _briefing_checkpoint(
                    session,
                    loop,
                    claimed_task,
                    # `selection` is None on the "never filled" queue, where there is no task and
                    # so nothing to be reviewing.
                    is_review=bool(selection is not None and selection.is_review),
                )
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
                # Design D9, and the whole of task 4b. Without this the reviewer is fired into its
                # own working checkout, where the author's unmerged work does not exist -- finding
                # F10 reproduced by the flow that was meant to make review routine. Set only for a
                # selection the ladder made *as a review*, so ordinary work acquires no checkout.
                review_task_id=(
                    selection.task.id if (selection is not None and selection.is_review) else None
                ),
                # `every-run-knows-its-task` D1/D2: the other half of the same selection, set only
                # where the ladder made this an ordinary claim. Never both on one entry — a firing
                # is either reviewing or working, and the field that isn't its kind stays `None`
                # (design D3 depends on this: it is what lets the scheduler tell the two apart).
                task_id=(
                    selection.task.id
                    if (selection is not None and not selection.is_review)
                    else None
                ),
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

            # Phase 1 of design D5's width: every extra selection's rows are written **before any
            # turn starts**, including this firing's own. `loop` is not None whenever the list is
            # non-empty — only `decide_firing` produces selections and only a loop reaches it.
            staged_extras: "list[tuple[str, str]]" = []
            if extra_selections:
                assert loop is not None
                staged_extras = await self._stage_additional_selections(
                    job, loop, extra_selections, trigger, fired_at
                )

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

            # Phase 2 of design D5's width: every extra selection's rows exist by now, so this
            # only starts their turns. See `_stage_additional_selections` for why the two are
            # separated.
            await self._start_additional_turns(job.project_id, staged_extras)

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

    async def _stage_additional_selections(
        self,
        job: AIJob,
        loop: Loop,
        selections: "list[LoopSelection]",
        trigger: str,
        fired_at: datetime,
    ) -> "list[tuple[str, str]]":
        """Write every extra selection's rows, and start none of their turns. Returns
        `(agent, run_id)` for each one that staged.

        **The split between staging and starting is a correctness requirement, found by task 10.6
        on 2026-08-24.** The first version staged each extra selection *and* started its turn, in a
        loop that ran after the primary selection's turn was already away. A turn that ends calls
        `finalize_job_run_for_conversation`, which writes `job_runs` — so with a fast turn (a test's
        fake pty, or any quick real one) the primary's completion interleaved with the staging of
        the third selection and produced
        `StaleDataError: UPDATE statement on table 'job_runs' expected to update 1 row(s); 0 were
        matched`. The third selection was then dropped, silently, and the firing did less than it
        had decided to.

        Every row this firing writes is therefore written before any turn is started, and the only
        thing left to interleave with a completing turn is `schedule_agent`, which takes the
        per-agent lock and is built for exactly that.

        A selection that fails to stage is logged and skipped; the others still go. Each stands or
        falls alone, which is the same independence design D13 gives them a `JobRun` each for.
        """
        staged: "list[tuple[str, str]]" = []
        for selection in selections:
            try:
                run_id = await self._fire_additional_selection(
                    job_id=job.id,
                    loop_id=loop.id,
                    task_id=selection.task.id,
                    agent=selection.agent,
                    is_review=selection.is_review,
                    trigger=trigger,
                    fired_at=fired_at,
                )
            except Exception as error:
                # Contained rather than raised: the outer handler marks *the firing's own* run as
                # failed, and by this point that run is queued and about to start, so letting this
                # escape would record a lie about the one selection that succeeded.
                logger.error(
                    f"Job {job.id} could not stage {selection.agent} for {selection.task.id}: "
                    f"{_safe_error_summary(error)}"
                )
                continue
            if run_id is not None:
                staged.append((selection.agent, run_id))
        return staged

    async def _start_additional_turns(
        self, project_id: str, staged: "list[tuple[str, str]]"
    ) -> None:
        """Start the turns for selections `_stage_additional_selections` already wrote rows for.

        A terminal refusal is recorded against that selection's own `JobRun`, in its own session —
        the same outcome the primary path records for itself, and the reason design D13 gives each
        selection a row: one agent's launch failing says nothing about the others.
        """
        from .turn_scheduler import schedule_agent

        for agent, run_id in staged:
            try:
                result = await schedule_agent(project_id, agent)
            except Exception as error:
                logger.error(
                    f"Could not start {agent} for run {run_id}: {_safe_error_summary(error)}"
                )
                continue
            if result.waiting_reason and result.terminal_failure:
                async with async_session_factory() as session:
                    run = await session.get(JobRun, run_id)
                    if run is not None:
                        run.status = "failed"
                        run.error_summary = result.waiting_reason
                        await session.commit()

    async def _fire_additional_selection(
        self,
        *,
        job_id: str,
        loop_id: str,
        task_id: str,
        agent: str,
        is_review: bool,
        trigger: str,
        fired_at: datetime,
    ) -> "Optional[str]":
        """Stage one more of a wide firing's selections: its own `JobRun`, conversation and queue
        entry, then start its turn (`loop-becomes-a-flow` group 5).

        **Opens its own session, and takes ids rather than ORM objects, and that is a correctness
        requirement rather than a style choice** (found by task 10.6, 2026-08-24). By the time this
        runs, `schedule_agent` has already started the *primary* selection's turn in the background,
        and that turn writes to the same rows through a session of its own — including the primary
        `Conversation` the caller's session still holds. Committing here through the caller's
        session flushed those stale objects and raised
        `StaleDataError: UPDATE statement on table 'conversations' expected to update 1 row(s); 0
        were matched`, which then poisoned the whole firing with a `PendingRollbackError`. A
        separate session touches only the rows this selection creates, which is also what makes the
        containment in the caller true rather than aspirational.

        **Design D13 is why this creates a `JobRun` rather than sharing the firing's.**
        `finalize_job_run_for_conversation` correlates a run back to the `Run` it started **only**
        through `conversation_id` — there is no foreign key, as `models.py` records — and each
        selection gets its own conversation. One row spanning several would have nothing left to
        correlate with, and would need a new rule for when a row covering three agents stops being
        "in progress". One row each keeps the finalize path untouched and each agent's outcome
        separately visible.

        **Never resumes a provider session**, and `session_id` is `None` on both the run and the
        entry. An extra selection is by construction an agent other than the primary one, so
        `job.last_session_id` belongs to somebody else; resuming one agent's session as another is
        not a thing this product does, and the primary path already refuses it for the same reason
        where its own agent diverges.

        Failure is per selection and not fatal to the firing: `run.status` becomes `failed` with the
        scheduler's own reason, exactly as the primary path records a terminal `schedule_agent`
        refusal, and the remaining selections still go.
        """
        async with async_session_factory() as session:
            job = await session.get(AIJob, job_id)
            loop = await session.get(Loop, loop_id)
            task = await session.get(Task, task_id)
            if job is None or loop is None or task is None:
                # Nothing to stage against. Cannot happen from a firing that just read all three,
                # so this is a guard rather than a case — but it *says so*: an earlier version
                # returned silently and turned a staging failure into a firing that quietly did
                # less than it decided to, which is the one outcome a wide firing must never have.
                logger.error(
                    f"Job {job_id} could not stage {agent} for {task_id}: "
                    f"job={job is not None} loop={loop is not None} task={task is not None}"
                )
                return None
            return await self._stage_selection(
                session,
                job=job,
                loop=loop,
                task=task,
                agent=agent,
                is_review=is_review,
                trigger=trigger,
                fired_at=fired_at,
            )

    async def _stage_selection(
        self,
        session: AsyncSession,
        *,
        job: AIJob,
        loop: Loop,
        task: Task,
        agent: str,
        is_review: bool,
        trigger: str,
        fired_at: datetime,
    ) -> str:
        """The body of `_fire_additional_selection`, given rows already loaded in its own session.

        Writes rows only. The turn is started later, by `_start_additional_turns`, once every
        selection's rows exist — see `_stage_additional_selections` for why that ordering matters.
        Returns the `JobRun` id so the starter can record a refusal against it.
        """
        from .inbound_queue import new_entry

        # Shared with `_do_fire_job`'s primary path — see `enter_selected_task` for why the review
        # half cannot live in only one of the two (finding F45).
        await enter_selected_task(session, task, agent=agent, is_review=is_review)

        conversation = new_conversation(project_id=job.project_id, agent=agent, origin="job")
        session.add(conversation)
        await inherit_runtime_overrides(session, conversation)
        name_conversation(conversation, job.name)

        run_id = f"run-{short_id()}"
        run = JobRun(
            id=run_id,
            job_id=job.id,
            project_id=job.project_id,
            fired_at=fired_at,
            # Straight to `in_progress`: unlike the primary row this one is created only once the
            # firing is known to proceed, so it never passes through the `"fired"` state the skip
            # branches above exist to overwrite.
            status="in_progress",
            trigger=trigger,
            session_id=None,
            conversation_id=conversation.id,
        )
        session.add(run)

        prior_checkpoint = await _briefing_checkpoint(session, loop, task, is_review=is_review)
        briefing = await _compose_loop_briefing(session, loop, task, prior_checkpoint)
        entry = new_entry(
            project_id=job.project_id,
            agent=agent,
            origin_type="job",
            content=f"{briefing}\n{job.message}",
            hop_depth=0,
            session_mode=job.session_mode,
            session_id=None,
            conversation_id=conversation.id,
            # Design D9, same as the primary path: only a selection the ladder made *as a review*
            # gets a checkout of the author's work.
            review_task_id=task.id if is_review else None,
            # `every-run-knows-its-task` D1/D2, same as the primary path: the other half of the
            # same selection, and never both on one entry.
            task_id=task.id if not is_review else None,
        )
        session.add(entry)
        # One per row, so `run_count` keeps counting `JobRun`s (finding F11 stamps the primary's at
        # the same boundary). `job.last_run` is not touched: the firing has one time, already
        # stamped, and moving it per selection would make it mean "the last agent started".
        job.run_count += 1
        await session.commit()

        queue_payload = {
            "entry_id": entry.id,
            "agent": agent,
            "origin_type": "job",
            "hop_depth": 0,
            "job_id": job.id,
            "conversation_id": conversation.id,
        }
        await persist_event(
            session, job.project_id, "queue_entry_queued", queue_payload, agent=agent
        )
        await sse_manager.broadcast(job.project_id, "queue_entry_queued", queue_payload)

        fired_payload = {
            "job_id": job.id,
            "job_name": job.name,
            "agent": agent,
            "trigger": trigger,
            "run_id": run_id,
        }
        await sse_manager.broadcast(
            job.project_id,
            "job_fired",
            {
                "id": job.id,
                "name": job.name,
                "agent": agent,
                "trigger": trigger,
                "run_id": run_id,
            },
        )
        await persist_event(session, job.project_id, "job_fired", fired_payload, agent=agent)
        return run_id


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
