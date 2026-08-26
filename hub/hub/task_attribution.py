"""Who is on a task, and in what capacity. One computation, one owner.

`agent-loops` states the concept: *"An agent attributed to a task SHALL be attributed in a stated
capacity."* Four capacities, and **each has its own source**:

```
  working   ← the runs table                 something is running against this task right now
  held      ← the firing, minus the runs     staffed, and nothing is running
  next      ← the firing's selection         who the next firing would give it to
  assigned  ← the task's own assignee        nobody is being selected; this is the row's own name
```

## Why this module exists

The bug it ends is not "two inputs". It is **one input asked a question it does not answer.**

`FiringDecision`'s cannot-staff collection means *"this firing cannot staff anybody onto this"* and
nothing more. The scheduler appends an `under_review` task with an assignee to it unconditionally
and deliberately — that is what keeps a review which ended without a verdict visible on the board
instead of vanishing from it (findings F23 and F45). It is a statement about **staffing**, and it
was read as a statement about **activity**. So a board rendered `relay` as mid-turn on a task whose
review run had already failed, with no run anywhere in the database (finding F63).

That collection had been public on a frozen dataclass, so any consumer could pick it up and read it
as anything. One did. It is private now, and this module is its only reader — enforced by a
source-scanning test, in the idiom `test_nothing_pushes` already uses for `task_integration.py`'s
never-push guarantee, because Python cannot enforce it and a comment is not a mechanism.

## Why the derivation lives here rather than in the renderer

F49 was a five-line derivation bug that was live from the day it shipped: `decision.in_flight` is a
sequence of `(task_id, agent)` pairs, `set(...)` of it is a set of *tuples*, and the membership test
asked it with a bare task id — so it never matched and `working` was unreachable in production. It
had five vitest cases over the renderer and **zero tests over the derivation**. The renderer was
tested; the thing that decided the answer was not.

So: a module, in Python, tested per capacity, with a mutation check per branch. `jobs.py` renders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Run, Task

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .scheduler import FiringDecision

#: Something is running against this task right now.
CAPACITY_WORKING = "working"
#: Staffed to this agent, and nothing is running. The state F23 asked to keep visible — a review
#: whose turn ended without a verdict, or failed — finally wearing its own name instead of
#: borrowing `working`'s (finding F63).
CAPACITY_HELD = "held"
#: Who the next firing would give it to. For a `completed` task that is its reviewer, not the agent
#: that did the work (finding F26).
CAPACITY_NEXT = "next"
#: Nobody is being selected and nothing is running; this is the row's own assignee. The `blocked`
#: case, waiting on a person.
CAPACITY_ASSIGNED = "assigned"

CAPACITIES = (CAPACITY_WORKING, CAPACITY_HELD, CAPACITY_NEXT, CAPACITY_ASSIGNED)


@dataclass(frozen=True)
class Attribution:
    """Who is on a task and in what capacity, or neither.

    `agent` and `capacity` are set together or not at all. A task nobody is on gets
    `Attribution()`, and the renderer omits the attribution rather than showing a blank one — a
    reader must never see a name with no meaning attached, which is F26 in one line.
    """

    agent: Optional[str] = None
    capacity: Optional[str] = None

    def __bool__(self) -> bool:
        return self.agent is not None


@dataclass(frozen=True)
class LiveRuns:
    """What the runs table says is running, right now, for one set of projects.

    Asked once per batch rather than per task: this is the seventh query in the loop-summary path
    and it stays batched for design D7's reason.

    Two collections rather than one because `Run.task_id` is not always set. `task_ids` is the
    precise answer and is the only one this module trusts to mean *"this task is being worked"*.
    `agents_without_task` is the imprecise one — see `agent_fallback` on `attribute`.
    """

    task_ids: frozenset
    agents_without_task: frozenset


async def live_runs(session: AsyncSession, project_ids: Iterable[str]) -> LiveRuns:
    """Everything running in *project_ids*, split by whether it knows what task it is for."""
    ids = list(project_ids)
    if not ids:
        return LiveRuns(frozenset(), frozenset())
    rows = (
        await session.execute(
            select(Run.agent, Run.task_id).where(
                Run.project_id.in_(ids),
                Run.status == "running",
            )
        )
    ).all()
    return LiveRuns(
        task_ids=frozenset(task_id for _agent, task_id in rows if task_id),
        agents_without_task=frozenset(agent for agent, task_id in rows if not task_id),
    )


@dataclass(frozen=True)
class FlowStaffing:
    """What one firing decision says about who is on what — the only shape that leaves it.

    Built by `staffing_from_decision`, which is the sole reader of `FiringDecision`'s private
    cannot-staff collection. Consumers get two named questions instead of one collection they can
    misread: *who did this firing select*, and *who is this firing unable to staff*.
    """

    #: `task_id -> agent` the firing chose to start.
    selected: Mapping[str, str]
    #: `task_id -> agent` the firing cannot staff anybody onto, because that agent already holds it.
    #: **Not** "is running" — that is the confusion this whole module exists to end.
    unstaffable: Mapping[str, str]

    def agent_for(self, task_id: str) -> Optional[str]:
        """Who this firing attributes *task_id* to, selection winning over held work.

        Selection wins because it is the more current statement: if this firing is about to hand
        the task to somebody, that is who it is for.
        """
        return self.selected.get(task_id) or self.unstaffable.get(task_id)


def staffing_from_decision(decision: "FiringDecision") -> FlowStaffing:
    """The one place `FiringDecision`'s cannot-staff collection is read.

    Kept to a single function so the source-scanning test has one thing to check and the
    encapsulation is a fact about the codebase rather than a note in a docstring.
    """
    return FlowStaffing(
        selected={selection.task.id: selection.agent for selection in decision.selections},
        unstaffable=dict(decision._cannot_staff),
    )


def attribute(
    task: Task,
    *,
    staffing: FlowStaffing,
    live: LiveRuns,
    agent_fallback: bool = True,
) -> Attribution:
    """Which agent is on *task*, and in what capacity. The one entry point.

    Reads as the fall-through it is:

    - the firing cannot staff it, and something is running against it → `working`;
    - the firing cannot staff it, and nothing is running → `held`;
    - the firing selected it → `next`;
    - neither, and the task names an assignee → `assigned`.

    **`agent_fallback` is a defect being carried deliberately, not a feature.** When `Run.task_id`
    is set, `live.task_ids` answers precisely. It is not set for a flow's own work firings — 61
    job-origin queue entries on the trial database, none carrying `task_id` — so without the
    fallback every actively-worked flow task would read `held`, which is the same class of lie in
    the other direction. Matching on the agent instead over-reports `working` when that agent is
    mid-turn on a *different* task: bounded and one-directional, where the bug it replaces was
    unbounded.

    It exists because only half of the missing run→task edge has been written.
    `one-answer-to-what-is-happening` group 1 wrote it for reviews;
    `openspec/explorations/2026-08-26-the-other-half-of-the-binding.md` is the other half, and
    removing this parameter is what closing that gap buys. The parameter exists so a test can
    demonstrate the difference rather than argue about it.
    """
    agent = staffing.agent_for(task.id) or task.assignee
    if agent is None:
        return Attribution()

    if task.id in staffing.unstaffable:
        running = task.id in live.task_ids or (agent_fallback and agent in live.agents_without_task)
        return Attribution(agent, CAPACITY_WORKING if running else CAPACITY_HELD)

    if task.id in staffing.selected:
        return Attribution(agent, CAPACITY_NEXT)

    return Attribution(agent, CAPACITY_ASSIGNED)
