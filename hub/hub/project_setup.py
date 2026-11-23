"""What a project still needs before it can do its work (`a-project-says-what-it-still-needs`).

Four items, each shown only while it is not met (FR-1): the project's folder is found where it was
bound; that folder is a git repository; the project has an agent that is not archived; and every
agent that is not archived can run (one item per agent that cannot). All of them are read from the
project's state now, never from anything recorded when it was created (FR-5), so a project created
before this module reads the same as a new one.

Only the repository item can be dismissed (FR-3): a scratch folder may deliberately have no git,
but without a folder, or an agent that runs, nothing works at all. A dismissal is a
`SetupDismissal` row; showing the item again deletes it.

The agent item is the `profiles` offer (`profiles-threads-and-builds-everywhere` D6, FR-8): shown
while the project has no open agent, until the operator uses it or dismisses it. Using it
(`create_offered_profiles`) records the same row a dismissal does, so it does not come back when
those profiles are archived.

A fifth item, `specification`, is shown while the project's corpus is empty
(`a-project-with-no-specs-is-offered-a-start`, FR-3; `corpus_start.corpus_state`). It opens the
start offer, can be dismissed like the repository item, and is gone without being dismissed once
the corpus holds any document.

`SETUP_CHANGED` is broadcast where an item can change and no event the app already re-reads the
projects on is sent (FR-6): a model bound to an agent, and a dismissal made or undone.
"""

from __future__ import annotations

import asyncio
import contextlib
import subprocess
from typing import Dict, List, Literal, Optional, Sequence, Tuple

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import blocking, project_workspace, spec_documents, task_integration
from .db.models import Agent, Project, Runner, SetupDismissal, SpecDocument
from .launchability import probe_agent
from .runner_provider import runner_probe_config

SetupKey = Literal["folder", "repository", "profiles", "can-run", "specification"]

#: The items an operator may dismiss. The rest cannot be waved away (FR-3).
DISMISSABLE = frozenset({"repository", "profiles", "specification"})

#: The event the app re-reads a project's set-up items on.
SETUP_CHANGED = "project_setup_changed"


class SetupItem(BaseModel):
    """One thing the project still needs. `id` is the key, except a can-run item's, which is
    `can-run-<agent>`, one per agent that cannot run."""

    id: str
    key: SetupKey
    dismissable: bool = False
    # A can-run item's agent, and why it cannot run: `not_installed` (its model's coding agent is
    # not on the Hub's PATH), `not_logged_in`, `no_model` (no model chosen), or `cannot_run` for any
    # other refusal, with the probe's own sentence in `detail`.
    agent: Optional[str] = None
    provider: Optional[str] = None
    reason: Optional[str] = None
    detail: Optional[str] = None


class ProjectSetup(BaseModel):
    """The items still shown, and the ones the operator dismissed while unmet."""

    items: List[SetupItem] = []
    dismissed: List[SetupItem] = []


async def dismissed_items(session: AsyncSession, project_id: str) -> set[str]:
    rows = await session.execute(
        select(SetupDismissal.item).where(SetupDismissal.project_id == project_id)
    )
    return set(rows.scalars().all())


def _can_run_item(agent: Agent, runner: Optional[Runner], verdict: Optional[dict]) -> SetupItem:
    item_id = f"can-run-{agent.name}"
    if runner is None or verdict is None:
        return SetupItem(
            id=item_id,
            key="can-run",
            agent=agent.name,
            reason="no_model",
            detail="No model is chosen for this agent.",
        )
    if not verdict.get("present"):
        reason = "not_installed"
    elif not verdict.get("authorized"):
        reason = "not_logged_in"
    else:
        reason = "cannot_run"
    return SetupItem(
        id=item_id,
        key="can-run",
        agent=agent.name,
        provider=runner.cli,
        reason=reason,
        detail=verdict.get("reason"),
    )


def _is_repository(root) -> bool:  # noqa: ANN001 -- a workspace root
    """`is_repository`, False where git cannot be run at all (the Hub's Docker image ships none):
    a listing must not fail for it, and without git the Hub cannot use the repository either."""
    try:
        return task_integration.is_repository(root)
    except (OSError, subprocess.SubprocessError):
        return False


def _disk_facts(
    workspace: project_workspace.ProjectWorkspace, ask_corpus: bool
) -> Tuple[bool, bool]:
    """Whether *workspace*'s folder is a repository, and (when *ask_corpus*) whether its `spec/`
    holds no document. Runs on the blocking pool: both read the project's filesystem."""
    return _is_repository(workspace.root), ask_corpus and not spec_documents.discover(workspace)[0]


