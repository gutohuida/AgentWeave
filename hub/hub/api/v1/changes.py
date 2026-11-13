"""The side panel's Changes tab: what a conversation's agent changed, read from its branch.

Read-only. Nothing here provisions a checkout, stages or commits: an absent checkout is an answer
(`state="no_checkout"`), not something to create. All git work runs in a thread, off the event loop.

Which branch is shown follows the conversation's most recent turn: when that turn ran in a task's
checkout, the task's branch (and the task is named); otherwise the agent's own branch. "Last turn"
is that turn's auto-snapshot commit, "Since main" is `base...branch`, and while a turn of the
conversation runs, `working_now` names what its checkout holds uncommitted.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import changes_view, project_workspace, worktrees
from ...auth import get_project
from ...conversations import get_conversation_by_id
from ...db.engine import get_session
from ...db.models import Project, Run, Task
from ...launchability import get_agent_config

router = APIRouter(prefix="/conversations", tags=["conversations"])

State = Literal["ok", "empty", "no_checkout", "unreadable"]


class ChangedFileInfo(BaseModel):
    path: str
    status: str
    added: int
    removed: int
    binary: bool = False
    old_path: Optional[str] = None


class ChangesTask(BaseModel):
    id: str
    readable_id: Optional[str] = None
    title: Optional[str] = None


class ChangesResponse(BaseModel):
    state: State
    #: Plain words for `no_checkout` / `unreadable`; never an error code.
    message: Optional[str] = None
    agent: str
    branch: Optional[str] = None
    base: Optional[str] = None
    task: Optional[ChangesTask] = None
    #: What the conversation's most recent finished turn committed.
    turn: List[ChangedFileInfo] = []
    #: Everything on the branch that the base does not have.
    since_base: List[ChangedFileInfo] = []
    running: bool = False
    #: Files changed in the checkout and not yet committed, while a turn runs.
    working_now: List[str] = []


class PatchResponse(BaseModel):
    path: str
    patch: str
    binary: bool
    truncated: bool
    total_lines: int


def _info(files: List[changes_view.ChangedFile]) -> List[ChangedFileInfo]:
    return [
        ChangedFileInfo(
            path=f.path,
            status=f.status,
            added=f.added,
            removed=f.removed,
            binary=f.binary,
            old_path=f.old_path,
        )
        for f in files
    ]


async def _load(project_id: str, conversation_id: str, session: AsyncSession):
    conversation = await get_conversation_by_id(session, conversation_id)
    if conversation is None or conversation.project_id != project_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    runs = (
        (
            await session.execute(
                select(Run)
                .where(Run.project_id == project_id, Run.conversation_id == conversation_id)
                .order_by(Run.started_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return conversation, workspace.root, list(runs)


def _task_of(run: Optional[Run]) -> Optional[str]:
    """The task whose checkout *run* executed in, or None. Read off the directory, as
    `snapshot_worktree` does, so the branch cannot disagree with the checkout."""
    if run is None or not run.workspace_dir:
        return None
    return worktrees.task_id_of(Path(run.workspace_dir))


async def _resolve_target(
    session: AsyncSession, project_id: str, conversation, repo_root: Path, runs: List[Run]
):
    """Returns (branch, task_row, state, message). `branch` is None when there is nothing to read."""
    if not worktrees.is_git_repo(repo_root):
        return (
            None,
            None,
            "no_checkout",
            "This project is not a git repository, so the agent has no checkout of its own.",
        )
    latest = runs[0] if runs else None
    task_id = _task_of(latest)
    if task_id is not None:
        task = await session.get(Task, task_id)
        return worktrees.task_branch_name(task_id), task or task_id, None, None
    config = await get_agent_config(project_id, conversation.agent, session)
    if not worktrees.is_writing_agent(config):
        return (
            None,
            None,
            "no_checkout",
            f"{conversation.agent} has no checkout of its own: it is read-only and works in the project directory.",
        )
    try:
        return worktrees.branch_name(conversation.agent), None, None, None
    except ValueError:
        return None, None, "unreadable", f"{conversation.agent}'s branch cannot be read."


def _read(
    repo_root: Path,
    branch: str,
    base_name: Optional[str],
    sha: Optional[str],
    checkout: Optional[Path],
):
    """All the blocking git reads for one answer, in one thread hop."""
    if not changes_view.branch_exists(repo_root, branch):
        return None
    base = changes_view.resolve_base(repo_root, base_name)
    turn = changes_view.turn_files(repo_root, sha) if sha else []
    since = changes_view.branch_files(repo_root, base, branch) if base else []
    working: List[str] = []
    if checkout is not None:
        working = changes_view.uncommitted_paths(checkout)
    return base, turn, since, working


@router.get("/{conversation_id}/changes", response_model=ChangesResponse)
async def get_changes(
    conversation_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> ChangesResponse:
    project_id, _ = project
    conversation, repo_root, runs = await _load(project_id, conversation_id, session)
    agent = conversation.agent
    branch, task, state, message = await _resolve_target(
        session, project_id, conversation, repo_root, runs
    )
    if branch is None:
        return ChangesResponse(state=state, message=message, agent=agent)

    task_info = None
    if isinstance(task, Task):
        task_info = ChangesTask(id=task.id, readable_id=task.readable_id, title=task.title)
    elif isinstance(task, str):
        task_info = ChangesTask(id=task)

    running_run = next((r for r in runs if r.status == "running"), None)
    finished = next((r for r in runs if r.status != "running"), None)
    sha = finished.snapshot_commit_sha if finished is not None else None
    checkout: Optional[Path] = None
    if running_run is not None and running_run.workspace_dir:
        candidate = Path(running_run.workspace_dir)
        # Never the project's own checkout: its dirty files are the operator's, not this turn's.
        if (candidate / ".git").is_file() and candidate.is_dir():
            checkout = candidate

    project_row = await session.get(Project, project_id)
    main_branch = project_row.main_branch if project_row is not None else None
    try:
        read = await asyncio.to_thread(_read, repo_root, branch, main_branch, sha, checkout)
    except worktrees.GitCommandError:
        return ChangesResponse(
            state="unreadable",
            message=f"{agent}'s branch {branch} could not be read.",
            agent=agent,
            branch=branch,
            task=task_info,
        )
    if read is None:
        return ChangesResponse(
            state="no_checkout",
            message=f"{agent} has no checkout yet: {branch} has not been created.",
            agent=agent,
            branch=branch,
            task=task_info,
        )
    base, turn, since, working = read
    return ChangesResponse(
        state="ok" if (turn or since or working) else "empty",
        agent=agent,
        branch=branch,
        base=base,
        task=task_info,
        turn=_info(turn),
        since_base=_info(since),
        running=running_run is not None,
        working_now=working,
    )


@router.get("/{conversation_id}/changes/patch", response_model=PatchResponse)
async def get_change_patch(
    conversation_id: str,
    path: str = Query(..., min_length=1, max_length=4096),
    scope: Literal["turn", "branch"] = Query("turn"),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> PatchResponse:
    """One changed file's diff: binary files have no body; a very long diff is cut to its start."""
    project_id, _ = project
    if path.startswith("-") or "\0" in path:
        raise HTTPException(status_code=400, detail="Invalid path")
    conversation, repo_root, runs = await _load(project_id, conversation_id, session)
    branch, _task, state, message = await _resolve_target(
        session, project_id, conversation, repo_root, runs
    )
    if branch is None:
        raise HTTPException(status_code=404, detail=message or "No checkout")
    finished = next((r for r in runs if r.status != "running"), None)
    sha = finished.snapshot_commit_sha if finished is not None else None
    if scope == "turn" and not sha:
        raise HTTPException(status_code=404, detail="The last turn changed no files")
    project_row = await session.get(Project, project_id)
    main_branch = project_row.main_branch if project_row is not None else None

    def _patch():
        base = changes_view.resolve_base(repo_root, main_branch)
        return changes_view.file_patch(
            repo_root,
            path=path,
            sha=sha if scope == "turn" else None,
            base=base,
            branch=branch,
        )

    try:
        result = await asyncio.to_thread(_patch)
    except worktrees.GitCommandError as exc:
        raise HTTPException(status_code=404, detail="That diff cannot be read") from exc
    return PatchResponse(
        path=path,
        patch=result.patch,
        binary=result.binary,
        truncated=result.truncated,
        total_lines=result.total_lines,
    )
