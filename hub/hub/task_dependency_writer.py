"""The one place a `TaskDependency` edge is created, whoever asked for it.

Until F37's sibling finding (F36) this had exactly one caller — `spec_tasks.materialise()`, reached
only when an approved document carried `depends_on` keys. `TaskUpdate` refused the field with
`422 extra_forbidden` and no dependencies route existed, so an operator could not say "B needs A"
about two tasks they created. The whole subsystem — `dependency_gate`, the Dependencies board tab,
`task_dependencies` and `task_dependency_references`, `Task.dependency_state`, and the
`prerequisites`/`dependents` fields on every task response — was reachable only if an agent happened
to author the right keys into a document that was then approved. In the sweep the agent authored a
five-task decomposition with no `depends_on` at all, so the graph came out empty and the gate was
never exercisable.

Two callers now, and one writer, so the graph cannot be built two different ways. The document path
keeps its own key resolution (document-local keys are its vocabulary, not the operator's) and hands
this module resolved task ids, exactly as the operator path does.

**The cycle check lives here rather than in either caller**, which is the point of extracting it: it
was absent before, so a document declaring `a -> b -> a` produced a graph on which
`dependency_gate` would refuse both tasks forever, each waiting on the other.

The two callers want different things from a refusal, so this reports rather than decides. The
operator path turns a refusal into a `400` naming what is wrong. The document path records a
`TaskDependencyReference` — its existing channel for a `depends_on` it could not honour — because
an approval must not fail over the shape of a dependency, the same reasoning
`materialise_quietly` already states.
"""

from __future__ import annotations

from typing import Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Task, TaskDependency
from .utils import short_id

#: Nothing was wrong and an edge now exists.
ADDED = "added"
#: The edge already existed. Not an error — declaring it twice is a restatement, not a conflict.
DUPLICATE = "duplicate"
#: A task cannot depend on itself. Silently skipped by the document path, refused for an operator.
SELF = "self"
#: One of the two tasks does not exist in this project.
MISSING = "missing"
#: The edge would close a loop, so every task in it would wait on another forever.
CYCLE = "cycle"


async def _prerequisites_of(session: AsyncSession, task_id: str) -> Set[str]:
    return set(
        (
            await session.execute(
                select(TaskDependency.depends_on_task_id).where(TaskDependency.task_id == task_id)
            )
        )
        .scalars()
        .all()
    )


async def would_cycle(session: AsyncSession, task_id: str, depends_on_task_id: str) -> bool:
    """Whether making `task_id` depend on `depends_on_task_id` closes a loop.

    Walks prerequisites forward from the proposed target: if `task_id` is reachable that way, it is
    already upstream of its own would-be prerequisite. Iterative and `seen`-guarded so an existing
    cycle — one written before this check existed — cannot make the check itself hang.
    """
    seen: Set[str] = set()
    frontier = [depends_on_task_id]
    while frontier:
        current = frontier.pop()
        if current == task_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(await _prerequisites_of(session, current))
    return False


async def add_dependency(
    session: AsyncSession,
    project_id: str,
    task_id: str,
    depends_on_task_id: str,
    *,
    known_edges: Optional[Set[str]] = None,
) -> str:
    """Stage one dependency edge. Returns one of the module constants; never raises for a bad edge.

    `known_edges` lets a caller adding several edges for one task pass the set it already read,
    rather than making this re-query per edge. It is updated in place when an edge is added, so a
    duplicate within a single batch is caught too.

    Nothing is committed. The caller commits, so a refused edge cannot leave a partial graph.
    """
    if task_id == depends_on_task_id:
        return SELF

    edges = known_edges if known_edges is not None else await _prerequisites_of(session, task_id)
    if depends_on_task_id in edges:
        return DUPLICATE

    rows = (
        (
            await session.execute(
                select(Task.id).where(
                    Task.project_id == project_id,
                    Task.id.in_([task_id, depends_on_task_id]),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(set(rows)) != 2:
        return MISSING

    if await would_cycle(session, task_id, depends_on_task_id):
        return CYCLE

    session.add(
        TaskDependency(
            id=f"tdep-{short_id()}",
            project_id=project_id,
            task_id=task_id,
            depends_on_task_id=depends_on_task_id,
        )
    )
    edges.add(depends_on_task_id)
    return ADDED


async def remove_dependency(
    session: AsyncSession, project_id: str, task_id: str, depends_on_task_id: str
) -> bool:
    """Drop one edge. Returns whether there was one to drop.

    Removal has no cycle question and no ordering question — a graph with an edge taken out is
    still a graph — so this is deliberately much smaller than its counterpart above.
    """
    row = (
        (
            await session.execute(
                select(TaskDependency).where(
                    TaskDependency.project_id == project_id,
                    TaskDependency.task_id == task_id,
                    TaskDependency.depends_on_task_id == depends_on_task_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return False
    await session.delete(row)
    return True
