"""Tests for POST /api/v1/projects/proj-test/session/sync's agent-roster reconciliation, including task
5.4's worktree-release wiring: an agent that drops out of the synced roster (removed
from agentweave.yml) has its isolated worktree released, with unmerged work reported
via a persisted + broadcast `worktree_released` event rather than discarded silently.
"""

import json
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import Agent
from hub.sse import sse_manager

# Named import, for the reason `test_task_worktrees.py` states: conftest's autouse
# `_no_real_worktree_provision` patches the module *attribute* to a no-op, and a name bound here
# at collection time is a separate reference to the real function. `ensure_worktree` above is not
# stubbed, so it stays a module lookup.
from hub.worktrees import ensure_task_worktree


def _drain(queue):
    events = []
    while True:
        try:
            item = queue.get_nowait()
        except Exception:  # asyncio.QueueEmpty
            break
        events.append((item.event, json.loads(item.data)))
    return events


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "f.txt").write_text("base\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


@pytest.mark.asyncio
async def test_sync_creates_and_removes_agents(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={
            "data": {"agents": {"keep-me": {"runner": "claude"}, "drop-me": {"runner": "claude"}}}
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert set(resp.json()["agents"]) == {"keep-me", "drop-me"}

    resp2 = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"keep-me": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["agents"] == ["keep-me"]

    async with async_session_factory() as db:
        result = await db.execute(select(Agent).where(Agent.project_id == "proj-test"))
        names = {row.name for row in result.scalars().all()}
    assert names == {"keep-me"}


@pytest.mark.asyncio
async def test_sync_rejects_agent_name_that_could_escape_worktree_root(app, auth_headers):
    response = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"../escape": {"runner": "claude"}}}},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "agent name" in response.json()["detail"]


@pytest.mark.asyncio
async def test_removing_agent_releases_its_worktree_and_reports_no_unmerged_work(
    app, auth_headers, bind_project_workspace, tmp_path
):
    repo_root = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo_root)
    path = worktrees.ensure_worktree(repo_root, "leaving-agent")
    assert path.is_dir()

    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"leaving-agent": {"runner": "claude"}}}},
        headers=auth_headers,
    )

    queue = sse_manager.subscribe("proj-test")
    resp = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {}}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert not path.exists()

    events = _drain(queue)
    released = [payload for name, payload in events if name == "worktree_released"]
    assert released == [
        {"agent": "leaving-agent", "branch": "agentweave/leaving-agent", "had_unmerged_work": False}
    ]

    branches = _git(repo_root, "branch", "--list", "agentweave/leaving-agent").stdout
    assert "agentweave/leaving-agent" in branches


@pytest.mark.asyncio
async def test_removing_agent_with_dirty_worktree_reports_unmerged_work(
    app, auth_headers, bind_project_workspace, tmp_path
):
    repo_root = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo_root)
    path = worktrees.ensure_worktree(repo_root, "dirty-agent")
    (path / "f.txt").write_text("dirty-agent's uncommitted work\n")

    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"dirty-agent": {"runner": "claude"}}}},
        headers=auth_headers,
    )

    queue = sse_manager.subscribe("proj-test")
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {}}},
        headers=auth_headers,
    )

    events = _drain(queue)
    released = [payload for name, payload in events if name == "worktree_released"]
    assert len(released) == 1
    assert released[0]["agent"] == "dirty-agent"
    assert released[0]["had_unmerged_work"] is True

    log = _git(repo_root, "log", "agentweave/dirty-agent", "-1", "--format=%s").stdout
    assert "dirty-agent" in log


@pytest.mark.asyncio
async def test_removing_agent_that_never_had_a_worktree_is_a_no_op(
    app, auth_headers, bind_project_workspace, tmp_path
):
    await bind_project_workspace(_init_repo(tmp_path / "repo"))

    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"never-provisioned": {"runner": "claude"}}}},
        headers=auth_headers,
    )

    queue = sse_manager.subscribe("proj-test")
    resp = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {}}},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    events = _drain(queue)
    assert [name for name, _ in events if name == "worktree_released"] == []


@pytest.mark.asyncio
async def test_removing_an_agent_leaves_the_checkouts_of_its_tasks_alone(
    app, auth_headers, bind_project_workspace, tmp_path
):
    """Task 6.10, and the decision it asked to be written down rather than inherited.

    A task's terminal status is the only thing that releases its checkout. A roster edit is not
    a statement about the task: its status is unchanged, another agent may be assigned to
    continue it, and taking the working tree away would act on the task lifecycle for a reason
    that has nothing to do with the task.

    Asserted alongside the agent's *own* release in the same sync, because that is what makes it
    a decision rather than an omission — a test showing only the task checkout surviving would
    equally describe a removal path that had stopped releasing anything at all.
    """
    repo_root = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo_root)
    base = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
    own = worktrees.ensure_worktree(repo_root, "leaving-agent")
    task_checkout = ensure_task_worktree(repo_root, "task-ab12cd34ef56", base, ())
    assert own.is_dir() and task_checkout.is_dir()

    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"leaving-agent": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    resp = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {}}},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert not own.exists()
    assert task_checkout.is_dir()
    # And git still registers it, so the checkout is usable rather than merely present on disk.
    assert worktrees._registered_worktree_branch(repo_root, task_checkout) == (
        f"refs/heads/{worktrees.task_branch_name('task-ab12cd34ef56')}"
    )
