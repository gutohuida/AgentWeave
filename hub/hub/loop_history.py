"""The two events a loop's history gains from this change: its creation and each addition to its queue.

`a-loops-history-records-its-creation-and-queue-additions` (D3/D4). Every writer here uses
`persist_event(commit=False)`, so the entry lands or rolls back with the rows it describes; the
caller commits. The actor is `data.by = {kind, agent, run_id}`, and the event's `agent` column holds
the agent for agent actors only.
"""

from typing import Any, Dict, Iterable, Optional, Tuple

from .db.models import SpecDocument
from .utils import persist_event

DOOR_JOBS = "jobs"
DOOR_APPROVAL = "approval"

SOURCE_INITIAL_TASKS = "initial_tasks"
SOURCE_CREATE_TASK = "create_task"
SOURCE_DOCUMENT = "document"
SOURCE_FLOW_BUILT = "flow_built"


def by_operator() -> Dict[str, Any]:
    return {"kind": "operator", "agent": None, "run_id": None}


def by_agent(agent: str, run_id: Optional[str]) -> Dict[str, Any]:
    return {"kind": "agent", "agent": agent, "run_id": run_id}


def by_headers(agent_identity: Optional[str], run_identity: Optional[str]) -> Dict[str, Any]:
    """The actor of a route that reads the `X-AgentWeave-Agent`/`-Run` pair: an agent only when both are
    present, which is how the routes themselves tell an agent run from the operator."""
    if agent_identity and run_identity:
        return by_agent(agent_identity, run_identity)
    return by_operator()


def _agent_of(by: Dict[str, Any]) -> Optional[str]:
    return by.get("agent") if by.get("kind") == "agent" else None


async def record_created(
    session: Any,
    project_id: str,
    loop: Any,
    *,
    by: Dict[str, Any],
    door: str,
    agent: str,
) -> None:
    # The id is what the loop stores; the path is what the operator recognises it by, so both ride.
    document = (
        await session.get(SpecDocument, loop.spec_document_id) if loop.spec_document_id else None
    )
    await persist_event(
        session,
        project_id,
        "loop_created",
        {
            "by": by,
            "door": door,
            "agent": agent,
            "purpose": loop.purpose or "",
            "document": loop.spec_document_id,
            "document_path": document.path if document is not None else None,
        },
        agent=_agent_of(by),
        loop_id=loop.id,
        commit=False,
    )


async def record_tasks_added(
    session: Any,
    project_id: str,
    loop_id: str,
    tasks: Iterable[Tuple[str, str]],
    *,
    by: Dict[str, Any],
    source: str,
) -> None:
    """One entry for the call, listing `(id, title)` of each task it added; nothing for no tasks."""
    listed = [{"id": task_id, "title": title} for task_id, title in tasks]
    if not listed:
        return
    await persist_event(
        session,
        project_id,
        "loop_tasks_added",
        {"by": by, "source": source, "tasks": listed},
        agent=_agent_of(by),
        loop_id=loop_id,
        commit=False,
    )
