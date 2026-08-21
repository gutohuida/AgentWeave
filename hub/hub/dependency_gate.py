"""The gate: a task may not start while a task it depends on is not yet approved.

Lives beside `requirement_gate` for the same reason that one does: a second enforcement point is a
second thing to bypass, so this is called from inside `task_transition_service.apply_transition`,
before the history row is written, rather than from each of its callers.

**On `-> in_progress` only, including the `blocked -> in_progress` resume edge** (`task-dependencies`
design D1). Not `-> assigned`: a whole wave can be routed ahead of time and each task starts only
once its own prerequisites clear — gating assignment would make assigning ahead impossible.

**Met at `approved`, nothing earlier** (design D2, and `TaskDependency`'s own docstring: "may not
start until `depends_on_task_id` is `approved`"). A dependency chain therefore cannot advance with a
single agent alone, and cannot advance past a dependency that is done but unreviewed.

**A `rejected` prerequisite gates permanently**, reported separately from "not yet approved" because
the remedy is different — reopening or rewriting the document that declared the dependency, not
waiting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Task, TaskDependency

#: The one status a prerequisite must reach. Nothing earlier satisfies it (design D2).
MET_STATUS = "approved"

#: A prerequisite in this status will never satisfy the dependency on its own — the remedy is to
#: reopen or rewrite the document, not to wait.
PERMANENTLY_UNMET_STATUS = "rejected"


@dataclass
class DependencyRefusal:
    """Why the gate refused, in a shape a surface can render without parsing prose."""

    #: Prerequisites that may still become `approved`.
    unmet: List[Dict[str, str]] = field(default_factory=list)
    #: Prerequisites that never will — a `rejected` prerequisite, reported separately because the
    #: remedy differs (reopen/rewrite, not wait).
    rejected: List[Dict[str, str]] = field(default_factory=list)

    @property
    def refuses(self) -> bool:
        return bool(self.unmet or self.rejected)

    def detail(self) -> str:
        parts: List[str] = []
        for entry in self.rejected:
            parts.append(
                f"{entry['title']!r} ({entry['id']}) was rejected and will not become approved on "
                "its own — reopen it, or edit the document that declared this dependency"
            )
        for entry in self.unmet:
            parts.append(
                f"{entry['title']!r} ({entry['id']}) is {entry['status']!r}, not yet approved"
            )
        return "This task depends on work that is not ready to build on: " + "; ".join(parts) + "."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": "dependency_unmet",
            "unmet": list(self.unmet),
            "rejected": list(self.rejected),
            "message": self.detail(),
        }


async def evaluate(session: AsyncSession, task: Task) -> DependencyRefusal:
    """Every prerequisite `task` names, sorted into unmet and permanently rejected.

    A task with no `TaskDependency` rows returns a refusal that refuses nothing — the query below
    has nothing to iterate, so a task with no dependencies transitions exactly as it did before this
    gate existed (task 5.9).
    """
    refusal = DependencyRefusal()
    prerequisites = (
        (
            await session.execute(
                select(Task)
                .join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
                .where(TaskDependency.task_id == task.id)
            )
        )
        .scalars()
        .all()
    )
    for prerequisite in prerequisites:
        if prerequisite.status == MET_STATUS:
            continue
        entry = {"id": prerequisite.id, "title": prerequisite.title, "status": prerequisite.status}
        if prerequisite.status == PERMANENTLY_UNMET_STATUS:
            refusal.rejected.append(entry)
        else:
            refusal.unmet.append(entry)
    return refusal