async def project_setups(
    session: AsyncSession,
    projects: Sequence[Project],
    *,
    verdicts: Optional[Dict[str, dict]] = None,
) -> Dict[str, ProjectSetup]:
    """Each project's set-up items, worked out from its state now, keyed by project id.

    Batched for the projects list (BWYCS-8): over ~200 projects, a `git rev-parse` per folder run
    one after another took ~19 s, and ten queries per project ~4 s more. The database is read once
    per kind of row, and the folders are asked concurrently on the blocking pool.

    `verdicts` is a launchability cache keyed by runner id that a caller may share between calls;
    each runner is probed once per call either way.
    """
    ids = [project.id for project in projects]
    workspaces: Dict[str, project_workspace.ProjectWorkspace] = {}
    for project in projects:
        with contextlib.suppress(project_workspace.ProjectWorkspaceError):
            workspaces[project.id] = await project_workspace.resolve_project_workspace(
                session, project.id
            )
    # Asked only of a folder that is found: an empty corpus in a missing folder is not news.
    found = {
        project.id: workspaces[project.id]
        for project in projects
        if project.id in workspaces and project.directory_state == "available"
    }
    # A project with any document row (archived ones count) is not empty, whatever is on disk;
    # one with none is empty exactly when discovery finds no file (`corpus_start.corpus_state`).
    with_documents = set(
        (
            await session.execute(
                select(SpecDocument.project_id).where(SpecDocument.project_id.in_(ids)).distinct()
            )
        )
        .scalars()
        .all()
    )
    agents_of: Dict[str, List[Agent]] = {project_id: [] for project_id in ids}
    for agent in (
        await session.execute(
            select(Agent)
            .where(Agent.project_id.in_(ids), Agent.lifecycle == "open")
            .order_by(Agent.name)
        )
    ).scalars():
        agents_of[agent.project_id].append(agent)
    runner_ids = {agent.runner_id for agents in agents_of.values() for agent in agents}
    runners = {
        runner.id: runner
        for runner in (
            await session.execute(select(Runner).where(Runner.id.in_(runner_ids - {None})))
        ).scalars()
    }
    dismissed_of: Dict[str, set[str]] = {project_id: set() for project_id in ids}
    for project_id, item in await session.execute(
        select(SetupDismissal.project_id, SetupDismissal.item).where(
            SetupDismissal.project_id.in_(ids)
        )
    ):
        dismissed_of[project_id].add(item)
    # Half the blocking pool at most, so a cold list (no folder remembered yet) leaves threads for
    # the turn starts and merges that share it.
    lanes = asyncio.Semaphore(max(1, blocking.MAX_WORKERS // 2))

    async def ask(project_id: str, workspace: project_workspace.ProjectWorkspace):
        async with lanes:
            return await blocking.run(_disk_facts, workspace, project_id not in with_documents)

    answers = await asyncio.gather(*(ask(pid, ws) for pid, ws in found.items()))
    disk = dict(zip(found, answers, strict=True))

    cache = verdicts if verdicts is not None else {}
    setups: Dict[str, ProjectSetup] = {}
    for project in projects:
        candidates: List[SetupItem] = []
        repository, corpus_empty = disk.get(project.id, (False, False))
        if project.id not in found:
            candidates.append(SetupItem(id="folder", key="folder"))
        # A folder that is not found cannot be asked whether it is a repository: the folder item
        # is what the operator resolves first, and the repository item follows if it still applies.
        elif not repository:
            candidates.append(SetupItem(id="repository", key="repository", dismissable=True))

        agents = agents_of[project.id]
        if not agents:
            candidates.append(SetupItem(id="profiles", key="profiles", dismissable=True))
        for agent in agents:
            runner = runners.get(agent.runner_id) if agent.runner_id else None
            if runner is not None and runner.project_id != project.id:
                runner = None
            verdict = None
            if runner is not None:
                if runner.id not in cache:
                    cache[runner.id] = dict(probe_agent(agent.name, runner_probe_config(runner)))
                verdict = cache[runner.id]
                if verdict.get("runnable"):
                    continue
            candidates.append(_can_run_item(agent, runner, verdict))

        if corpus_empty:
            candidates.append(SetupItem(id="specification", key="specification", dismissable=True))

        dismissed = dismissed_of[project.id]
        setups[project.id] = ProjectSetup(
            items=[item for item in candidates if item.id not in dismissed],
            dismissed=[item for item in candidates if item.id in dismissed],
        )
    return setups


async def project_setup(
    session: AsyncSession,
    project: Project,
    *,
    verdicts: Optional[Dict[str, dict]] = None,
) -> ProjectSetup:
    """The project's set-up items, worked out from its state now (`project_setups` of one)."""
    return (await project_setups(session, [project], verdicts=verdicts))[project.id]


async def dismiss(session: AsyncSession, project_id: str, item: str) -> None:
    """Record *item* dismissed for the project. Raises ValueError for an item that cannot be."""
    if item not in DISMISSABLE:
        raise ValueError(item)
    if await session.get(SetupDismissal, (project_id, item)) is None:
        session.add(SetupDismissal(project_id=project_id, item=item))
    await session.commit()


async def show_again(session: AsyncSession, project_id: str, item: str) -> None:
    """Undo a dismissal. Raises ValueError for an item that cannot be dismissed."""
    if item not in DISMISSABLE:
        raise ValueError(item)
    await session.execute(
        delete(SetupDismissal).where(
            SetupDismissal.project_id == project_id, SetupDismissal.item == item
        )
    )
    await session.commit()


async def publish_setup_changed(project_id: str) -> None:
    """Tell the app the project's set-up items may have changed, so it re-reads them (FR-6).

    Sent beside the event each change already sends, so the app has one event to follow whatever
    resolved the item. Never raises: the change it reports is already committed.
    """
    from .sse import sse_manager

    with contextlib.suppress(Exception):
        await sse_manager.broadcast(project_id, SETUP_CHANGED, {"id": project_id})
