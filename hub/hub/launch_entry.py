"""Which pool entry a run launches with (`a-profile-runs-each-task-on-a-runner-and-model-chosen-from-
its-pool`, FR-7, FR-8, FR-10, FR-13).

Every run starts on an entry of its profile's pool: a runner plus an optional effort. Which one:

- A task's **builder** run (the turn is bound to a task the agent builds) and a task's **review**
  run (the agent is staffed to check it) use the task's entry for that role. The first run of each
  fixes it, from the operator's Build choice for the task, else the document's recommendation when
  the pool holds it, else the pool's default; every later run of that role by the same agent uses
  the fixed entry, re-reviews after a send-back included (FR-7).
- Every other run — a chat, a job firing, a peer message, a mend turn — uses the pool's default.

A fixed or chosen entry no longer in the pool when a run starts falls back to the default, and the
run's trace says so (FR-8), unless the run continues a conversation whose last run launched on that
entry's runner: a conversation already started keeps the runner it started on.

A pool of one entry with no effort resolves to exactly the runner `Agent.runner_id` names with no
effort, which is what a run launched with before pools existed (FR-13).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import agent_pool, blocking, builds, project_workspace, spec_documents
from . import spec_payload as spec_payload_module
from .db.models import Agent, AgentPoolEntry, Run, Runner, SpecDocument, Task

logger = logging.getLogger(__name__)

BUILDER = "builder"
CHECKER = "checker"

#: The conversation override keys a pool entry decides (FR-10): which model, and how hard it
#: thinks. A runner is never an override; the posture (`permission_mode`) is not the pool's.
ENTRY_OVERRIDE_KEYS = frozenset({"model", "effort"})

#: Trace event naming a chosen entry that left the pool (FR-8).
FALLBACK_EVENT = "pool_entry_removed"


@dataclass
class LaunchEntry:
    """The entry a run launches with, and why."""

    runner_id: str
    effort: Optional[str]
    #: `default`, `build`, `recommendation`, `fixed` (the task's kept entry), `conversation` (a
    #: conversation keeping the runner it started on) or `fallback` (FR-8).
    source: str
    #: `builder` or `checker` for a task's run; None for every other run.
    role: Optional[str] = None
    #: Trace events to stage on the run's root (FR-8's line).
    events: List[Dict[str, Any]] = field(default_factory=list)


def _entry_dict(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict) or not value.get("runner_id"):
        return None
    return {"runner_id": str(value["runner_id"]), "effort": value.get("effort") or None}


def role_for(agent: str, task: Optional[Task], *, review: bool) -> Optional[str]:
    """Which of *task*'s entries a run of *agent* launches with, or None for the pool's default.

    A review run is the checker's. A turn bound to a task is the builder's when *agent* is the
    agent building it — its `builder`, or where it names none, its `assignee` — and nobody else's:
    another agent's turn about the task (a peer message, a mend turn) is not building it.
    """
    if task is None:
        return None
    if review:
        return CHECKER
    builder = task.builder or task.assignee
    return BUILDER if builder and builder == agent else None


async def _recommended(session: AsyncSession, task: Task, role: str) -> Optional[Dict[str, Any]]:
    """The entry *task*'s document recommends for *role*, or None. Best effort: a document that
    cannot be read recommends nothing, and the run starts on the default."""
    if not task.spec_document_id or not task.spec_task_key:
        return None
    document = await session.get(SpecDocument, task.spec_document_id)
    if document is None:
        return None
    try:
        workspace = await project_workspace.resolve_project_workspace(session, task.project_id)
        payload = await blocking.run(spec_documents.read_payload, workspace, document.path)
    except Exception:  # noqa: BLE001 -- an unreadable document recommends nothing
        logger.debug("reading %s for task %s's recommendation failed", document.path, task.id)
        return None
    return _entry_dict(spec_payload_module.declared_entries(payload, role).get(task.spec_task_key))


async def _conversation_runner(
    session: AsyncSession, conversation_id: Optional[str]
) -> Optional[str]:
    """The runner the conversation's latest recorded run launched on, or None."""
    if not conversation_id:
        return None
    return (
        await session.execute(
            select(Run.runner_id)
            .where(Run.conversation_id == conversation_id, Run.runner_id.is_not(None))
            .order_by(Run.started_at.desc())
            .limit(1)
        )
    ).scalar()


