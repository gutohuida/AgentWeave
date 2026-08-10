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

    def __post_init__(self) -> None:
        if self.kind not in ACTOR_KINDS:
            raise ValueError(f"actor kind must be one of {list(ACTOR_KINDS)}, got {self.kind!r}")
        if self.kind == ACTOR_RUN and not self.run_id:
            raise ValueError("an actor of kind 'run' must carry a run_id")
        if self.kind == ACTOR_OPERATOR and self.run_id:
            raise ValueError("an actor of kind 'operator' must not carry a run_id")

    @property
    def is_operator(self) -> bool:
        return self.kind == ACTOR_OPERATOR


def operator() -> Actor:
    """The operator, acting directly."""
    return Actor(kind=ACTOR_OPERATOR)


def run_actor(run_id: str) -> Actor:
    """An authenticated agent run."""
    return Actor(kind=ACTOR_RUN, run_id=run_id)


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

#: Every status the machine knows. Pinned to the two independent declarations in
#: `src/agentweave/constants.py` and `hub/hub/schemas/tasks.py` by
#: `hub/tests/test_task_transitions.py`, so a ninth status cannot be added anywhere without
#: declaring its edges here.
STATUSES: FrozenSet[str] = frozenset(TRANSITIONS)


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
