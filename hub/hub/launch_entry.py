"""Which pool entry a run launches with (`a-profile-runs-each-task-on-a-runner-and-model-chosen-from-
its-pool`, FR-7, FR-8, FR-10, FR-13).

Every run starts on an entry of its profile's pool: a runner plus an optional effort. Which one:

- A task's **builder** run (the turn is bound to a task the agent builds) and a task's **review**
  run (the agent is staffed to check it) use the task's entry for that role. The first run of each
  fixes it, from the operator's Build choice for the task, else the document's recommendation when
  the pool holds it, else the pool's default; every later run of that role by the same agent uses
  the fixed entry, re-reviews after a send-back included (FR-7).
- An operator's chat turn uses the runner the chat chose, which may be any catalog model, in the
  pool or not (`a-profile-s-pool-and-a-new-chat-can-use-any-model-of-any-provider`, FR-10).
- Every other run — a job firing, a peer message, a mend turn, a chat that chose nothing — uses
  the pool's default; a chat's choice never reaches it (FR-7).

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
from .runner_provider import has_provider

logger = logging.getLogger(__name__)

BUILDER = "builder"
CHECKER = "checker"

#: The conversation override keys a pool entry decides (FR-10): which model, and how hard it
#: thinks. A runner is never an override; the posture (`permission_mode`) is not the pool's.
ENTRY_OVERRIDE_KEYS = frozenset({"model", "effort"})

#: Trace event naming a chosen entry that left the pool (FR-8).
FALLBACK_EVENT = "pool_entry_removed"

#: The conversation override naming the runner of the pool entry a chat chose (FR-9). Stored with
#: the entry's `effort` beside it; never passed to a CLI as a control.
CHAT_RUNNER_KEY = "runner_id"

#: The key naming which catalog provider a chat's `model` is (FR-10); read, never stored.
CHAT_PROVIDER_KEY = "provider"

#: The keys a chat names its runner by; its effort is its own and never moves it (FR-6).
_CHAT_RUNNER_KEYS = frozenset({CHAT_RUNNER_KEY, CHAT_PROVIDER_KEY, "model"})


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


async def _pool(
    session: AsyncSession, agent_row: Agent
) -> "tuple[set[tuple[str, Optional[str]]], Optional[Dict[str, Any]]]":
    """The (runner, effort) pairs *agent_row* may run on, and its default; no default when the
    pool is empty and no runner is bound."""
    pool: List[AgentPoolEntry] = await agent_pool.pool_rows(session, agent_row.id)
    held = {(entry.runner_id, entry.effort) for entry in pool}
    default_row = next((entry for entry in pool if entry.is_default), None)
    if default_row is not None:
        return held, {"runner_id": default_row.runner_id, "effort": default_row.effort}
    if agent_row.runner_id:
        # An agent bound before its pool was seeded, or by a door that writes `runner_id` alone:
        # the runner it names is its default, as before pools.
        held.add((agent_row.runner_id, None))
        return held, {"runner_id": agent_row.runner_id, "effort": None}
    return held, None


async def resolve(
    session: AsyncSession,
    agent_row: Agent,
    *,
    task: Optional[Task] = None,
    review: bool = False,
    conversation_id: Optional[str] = None,
    chat_runner_id: Optional[str] = None,
    fix: bool = True,
    role: Optional[str] = None,
) -> Optional[LaunchEntry]:
    """The entry a run of *agent_row* launches with, fixing *task*'s entry where this is its first
    run of the role (staged on *session*, committed with the run). None when the pool is empty and
    the agent has no runner: the caller refuses the start as it always has (FR-1).

    *chat_runner_id* is the runner a chat chose from the pool (FR-9, its conversation's
    `runner_id` override); a run that is not a task's starts on it while the pool still holds it.
    With *fix* false nothing is staged: the scheduler asks which CLI a turn would start on before
    it decides whether a hold stops it (FR-11). *role* asks as that role's run whoever holds the
    task now: a flow asks which CLI an agent it may give the task to would build it on."""
    held, default = await _pool(session, agent_row)
    if default is None:
        return None

    if role is None:
        role = role_for(agent_row.name, task, review=review)
    if role is None or task is None:
        if chat_runner_id and await session.get(Runner, chat_runner_id) is not None:
            # A chat runs on the runner it chose, in the pool or not (FR-10 of `a-profile-s-pool-
            # and-a-new-chat-can-use-any-model-of-any-provider`); its effort travels in its
            # overrides (`entry_overrides`). Only an operator's chat turn passes one (FR-7).
            return LaunchEntry(chat_runner_id, None, "chat")
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

    if source != "conversation" and fix:
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
    # The chat's runner choice is the entry itself (`resolve`'s *chat_runner_id*), never a control.
    out.pop(CHAT_RUNNER_KEY, None)
    if not chat or entry.role is not None:
        for key in ENTRY_OVERRIDE_KEYS:
            out.pop(key, None)
    if entry.effort and "effort" not in out:
        out["effort"] = entry.effort
    return out


def chat_runner(conversation: Any, *, initiator: Optional[str]) -> Optional[str]:
    """The runner a chat chose from the pool, for a turn the operator started (FR-9); None for
    every other run, which launches by start precedence or on the default (FR-10)."""
    if initiator != "operator" or conversation is None:
        return None
    value = (conversation.runtime_overrides or {}).get(CHAT_RUNNER_KEY)
    return str(value) if value else None


class ChatChoiceRefusalError(Exception):
    """A conversation override naming no entry of the profile's pool (FR-9), with the sentence."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def started_cli(
    session: AsyncSession, conversation_id: Optional[str], agent_row: Agent
) -> Optional[str]:
    """The CLI a conversation started on, or None before its first turn (FR-9).

    Read from its latest run's recorded runner; a conversation whose runs predate that record ran
    on the agent's runner, its default.
    """
    if not conversation_id:
        return None
    has_run = (
        await session.execute(select(Run.id).where(Run.conversation_id == conversation_id).limit(1))
    ).scalar()
    if has_run is None:
        return None
    runner_id = await _conversation_runner(session, conversation_id) or agent_row.runner_id
    runner = await session.get(Runner, runner_id) if runner_id else None
    return runner.cli if runner is not None else None


