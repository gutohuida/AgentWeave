"""Which workspace a task-bound turn is entitled to, answered from the database (design D1, D4).

`worktrees` is deliberately independent of the DB/session layer, so somebody has to turn "this turn
is bound to task X" into the three plain values `worktrees.resolve_turn_workspace` takes — the task
id it may provision for, the commit its branch is cut from, and the commits its prerequisites
contributed. That is this module, and it is a module rather than another hundred lines of
`agent_trigger` because every one of those three answers has a rule behind it that is worth being
able to test on its own.

**It reads. It never writes.** In particular it never writes `Task.workspace_scheme`: that column is
stamped once by migration `0095` and by nothing else, which is the entire mechanism behind "the
grandfathered set can only shrink" (design D4). `test_task_workspace_scheme.py` scans this package
for every spelling of a write, so the rule is enforced rather than asserted.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import dependency_gate, task_integration, worktrees
from .db.models import Project, Task, TaskDependency

logger = logging.getLogger(__name__)

#: The scheme a task created from here on gets: its own worktree on its own branch.
TASK_SCHEME = "task"

#: The scheme migration `0095` stamped onto every task that had already been worked when per-task
#: isolation shipped. Those tasks keep the shared per-agent checkout for the rest of their lives,
#: because the alternative is starting them clean from the integration base with their own prior
#: work missing (design D4).
AGENT_SCHEME = "agent"


class TurnWorkspace(NamedTuple):
    """What `worktrees.resolve_turn_workspace` needs, and nothing else.

    `task_id` is `None` for every turn that is not getting a task workspace — unbound, grandfathered,
    or carrying an id this product could not have minted. Collapsing those three into one value is
    deliberate: they are three reasons for the same answer, and the caller has no decision left to
    make between them.
    """

    task_id: Optional[str]
    base: Optional[str]
    prerequisites: Tuple[str, ...]


#: The answer for every turn that is not getting a task workspace.
UNBOUND = TurnWorkspace(None, None, ())


async def resolve_turn_workspace_inputs(
    session: AsyncSession,
    *,
    project_id: str,
    repo_root: Path,
    task: Optional[Task],
) -> TurnWorkspace:
    """The task id, base and prerequisite commits for *task*'s workspace.

    Three ways to get `UNBOUND`, and each is a decision rather than a fallback:

    1. **No task.** The turn is chat, exploration, a question or scheduled work, and gets the
       agent's own workspace (design D3).
    2. **A grandfathered task** (`workspace_scheme == 'agent'`). Read, never recomputed — R1
       proposed deciding this live from a prior run's `snapshot_commit_sha` and it was wrong in both
       halves, in the direction that loses an agent's own work (design D4).
    3. **A task id `validate_task_id` refuses.** Measured rather than anticipated: ids the product
       mints are `task-` followed by hex (`short_id`), but nothing in the schema enforces that, and a
       row that arrived another way must not be able to take every turn on it out. Refusing the turn
       would be an outage; a task branch cannot be cut for an id that cannot become a ref and a path.
       So the turn runs where it ran before — today's behaviour, which is what grandfathering
       already means — and it is logged, because unlike (1) and (2) it is not a shape this product
       expects to see.
    """
    if task is None:
        return UNBOUND
    if task.workspace_scheme != TASK_SCHEME:
        return UNBOUND
    try:
        worktrees.validate_task_id(task.id)
    except ValueError as exc:
        logger.warning(
            "task %s cannot be given its own workspace (%s); its turns run in the per-agent "
            "checkout, as they did before per-task isolation",
            task.id,
            exc,
        )
        return UNBOUND

    return TurnWorkspace(
        task_id=task.id,
        base=await _integration_base(session, project_id, repo_root),
        prerequisites=await _prerequisite_commits(session, task, repo_root),
    )


async def _integration_base(session: AsyncSession, project_id: str, repo_root: Path) -> str:
    """What a task branch is cut from: the branch approval will merge *into* (design D1).

    `Project.main_branch` when it is set **and resolves**, and the project checkout's `HEAD`
    otherwise. Both halves matter. Cutting from `HEAD` unconditionally — which is what
    `ensure_worktree` does for an agent branch — makes the merge base with the integration target
    whatever branch or detached commit the operator's checkout happens to be sitting on. And a
    `main_branch` naming a ref this repository does not have would fail the `worktree add` outright,
    turning a stale setting into a refused turn where today's behaviour is available and harmless.
    """
    project = await session.get(Project, project_id)
    main_branch = project.main_branch if project is not None else None
    if main_branch and task_integration.branch_exists(repo_root, main_branch):
        return main_branch
    return "HEAD"


async def _prerequisite_commits(
    session: AsyncSession, task: Task, repo_root: Path
) -> Tuple[str, ...]:
    """Every commit *task*'s direct prerequisites contributed, in a stable order.

    **Direct only, and that is sufficient rather than approximate.** If A → B → C and each link was
    provisioned under this scheme, B's branch already carries A's work, so merging B's commits into
    C brings A's along (design D1, "transitivity is free"). A grandfathered link breaks that chain,
    which is why grandfathering is per-task and self-extinguishing.

    The commits come from `task_integration.merge_targets`, which is already exactly this question —
    *what would approving this task have merged*. Calling it rather than restating it is the point:
    "which commit is this task's work" having two implementations is the drift that produced F58 in
    the first place, and that argument is what moved this from `integration_targets` to
    `merge_targets` (design D12) once a second answer to the same question existed.

    **Why this is not merely nicer.** `task-dependencies` SHALLs that a task's isolated checkout
    contains the work of every prerequisite it was permitted to start on, *"whether or not that work
    reached the project's main branch"* — and it names the dirty and parked checkouts
    (`task_integration.py:329-335`, both of which skip the merge while approval stands) as the
    reasons the requirement exists. An evidence-free loop task's prerequisite work would otherwise
    reach its successor only through the main branch, which is the exact dependence that sentence
    forbids.

    **The `approved` filter is load-bearing, and it applies to the branch-tip route only.** This
    function's previous docstring defended `integration_targets` on the grounds that anything else
    *"would carry work nobody accepted into a checkout an agent is about to write in"*. On the
    evidence route that filter is automatic — nothing is a target until a reviewer accepts it, at
    any status. On the branch-tip route there is no automatic filter at all: an in-progress
    prerequisite's tip is a real commit, and on that route approval *is* the acceptance, which is
    why the status check restores exactly the property the sentence above is defending.

    **Applying it to both routes would have been a regression, and F159 is why** (design D12 said
    to, unconditionally; found while implementing it). The dependency gate does not make a
    prerequisite `approved` by the time this runs: a task branch is cut at **dispatch**
    (`pending -> assigned`), one edge before the gate fires, and `agent_trigger` consults no
    dependency gate at all (F158). So at the moment prerequisites are seeded, an unapproved
    prerequisite carrying accepted evidence is the ordinary case, not an exotic one — and it seeds
    that checkout today. A blanket status check would have stopped it, breaching the same
    requirement D12 exists to satisfy, in the other direction.

    Resolved on every task-bound turn even though `ensure_task_worktree` merges only when it creates
    the branch. That costs one query for the overwhelmingly common case of a task with no
    prerequisites at all, and the alternative — deciding here whether the branch already exists —
    would put a copy of `ensure_task_worktree`'s own idempotency check on the far side of a race.
    """
    prerequisites = (
        (
            await session.execute(
                select(Task)
                .join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
                .where(TaskDependency.task_id == task.id)
                # Deterministic, so the merge order of two prerequisites is a property of the data
                # rather than of the database's row order.
                .order_by(Task.id)
            )
        )
        .scalars()
        .all()
    )
    commits: List[str] = []
    for prerequisite in prerequisites:
        governed = await task_integration.evidence_governs(session, prerequisite)
        if not governed and prerequisite.status != dependency_gate.MET_STATUS:
            continue
        for target in await task_integration.merge_targets(session, prerequisite, repo_root):
            if target.commit_sha and target.commit_sha not in commits:
                commits.append(target.commit_sha)
    return tuple(commits)