async def _label(session: AsyncSession, entry: Dict[str, Any]) -> str:
    runner = await session.get(Runner, entry["runner_id"])
    base = agent_pool.entry_label(runner, entry.get("effort"))
    return f"{base} (runner {runner.name})" if runner is not None else base


async def resolve(
    session: AsyncSession,
    agent_row: Agent,
    *,
    task: Optional[Task] = None,
    review: bool = False,
    conversation_id: Optional[str] = None,
) -> Optional[LaunchEntry]:
    """The entry a run of *agent_row* launches with, fixing *task*'s entry where this is its first
    run of the role (staged on *session*, committed with the run). None when the pool is empty and
    the agent has no runner: the caller refuses the start as it always has (FR-1)."""
    pool: List[AgentPoolEntry] = await agent_pool.pool_rows(session, agent_row.id)
    held = {(entry.runner_id, entry.effort) for entry in pool}
    default_row = next((entry for entry in pool if entry.is_default), None)
    default: Dict[str, Any]
    if default_row is not None:
        default = {"runner_id": default_row.runner_id, "effort": default_row.effort}
    elif agent_row.runner_id:
        # An agent bound before its pool was seeded, or by a door that writes `runner_id` alone:
        # the runner it names is its default, as before pools.
        default = {"runner_id": agent_row.runner_id, "effort": None}
        held.add((agent_row.runner_id, None))
    else:
        return None

    role = role_for(agent_row.name, task, review=review)
    if role is None or task is None:
        return LaunchEntry(default["runner_id"], default["effort"], "default")

    column = f"{role}_entry"
    kept = getattr(task, column, None)
    chosen: Optional[Dict[str, Any]] = None
    source = "default"
    if isinstance(kept, dict) and kept.get("agent") == agent_row.name and _entry_dict(kept):
        chosen, source = _entry_dict(kept), "fixed"
    else:
        build = await builds.build_of_task(session, task)
        picked = builds.chosen_entry(build, task, role)
        # The Build choice was checked against the pool of the agent the task resolved to then; a
        # task since handed to another agent takes that agent's default.
        if role == CHECKER:
            resolved = builds.checker_of(build, task)
            own = (resolved[0] if resolved is not None else task.checker) or None
        else:
            own = task.builder or None
        if picked is not None and (own is None or own == agent_row.name):
            chosen, source = picked, "build"
        else:
            recommended = await _recommended(session, task, role)
            if (
                recommended is not None
                and (recommended["runner_id"], recommended["effort"]) in held
            ):
                chosen, source = recommended, "recommendation"

    events: List[Dict[str, Any]] = []
    if chosen is None:
        chosen, source = dict(default), "default"
    elif (chosen["runner_id"], chosen["effort"]) not in held:
        started_on = await _conversation_runner(session, conversation_id)
        if (
            source == "fixed"
            and started_on == chosen["runner_id"]
            and await session.get(Runner, chosen["runner_id"]) is not None
        ):
            source = "conversation"
        else:
            dropped = await _label(session, chosen)
            instead = await _label(session, default)
            events.append(
                {
                    "name": FALLBACK_EVENT,
                    "attributes": {
                        "aw.pool.dropped_runner_id": chosen["runner_id"],
                        "aw.pool.dropped_effort": chosen["effort"],
                        "aw.pool.default_runner_id": default["runner_id"],
                        "aw.message": (
                            f"{dropped}, chosen for this task's {role}, was removed from "
                            f"{agent_row.name}'s pool; this run launches on the default, {instead}."
                        ),
                    },
                }
            )
            chosen, source = dict(default), "fallback"

    if source != "conversation":
        setattr(
            task,
            column,
            {"agent": agent_row.name, "runner_id": chosen["runner_id"], "effort": chosen["effort"]},
        )
    return LaunchEntry(chosen["runner_id"], chosen["effort"], source, role=role, events=events)


def entry_overrides(overrides: Dict[str, Any], entry: LaunchEntry, *, chat: bool) -> Dict[str, Any]:
    """The conversation overrides a run launches with, given its *entry* (FR-10).

    A chat keeps its own model and effort over the entry, as a composer's choice always has (FR-9
    bounds those choices to the pool). Every other run — a task's, a review, a job firing, a peer
    message — launches with the entry's model and effort only, whatever its conversation stores.
    The entry's effort fills an override left unset.
    """
    out = dict(overrides)
    if not chat or entry.role is not None:
        for key in ENTRY_OVERRIDE_KEYS:
            out.pop(key, None)
    if entry.effort and "effort" not in out:
        out["effort"] = entry.effort
    return out