def _same_model(cli: str, named: str, runner_model: Optional[str]) -> bool:
    if not runner_model:
        return False
    if named == runner_model:
        return True
    from .model_catalog import get_provider

    provider = get_provider(cli)
    if provider is None:
        return False
    left, right = provider.model(named), provider.model(runner_model)
    return left is not None and right is not None and left.id == right.id


async def bound_chat_overrides(
    session: AsyncSession,
    agent_row: Agent,
    overrides: Dict[str, Any],
    *,
    stored: Dict[str, Any],
    conversation_id: Optional[str],
) -> "tuple[Dict[str, Any], Optional[Runner]]":
    """*overrides* as a chat's choice (`a-profile-s-pool-and-a-new-chat-can-use-any-model-of-any-
    provider`, FR-10, FR-11), and the runner the chat's turn launches on.

    A chat names any catalog model: by `provider` and `model` (the composer), by `model` alone (as
    a composer did before pools; read on the CLI the chat is on first), or by a runner of the
    project (`runner_id`). The pool is never changed: a model on a runner the chat is on or the
    pool holds launches on that runner, any other on the project's plain runner for it, reused or
    created (`agent_pool.plain_runner_for`). Once the conversation has a turn, only a model of the
    CLI it started on is accepted. The effort is the chat's own and never decides the runner.

    A choice on another runner than the default's is answered by its runner, without `model`: the
    runner decides the model. One on the default's runner is answered as sent, so the chat follows
    the default, as a chat followed a rebound agent before pools. Overrides naming none of these,
    or re-sending the conversation's stored ones unchanged, are left as they are. `provider` is
    never stored. Raises `ChatChoiceRefusalError`.
    """
    as_sent = {key: value for key, value in overrides.items() if key != CHAT_PROVIDER_KEY}
    _, default = await _pool(session, agent_row)
    if default is None:
        return as_sent, None
    default_runner = await session.get(Runner, default["runner_id"])
    stored_runner = stored.get(CHAT_RUNNER_KEY)
    current = await _project_runner(session, agent_row, stored_runner) if stored_runner else None
    current = current or default_runner
    chosen_keys = {key: overrides[key] for key in _CHAT_RUNNER_KEYS if key in overrides}
    stored_keys = {key: stored[key] for key in _CHAT_RUNNER_KEYS if key in stored}
    if current is None or not chosen_keys or chosen_keys == stored_keys:
        # Nothing about the runner is being chosen: the composer sends the stored overrides back
        # with every message, and a stored choice keeps working where it is stored. The effort
        # alone never moves the chat off its runner (FR-6).
        return as_sent, current

    started = await started_cli(session, conversation_id, agent_row)
    runner, label = await _chosen_runner(
        session, agent_row, overrides, stored=stored, current=current, started=started
    )
    if started is not None and runner.cli != started:
        raise ChatChoiceRefusalError(
            f"This conversation runs on {agent_pool.cli_label(started)}, and {label} runs on "
            f"{agent_pool.cli_label(runner.cli)}: start a new chat to use it."
        )
    accepted = {key: value for key, value in overrides.items() if key not in _CHAT_RUNNER_KEYS}
    if default_runner is not None and runner.id == default_runner.id:
        # A choice on the default's runner is stored as a chat's choice always was, so the
        # conversation follows the default, as it did before pools when the agent was rebound.
        if "model" in overrides and CHAT_PROVIDER_KEY not in overrides:
            accepted["model"] = overrides["model"]
        return accepted, runner
    accepted[CHAT_RUNNER_KEY] = runner.id
    return accepted, runner


