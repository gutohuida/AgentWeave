"""The task lifecycle as a declared machine, rather than as whatever the last writer said.

Before this module, `update_task_for_actor` applied `task.status = body.status` with no notion of
adjacency and no notion of who was asking, and `update_task` in the MCP surface handed that to every
bound agent — so a run could move its own work from `in_progress` straight to `approved` in one
call. See `openspec/changes/2026-08-10-task-transition-machine/`.

Two ideas carry the design:

**An edge names who may take it.** The operator's extra authority — rejecting work before review,
reopening something already decided — is expressed as *additional edges*, not as an exemption from
the map (design D9). So the operator is still bound by the machine, and every recorded history
therefore describes a legal sequence. That is what makes the history worth reading, and it is why no
forced-move override exists.

**A lifecycle that can be entered anywhere is not a lifecycle.** `ENTRY_STATUSES` exists because
governing transitions alone left the machine walkable around: a caller could create a task already
`approved` and never transition at all (design D10).

This module is deliberately inert — it declares and answers questions. It performs no I/O, holds no
session, and knows nothing about author/reviewer separation, which needs the transition history and
so lives in the service built on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Mapping, Optional, Tuple

# --------------------------------------------------------------------------------------
# Actors
# --------------------------------------------------------------------------------------

ACTOR_RUN = "run"
ACTOR_OPERATOR = "operator"
ACTOR_KINDS: Tuple[str, ...] = (ACTOR_RUN, ACTOR_OPERATOR)


@dataclass(frozen=True)
class Actor:
    """Who is asking for a transition.

    Explicit rather than inferred from a null run id (design D2). The two call sites happen to
    coincide today — the operator route passes no run, the agent route always has one — but "no run
    id" and "the operator" are different propositions, and a future path that merely *lost* a run id
    would otherwise acquire operator privileges, including exemption from self-approval.
    """

    kind: str
    run_id: Optional[str] = None
    #: Which agent the run belongs to. Author/reviewer separation compares *this*, not `run_id`:
    #: every turn an agent takes is a new run, so a run-based check is satisfied automatically by
    #: an agent simply continuing its own work. Found in first live use, 2026-08-10 — an agent
    #: completed on one run and approved on the next, and the rule as originally written passed it.
    agent: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in ACTOR_KINDS:
            raise ValueError(f"actor kind must be one of {list(ACTOR_KINDS)}, got {self.kind!r}")
        if self.kind == ACTOR_RUN and not self.run_id:
            raise ValueError("an actor of kind 'run' must carry a run_id")
        if self.kind == ACTOR_RUN and not self.agent:
            raise ValueError("an actor of kind 'run' must carry the agent it belongs to")
        if self.kind == ACTOR_OPERATOR and self.run_id:
            raise ValueError("an actor of kind 'operator' must not carry a run_id")
        if self.kind == ACTOR_OPERATOR and self.agent:
            raise ValueError("an actor of kind 'operator' must not carry an agent")

    @property
    def is_operator(self) -> bool:
        return self.kind == ACTOR_OPERATOR


def operator() -> Actor:
    """The operator, acting directly."""
    return Actor(kind=ACTOR_OPERATOR)


def run_actor(run_id: str, agent: str) -> Actor:
    """An authenticated agent run, and the agent it belongs to."""
    return Actor(kind=ACTOR_RUN, run_id=run_id, agent=agent)


# --------------------------------------------------------------------------------------
# The map
# --------------------------------------------------------------------------------------

_BOTH: FrozenSet[str] = frozenset(ACTOR_KINDS)
_OPERATOR_ONLY: FrozenSet[str] = frozenset({ACTOR_OPERATOR})

#: Statuses a task may be *created* in. Everything else must be reached by transitioning.
#: `assigned` is included because creating a task already directed at an agent is ordinary, and
#: forcing `pending` plus an immediate move would record a transition that says nothing (D10).
ENTRY_STATUSES: FrozenSet[str] = frozenset({"pending", "assigned"})

#: from_status -> to_status -> the actor kinds permitted to take that edge.
#:
#: `under_review` is the only place an agent may reject: there, rejection is a review outcome. From
#: anywhere else it is a decision to abandon work, which is the operator's (D9). `approved` and
#: `rejected` are not terminal, but their only exits belong to the operator.
TRANSITIONS: Mapping[str, Mapping[str, FrozenSet[str]]] = {
    "pending": {
        "assigned": _BOTH,
        "in_progress": _BOTH,
        "rejected": _OPERATOR_ONLY,
    },
    "assigned": {
        "in_progress": _BOTH,
        "pending": _BOTH,
        "rejected": _OPERATOR_ONLY,
    },
    "in_progress": {
        "completed": _BOTH,
        "assigned": _BOTH,
        "blocked": _BOTH,
        "rejected": _OPERATOR_ONLY,
    },
    # Work that started and then hit something only a person can supply.
    #
    # Reachable only from `in_progress`: a task nobody has started is not blocked, it is pending.
    #
    # `blocked -> completed` is deliberately absent. Work that was waiting and is now done passes
    # back through `in_progress`, so the history says the block ended before the work did. The
    # shortcut would let a task be recorded as completed while still waiting on a person who never
    # answered — the exact class of untrue record the transition machine exists to prevent.
    #
    # Reassignment and rejection stay open to the operator: "this agent is stuck, give it to someone
    # else" and "this is not worth unblocking" are both real.
    "blocked": {
        "in_progress": _BOTH,
        "assigned": _OPERATOR_ONLY,
        "rejected": _OPERATOR_ONLY,
    },
    "completed": {
        "under_review": _BOTH,
        "rejected": _OPERATOR_ONLY,
    },
    "under_review": {
        "approved": _BOTH,
        "revision_needed": _BOTH,
        "rejected": _BOTH,
    },
    "revision_needed": {
        "in_progress": _BOTH,
        "rejected": _OPERATOR_ONLY,
    },
    "approved": {
        "revision_needed": _OPERATOR_ONLY,
    },
    "rejected": {
        "pending": _OPERATOR_ONLY,
    },
}

#: Named because several modules must ask "is this task waiting on a person?" and a bare string
#: literal spread across the divergence check, the binding path and the questions route is how one
#: of them ends up spelled differently and silently never matching.
STATUS_BLOCKED = "blocked"

#: Every status the machine knows. Pinned to the two independent declarations in
#: `src/agentweave/constants.py` and `hub/hub/schemas/tasks.py` by
#: `hub/tests/test_task_transitions.py`, so a ninth status cannot be added anywhere without
#: declaring its edges here.
STATUSES: FrozenSet[str] = frozenset(TRANSITIONS)


# --------------------------------------------------------------------------------------
# Lifecycle bands
# --------------------------------------------------------------------------------------

#: Every status, classified once, into exactly one band (`loop-notices-and-reacts` design D9).
#:
#: **Why this exists.** Five constants around the codebase answered questions of the form "is this
#: task live?" and none knew the others existed. Both stall bugs fixed on 2026-08-20 lived in the
#: gaps between them -- the spin, because `completed` was in neither the claim nor the terminal
#: set; `revision_needed`, because it was in neither while two *other* sets already called it live
#: work. A third landed on 2026-08-24: the board was answering "what is this loop working on" with
#: the *claimable* set, so when `blocked` left the claim the board silently stopped showing blocked
#: tasks, and a loop parked on an unanswered question read as idle.
#:
#: **The trap this must not fall into.** Those five constants do not all answer one question, and a
#: classification that assumes they do will re-merge them. `blocked` is *no* to "may a firing claim
#: this?" and *yes* to "is this the loop's current work?". So the bands below are deliberately
#: finer than any single set, and each set is defined as the union of bands **for its own
#: question** -- never as one "live" band that everything reads.
#:
#: A status added to `TRANSITIONS` and not classified here fails at import, not at 3am in a loop
#: that fires forever.

#: Firing an agent makes progress possible. That is the whole test, and it is the one that decided
#: `revision_needed` belongs here (2026-08-20) while `blocked` does not (2026-08-21).
BAND_AGENT_ACTIONABLE = "agent_actionable"

#: Waiting on a person. Progress needs an answer no agent can supply, so firing one against it
#: spawns a turn that cannot move the work -- the 2026-08-20 spin, exactly. Still the loop's
#: current work, and the operator is the one who needs to see it.
#: (`openspec/explorations/2026-08-21-which-band-blocked-belongs-to.md`.)
BAND_AWAITING_PERSON = "awaiting_person"

#: Finished by its author and waiting for somebody else to take it up. Not yet anyone's active task.
#:
#: **Claimability here depends on who is asking** (`loop-becomes-a-flow` design D3), which is what
#: makes this band different in kind from the other four: every other band answers "may a firing
#: claim this?" with a yes or a no, and this one answers "not by the agent that finished it". An
#: agent may not approve its own work, so the author cannot take it back -- but anybody else can,
#: and that is the entire review mechanism. `REVIEWABLE_STATUSES` is the set; `scheduler`'s
#: `task_is_claimable_by` is the question, and it asks `agent_that_completed` rather than a second
#: implementation of the same determination, so a task the Hub offers an agent is never one that
#: agent would then be refused for approving.
BAND_AWAITING_HANDOFF = "awaiting_handoff"

#: Somebody else has it. Not claimable, but live work: it is in flight, just not here.
BAND_WITH_REVIEWER = "with_reviewer"

#: Done, one way or the other. The only exits belong to the operator.
BAND_TERMINAL = "terminal"

STATUS_BANDS: Mapping[str, str] = {
    "pending": BAND_AGENT_ACTIONABLE,
    "assigned": BAND_AGENT_ACTIONABLE,
    "in_progress": BAND_AGENT_ACTIONABLE,
    "revision_needed": BAND_AGENT_ACTIONABLE,
    "blocked": BAND_AWAITING_PERSON,
    "completed": BAND_AWAITING_HANDOFF,
    "under_review": BAND_WITH_REVIEWER,
    "approved": BAND_TERMINAL,
    "rejected": BAND_TERMINAL,
}


def _statuses_in(*bands: str) -> FrozenSet[str]:
    """The statuses belonging to any of *bands*.

    Sets are built from this rather than listed, so adding a status to `STATUS_BANDS` reaches
    every set that includes its band with no further edits.
    """
    wanted = frozenset(bands)
    return frozenset(status for status, band in STATUS_BANDS.items() if band in wanted)


def _check_bands() -> None:
    """Refuse to import with a status classified into none of the bands, or into a band that is
    not one of them.

    Checked against `TRANSITIONS` rather than a hand-maintained list, so the failure arrives the
    moment a status is added to the machine without a band -- which is the whole point. Raised at
    import so it cannot be discovered by a loop firing forever at 3am.

    A status cannot be doubly classified in this shape, because `STATUS_BANDS` is a mapping and a
    repeated key silently keeps the last value. The pairing is asserted from the other direction in
    `test_task_transitions.py`, where the literal source can be read.
    """
    known_bands = {
        BAND_AGENT_ACTIONABLE,
        BAND_AWAITING_PERSON,
        BAND_AWAITING_HANDOFF,
        BAND_WITH_REVIEWER,
        BAND_TERMINAL,
    }
    unclassified = sorted(set(TRANSITIONS) - set(STATUS_BANDS))
    if unclassified:
        raise RuntimeError(
            "task statuses are missing a lifecycle band: "
            + ", ".join(unclassified)
            + " -- add each to STATUS_BANDS in hub/hub/task_transitions.py"
        )
    stray = sorted(status for status, band in STATUS_BANDS.items() if band not in known_bands)
    if stray:
        raise RuntimeError(
            "task statuses are classified into an unknown band: "
            + ", ".join(f"{s} -> {STATUS_BANDS[s]!r}" for s in stray)
        )
    unknown = sorted(set(STATUS_BANDS) - set(TRANSITIONS))
    if unknown:
        raise RuntimeError(
            "STATUS_BANDS classifies statuses the transition machine does not define: "
            + ", ".join(unknown)
        )


_check_bands()


#: May a loop firing claim a task in this status -- that is, does firing an agent at it make
#: progress possible? Consumed by `scheduler.CLAIMABLE_LOOP_TASK_STATUSES`.
CLAIMABLE_STATUSES: FrozenSet[str] = _statuses_in(BAND_AGENT_ACTIONABLE)

#: May a firing claim a task in this status **if the agent asking is not the one that finished
#: it**? Consumed by `scheduler.REVIEWABLE_LOOP_TASK_STATUSES`.
#:
#: Deliberately not folded into `CLAIMABLE_STATUSES`. That set answers a question about a status
#: alone, and this one cannot be answered without an actor -- merging them would make the claim
#: actor-blind again, which `loop-becomes-a-flow` task 3.3 names as the obvious wrong fix.
REVIEWABLE_STATUSES: FrozenSet[str] = _statuses_in(BAND_AWAITING_HANDOFF)

#: Can a task in this status be a loop's *current item* on the board? The claimable statuses, plus
#: `blocked`, plus the reviewable ones -- and each addition is there because the board must be able
#: to name work the firing is dealing with even when it is not ordinary claimable work.
#:
#: `blocked` was the first: not something a firing may take, and exactly what the operator needs to
#: see the loop waiting on. `completed` joined it in `loop-becomes-a-flow` group 3 for the mirror
#: reason -- a firing *can* now claim one, for review, and if the board's query could not return
#: the row it would show no current item for a loop that was actively reviewing. That is the same
#: defect `blocked` caused on 2026-08-21, arriving from the other direction.
#:
#: `under_review` is the third, added by finding F45. A review that has been dispatched moves the
#: task into `BAND_WITH_REVIEWER`, and a band the board's query could not return would hide the
#: firing's most active work for exactly as long as the review takes -- the same defect `blocked`
#: caused from one direction and `completed` from the other, arriving from a third.
#:
#: Membership here is not a claim that the task is claimable. The board's own walk still shows a
#: task as current only when the firing would claim it or it is `blocked`, so a `completed` task
#: nobody may review is in this set and still not displayed as current.
CURRENT_ITEM_STATUSES: FrozenSet[str] = _statuses_in(
    BAND_AGENT_ACTIONABLE, BAND_AWAITING_PERSON, BAND_AWAITING_HANDOFF, BAND_WITH_REVIEWER
)

#: Statuses meaning "a reviewer already has this". Not claimable by anybody: the reviewer finishes
#: it, or the operator resolves it. Consumed by `scheduler.WITH_REVIEWER_LOOP_TASK_STATUSES`.
#:
#: This set is what closes finding F45. Before it, a dispatched review left the task in `completed`
#: -- still inside `REVIEWABLE_STATUSES` -- so a reviewer that finished without transitioning had
#: its work offered straight back to it on the next tick, forever, with no stop condition able to
#: end it and every tick reading as healthy.
WITH_REVIEWER_STATUSES: FrozenSet[str] = _statuses_in(BAND_WITH_REVIEWER)

#: Is this task finished, for the purpose of binding a run to it? Consumed by
#: `run_task_binding.TERMINAL_FOR_BINDING`.
TERMINAL_STATUSES: FrozenSet[str] = _statuses_in(BAND_TERMINAL)

#: Is this task live work somebody is accountable for right now? Consumed by both
#: `agents._ACTIVE_TASK_STATUSES` and `checkpoints._LIVE_TASK_STATUSES`, which were two identical
#: literals in two files before this.
#:
#: `blocked` is absent deliberately and has always been: a task waiting on a person is not work
#: anyone is presently doing. `under_review` is present for the mirror reason -- somebody else is
#: doing it.
LIVE_STATUSES: FrozenSet[str] = _statuses_in(BAND_AGENT_ACTIONABLE, BAND_WITH_REVIEWER)


# --------------------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------------------


def is_entry_status(status: str) -> bool:
    """May a task be created directly in `status`?"""
    return status in ENTRY_STATUSES


def allowed_targets(from_status: str, actor_kind: str) -> FrozenSet[str]:
    """The statuses `actor_kind` may move a task to from `from_status`.

    An unknown `from_status` yields the empty set rather than raising: callers reach this with a
    status read from a row, and a status the map does not know is exactly the case that should be
    refused rather than crash.
    """
    edges = TRANSITIONS.get(from_status, {})
    return frozenset(target for target, actors in edges.items() if actor_kind in actors)


def is_allowed(from_status: str, to_status: str, actor_kind: str) -> bool:
    """May `actor_kind` move a task from `from_status` to `to_status`?"""
    return to_status in allowed_targets(from_status, actor_kind)


def allowed_map_for(actor_kind: str) -> Dict[str, Tuple[str, ...]]:
    """The whole map as one actor sees it — `{from_status: (reachable, ...)}`.

    This is what the operator's status control reads (design D13): one actor-scoped fetch, from the
    same declaration the service enforces, so the client never holds a second copy of the map and a
    board of forty cards costs one request rather than forty. Targets are sorted so the response is
    stable and diffable.
    """
    return {
        from_status: tuple(sorted(allowed_targets(from_status, actor_kind)))
        for from_status in sorted(TRANSITIONS)
    }


def refusal_detail(from_status: str, to_status: str, actor_kind: str) -> str:
    """Why a move was refused, phrased so the reader can correct itself.

    A refused agent's only feedback is this string, so it names both the current status and what is
    actually reachable — an agent told merely "forbidden" retries the same call.
    """
    reachable = sorted(allowed_targets(from_status, actor_kind))
    if from_status not in TRANSITIONS:
        return f"Task is in unknown status {from_status!r}, from which no transition is defined."
    if not reachable:
        return (
            f"Cannot move a task from {from_status!r} to {to_status!r}: "
            f"a{'n operator' if actor_kind == ACTOR_OPERATOR else 'n agent run'} "
            f"has no transitions available from {from_status!r}."
        )
    return (
        f"Cannot move a task from {from_status!r} to {to_status!r}. "
        f"From {from_status!r} the available transitions are: {', '.join(reachable)}."
    )
