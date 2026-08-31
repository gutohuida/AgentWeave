"""Which runs this Hub process is executing right now, and whether a task has a live turn.

Two registries and one question. The registries used to live in `api/v1/agent_trigger`, which is
where they are written; they moved here because `requirement_gate` has to *read* them and importing
a route module from the transition service's gate would invert the layering (design D3, open
question 2). `agent_trigger` registers into these; nothing else writes them.

**Why a registry rather than the `Run` column.** `reconcile_interrupted_runs` runs only in
`lifespan()` startup (`main.py:350`), so a crashed agent leaves `Run.status == "running"` until the
Hub restarts. A predicate reading that column alone would wedge approval indefinitely on one crash.
The registry holds an entry per run *this* process is executing, so a run recorded `running` by a
previous Hub process is simply absent — and absence means not live, which fails in the safe
direction: it permits approval rather than blocking it.

**Why not `pty_runner.pid_alive`.** Its own docstring warns precisely the caller added here: *"If a
future caller checks liveness of a process this same Hub killed, it needs `waitpid(WNOHANG)` or a
`/proc/<pid>/stat` state check — do not assume this function alone is enough there"*
(`pty_runner.py:150-156`). On POSIX `os.kill(pid, 0)` succeeds for a zombie, and the function
inherits a pid-reuse limitation besides. The registry answers without either.

**Why membership rather than `PtySession.isalive()`.** Design D3 named `isalive()`; implementing it
showed membership is the stricter and the correct signal, and the difference is exactly the window
this predicate exists to close. `_execute_run` pops its registry entry in a `finally`
(`agent_trigger.py:2262`) that runs *after* the finalize block has taken the turn's snapshot commit
and restamped the evidence footprints (`:2036-2050`). `isalive()` goes false the moment the process
exits — which is *inside* the window, before the commit that holds the work exists. Membership
covers the whole turn, including the finalize block that produces the very commit an approval is
waiting for. So the entry's presence is the answer and its `isalive()` is not consulted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Run, Task
from .pty_runner import PipeSession, PtySession

# Live process session per in-progress run_id, so a stop request can reach the actual process, and
# so liveness can be answered without asking the OS. `_execute_run` populates and clears this
# around its own read/wait loop, since that is the only place the session instance exists. The
# legacy `_active_ptys` name is kept as the exported one to avoid churning lifecycle code that does
# not depend on the transport type.
active_ptys: Dict[str, PipeSession | PtySession] = {}

# run_ids currently executing over the Codex app-server transport. That path has no
# PtySession/PipeSession to register above — `codex_appserver.run_turn` owns its own subprocess
# internally — so the stop endpoint, the shutdown teardown and the liveness question below need a
# separate way to know such a run exists and is still working.
active_app_server_runs: Set[str] = set()


@dataclass(frozen=True)
class LiveTurn:
    """A run this process is executing that is bound to the task in question."""

    run_id: str
    agent: str


def live_run_ids() -> Set[str]:
    """Every run this Hub process is currently executing, over either transport."""
    return set(active_ptys) | set(active_app_server_runs)


def run_is_live(run_id: str) -> bool:
    """Is *run_id* a turn this process is executing right now?"""
    return run_id in active_ptys or run_id in active_app_server_runs


async def live_turn_for_task(
    session: AsyncSession, task: Task, *, acting_run_id: Optional[str] = None
) -> Optional[LiveTurn]:
    """The live turn bound to *task*, or `None`.

    **A turn is never blocked by itself** (design D10). `acting_run_id` is excluded, because since
    migration `0092` a review run is bound to the very task it inspects —
    `run_task_binding.task_named_by` resolves `entry.task_id or entry.review_task_id` (`:170-189`)
    and `_bind` writes `run.task_id = task.id` (`:427`). Counting the acting run would refuse every
    review the product staffs, and would refuse it with a remedy the refused party cannot take: its
    only way out is for the turn to end, and it *is* the turn.

    That exclusion carries a known residual, named rather than discovered later (design D10, round
    3): `_bind` binds a *working* run to its task exactly as it binds a review run, so an agent
    mid-turn on a task whose `completed` the **operator** recorded and whose assignee the operator
    cleared may approve its own in-flight work from inside its own turn. Closing it costs a join
    through `InboundQueueEntry.review_task_id`, which `Run` does not carry; that trade was
    considered and declined for scope. `test_approval_waits_for_the_turn.py` pins the shape.

    Scoped to runs *bound* to this task. The residual there is a run doing a task's work without
    being bound to it — the same gap `run_task_binding` already carries for evidence authorship.
    The ordinary path binds the run before it may move the task past `in_progress`
    (`task_transition_service._guard_run_holds_the_task`), so an unbound run doing the work is a
    shape the product does not produce on its own.
    """
    live = live_run_ids()
    live.discard(acting_run_id or "")
    if not live:
        return None

    rows = (
        (
            await session.execute(
                select(Run).where(
                    Run.project_id == task.project_id,
                    Run.task_id == task.id,
                    Run.id.in_(sorted(live)),
                )
            )
        )
        .scalars()
        .all()
    )
    for run in rows:
        return LiveTurn(run_id=run.id, agent=run.agent or "an agent")
    return None