async def _project_runner(
    session: AsyncSession, agent_row: Agent, runner_id: object
) -> Optional[Runner]:
    row = await session.get(Runner, str(runner_id))
    return row if row is not None and row.project_id == agent_row.project_id else None


async def _chosen_runner(
    session: AsyncSession,
    agent_row: Agent,
    overrides: Dict[str, Any],
    *,
    stored: Dict[str, Any],
    current: Runner,
    started: Optional[str],
) -> "tuple[Runner, str]":
    """The runner a chat's choice names, and the choice as a refusal names it (FR-10)."""
    from .model_catalog import get_provider, providers, undeclared_model_reason

    if CHAT_RUNNER_KEY in overrides:
        runner_id = overrides[CHAT_RUNNER_KEY]
        row = await _project_runner(session, agent_row, runner_id)
        if row is None:
            raise ChatChoiceRefusalError(f"There is no runner {runner_id!r} in this project.")
        return row, agent_pool.model_label(row)
    if "model" not in overrides:
        return current, agent_pool.model_label(current)

    model = str(overrides["model"])
    provider = overrides.get(CHAT_PROVIDER_KEY)
    if provider is None and model == stored.get("model"):
        # A stored model keeps working where it is stored, also once the catalog dropped it.
        return current, model
    if provider is not None:
        clis = [str(provider)]
    else:
        # The CLI the chat is on first, so an id two catalogs share stays on it.
        clis = []
        for cli in [started, current.cli, *(entry.provider for entry in providers())]:
            if cli and cli not in clis:
                clis.append(cli)
    found: Optional["tuple[str, str]"] = None
    for cli in clis:
        entry = get_provider(cli)
        declared = entry.model(model) if entry is not None else None
        if declared is not None:
            found = (cli, declared.label)
            break
    if found is None:
        raise ChatChoiceRefusalError(undeclared_model_reason(clis[0], model))
    cli, label = found
    # A runner the chat is on, or the pool holds, for this model first: no runner is made for it.
    candidates = [current]
    for pool_entry in await agent_pool.pool_rows(session, agent_row.id):
        row = await session.get(Runner, pool_entry.runner_id)
        if row is not None and row not in candidates:
            candidates.append(row)
    for row in candidates:
        if (
            row.cli == cli
            and not has_provider(row.provider_config)
            and _same_model(cli, model, row.model)
        ):
            return row, label
    try:
        runner = await agent_pool.plain_runner_for(session, agent_row.project_id, cli, model)
    except agent_pool.PoolRefusalError as refusal:
        raise ChatChoiceRefusalError(refusal.message) from refusal
    return runner, label
