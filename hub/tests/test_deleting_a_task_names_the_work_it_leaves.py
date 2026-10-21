"""F828: deleting a task (or a document) removed its rows and left its checkout and branch, with
the agent's unmerged commit, listed under a task id that no longer exists -- and said nothing.

Against a real disposable git repository under `tmp_path`: a checkout whose branch holds nothing
unmerged goes with the task; one that holds work is kept, and the answer names the branch and how
many commits are on it.
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import EventLog, Task
from hub.worktrees import ensure_task_worktree

from .test_a_finished_change_is_folded_into_its_capability import BASE, CHANGE, _approved_change
from .test_task_worktrees import _git, _init_repo

TASKS = "/api/v1/projects/proj-test/tasks"


def _commit_in(checkout: Path, name: str) -> None:
    (checkout / name).write_text("work\n")
    _git(checkout, "add", "-A")
    _git(checkout, "commit", "-q", "-m", f"work on {name}")


def _branches(repo: Path, task_id: str) -> str:
    return _git(repo, "branch", "--list", worktrees.task_branch_name(task_id)).stdout.strip()


async def _events(event_type: str):
    async with async_session_factory() as session:
        rows = await session.execute(select(EventLog).where(EventLog.event_type == event_type))
        return [row.data for row in rows.scalars()]


async def _task(app, auth_headers) -> str:
    created = await app.post(TASKS, json={"title": "Built something"}, headers=auth_headers)
    return created.json()["id"]


@pytest.mark.asyncio
async def test_a_deleted_task_with_nothing_unmerged_takes_its_checkout_and_branch(
    app, auth_headers, tmp_path
):
    repo = _init_repo(tmp_path)
    task_id = await _task(app, auth_headers)
    checkout = ensure_task_worktree(repo, task_id, "main", ())
    assert checkout.exists()

    response = await app.delete(f"{TASKS}/{task_id}", headers=auth_headers)

    assert response.status_code == 204, response.text
    assert not checkout.exists()
    assert _branches(repo, task_id) == ""
    assert await _events("task_checkout_kept") == []


@pytest.mark.asyncio
async def test_a_deleted_task_with_unmerged_commits_keeps_them_and_says_so(
    app, auth_headers, tmp_path
):
    repo = _init_repo(tmp_path)
    task_id = await _task(app, auth_headers)
    checkout = ensure_task_worktree(repo, task_id, "main", ())
    _commit_in(checkout, "a.txt")
    _commit_in(checkout, "b.txt")

    response = await app.delete(f"{TASKS}/{task_id}", headers=auth_headers)

    assert response.status_code == 204, response.text
    assert checkout.exists()
    assert _branches(repo, task_id) != ""
    kept = [data for data in await _events("task_checkout_kept") if data["task_id"] == task_id]
    assert len(kept) == 1
    assert kept[0]["branch"] == worktrees.task_branch_name(task_id)
    assert kept[0]["unmerged_commits"] == 2


@pytest.mark.asyncio
async def test_a_deleted_task_with_uncommitted_edits_is_kept_too(app, auth_headers, tmp_path):
    repo = _init_repo(tmp_path)
    task_id = await _task(app, auth_headers)
    checkout = ensure_task_worktree(repo, task_id, "main", ())
    (checkout / "scratch.txt").write_text("not yet committed\n")

    response = await app.delete(f"{TASKS}/{task_id}", headers=auth_headers)

    assert response.status_code == 204, response.text
    assert (checkout / "scratch.txt").exists()
    kept = [data for data in await _events("task_checkout_kept") if data["task_id"] == task_id]
    assert len(kept) == 1 and kept[0]["uncommitted"] is True


@pytest.mark.asyncio
async def test_deleting_a_document_names_the_work_its_tasks_left(app, auth_headers, tmp_path):
    await _approved_change(app, auth_headers)
    repo = _init_repo(tmp_path)
    async with async_session_factory() as session:
        task_ids = (await session.execute(select(Task.id))).scalars().all()
    assert task_ids
    kept_id, clean_id = task_ids[0], task_ids[-1]
    kept = ensure_task_worktree(repo, kept_id, "main", ())
    _commit_in(kept, "work.txt")
    if clean_id != kept_id:
        ensure_task_worktree(repo, clean_id, "main", ())

    response = await app.delete(f"{BASE}/documents/{CHANGE}", headers=auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kept_work"] == [
        {
            "task_id": kept_id,
            "branch": worktrees.task_branch_name(kept_id),
            "unmerged_commits": 1,
            "uncommitted": False,
        }
    ]
    assert kept.exists()
    if clean_id != kept_id:
        assert not worktrees.task_worktree_path(repo, clean_id).exists()
        assert _branches(repo, clean_id) == ""
