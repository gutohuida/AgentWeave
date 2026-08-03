"""Two-project filesystem isolation for direct/queued runs, context materialization,
workspace path listing, and worktree create/list/conflicts (phase 3, task 3.1 of
openspec/changes/2026-08-03-local-multi-project-workspace).

Every test here registers two real, distinct project directories under `tmp_path` and
asserts that one project's agent, context file, worktree, or workspace listing never
appears under the other's directory or its API responses — the core guarantee behind
design.md Decision 3: "No project-aware runtime operation SHALL use the Hub process
working directory as project identity."
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.project_lifecycle import ProjectLifecycleService

# Captured at collection time, before conftest.py's `_no_real_worktree_provision`
# autouse fixture (per-test) monkeypatches the module attribute — mirrors
# test_agent_trigger.py's identical `_REAL_RESOLVE_AGENT_WORKSPACE` pattern.
_REAL_RESOLVE_AGENT_WORKSPACE = worktrees.resolve_agent_workspace


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "README.md").write_text("base\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-q", "-m", "base")
    return path


async def _second_project(directory: Path) -> str:
    """Register *directory* as a genuinely new second project (not the legacy
    `proj-test` binding, which `bind_project_workspace` already claims for the first
    directory in a two-project test).
    """
    async with async_session_factory() as session:
        project = await ProjectLifecycleService(session).open_existing(directory)
    return project.id


async def _bind_runner(app, auth_headers, project_id, agent_name, cli="claude"):
    created = await app.post(
        f"/api/v1/projects/{project_id}/runners",
        json={"name": f"{agent_name}-runner", "cli": cli},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    runner_id = created.json()["id"]
    bound = await app.patch(
        f"/api/v1/projects/{project_id}/agents/{agent_name}",
        json={"runner_id": runner_id},
        headers=auth_headers,
    )
    assert bound.status_code == 200, bound.text
    return runner_id


def _fake_pty(lines, pid=4242):
    session = MagicMock()
    session.pid = pid
    session.read.side_effect = [*lines, ""]
    session.wait.return_value = 0
    return MagicMock(return_value=session)


@pytest.fixture
def two_projects(tmp_path):
    return _init_repo(tmp_path / "project-a"), _init_repo(tmp_path / "project-b")


@pytest.mark.asyncio
async def test_direct_trigger_materializes_context_in_its_own_project_directory(
    app, auth_headers, bind_project_workspace, two_projects
):
    """A direct (immediate) trigger for a read-only agent in project A writes its
    canonical context file under project A's directory only — never project B's, even
    though both projects are registered in the same running instance.
    """
    dir_a, dir_b = two_projects
    await bind_project_workspace(dir_a)
    project_b = await _second_project(dir_b)

    from hub.api.v1 import agent_trigger

    for project_id in ("proj-test", project_b):
        sync = await app.post(
            f"/api/v1/projects/{project_id}/session/sync",
            json={"data": {"agents": {"reader": {"runner": "claude", "read_only": True}}}},
            headers=auth_headers,
        )
        assert sync.status_code == 200
        await _bind_runner(app, auth_headers, project_id, "reader")

        # A fresh mock per trigger call: PtySession.spawn's `return_value` session is
        # the same object every call, and its `read.side_effect` list is a one-shot
        # iterator — reusing one across two runs starves the second run's read loop.
        fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
        with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
                resp = await app.post(
                    f"/api/v1/projects/{project_id}/agent/trigger",
                    json={"agent": "reader", "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                while agent_trigger._background_runs:
                    for task in list(agent_trigger._background_runs):
                        await task

    context_a = dir_a / ".agentweave" / "context" / "reader.md"
    context_b = dir_b / ".agentweave" / "context" / "reader.md"
    assert context_a.exists()
    assert context_b.exists()
    # The load-bearing assertion: each project's context file lives only under its own
    # directory — writing project B's context never touched project A's tree and vice
    # versa (there is exactly one reader.md under each root, not a cross-written pair).
    assert list((dir_a / ".agentweave" / "context").glob("*.md")) == [context_a]
    assert list((dir_b / ".agentweave" / "context").glob("*.md")) == [context_b]


@pytest.mark.asyncio
async def test_concurrent_writing_agents_get_isolated_worktrees_per_project(
    app, auth_headers, bind_project_workspace, two_projects, monkeypatch
):
    """Two writing agents named identically ("writer") in two different projects each
    get their own worktree rooted under their own project directory — never the other's.
    """
    dir_a, dir_b = two_projects
    await bind_project_workspace(dir_a)
    project_b = await _second_project(dir_b)

    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)

    from hub.api.v1 import agent_trigger

    for project_id in ("proj-test", project_b):
        sync = await app.post(
            f"/api/v1/projects/{project_id}/session/sync",
            json={"data": {"agents": {"writer": {"runner": "claude"}}}},
            headers=auth_headers,
        )
        assert sync.status_code == 200
        await _bind_runner(app, auth_headers, project_id, "writer")

        # A fresh mock per trigger call — see the comment in the context-materialization
        # test above for why reusing one across two runs hangs the second run's read loop.
        fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
        with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
                resp = await app.post(
                    f"/api/v1/projects/{project_id}/agent/trigger",
                    json={"agent": "writer", "message": "write", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                while agent_trigger._background_runs:
                    for task in list(agent_trigger._background_runs):
                        await task

    worktree_a = worktrees.worktree_path(dir_a, "writer")
    worktree_b = worktrees.worktree_path(dir_b, "writer")
    assert worktree_a.is_dir()
    assert worktree_b.is_dir()
    assert worktree_a != worktree_b
    assert not (dir_a / ".agentweave" / "worktrees" / "writer_wrong").exists()


@pytest.mark.asyncio
async def test_workspace_paths_endpoint_is_scoped_to_its_own_project(
    app, auth_headers, bind_project_workspace, two_projects
):
    dir_a, dir_b = two_projects
    await bind_project_workspace(dir_a)
    project_b = await _second_project(dir_b)

    (dir_a / "only-in-a.txt").write_text("a\n")
    (dir_b / "only-in-b.txt").write_text("b\n")

    resp_a = await app.get("/api/v1/projects/proj-test/workspace/paths", headers=auth_headers)
    resp_b = await app.get(f"/api/v1/projects/{project_b}/workspace/paths", headers=auth_headers)
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    assert "only-in-a.txt" in resp_a.json()
    assert "only-in-b.txt" not in resp_a.json()
    assert "only-in-b.txt" in resp_b.json()
    assert "only-in-a.txt" not in resp_b.json()


@pytest.mark.asyncio
async def test_worktree_endpoints_are_scoped_to_their_own_project(
    app, auth_headers, bind_project_workspace, two_projects, monkeypatch
):
    dir_a, dir_b = two_projects
    await bind_project_workspace(dir_a)
    project_b = await _second_project(dir_b)

    worktrees.ensure_worktree(dir_a, "alice")
    worktrees.ensure_worktree(dir_b, "bob")

    listing_a = await app.get("/api/v1/projects/proj-test/worktrees", headers=auth_headers)
    listing_b = await app.get(f"/api/v1/projects/{project_b}/worktrees", headers=auth_headers)

    assert listing_a.status_code == 200
    assert listing_b.status_code == 200
    assert {item["agent"] for item in listing_a.json()} == {"alice"}
    assert {item["agent"] for item in listing_b.json()} == {"bob"}


@pytest.mark.asyncio
async def test_work_dir_rejects_traversal_for_read_only_agent(
    app, auth_headers, bind_project_workspace, two_projects
):
    """Task 3.3: work_dir is project-relative only. Absolute paths and `..` traversal
    must be refused, not silently escape the project root."""
    dir_a, _ = two_projects
    await bind_project_workspace(dir_a)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"reader": {"runner": "claude", "read_only": True}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await _bind_runner(app, auth_headers, "proj-test", "reader")

    for bad_work_dir in ("..", "../escape", "/etc", str(dir_a.parent)):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "reader", "message": "hi", "work_dir": bad_work_dir},
            headers=auth_headers,
        )
        assert resp.status_code == 400, (bad_work_dir, resp.text)


@pytest.mark.asyncio
async def test_work_dir_accepts_a_contained_relative_path(
    app, auth_headers, bind_project_workspace, two_projects
):
    dir_a, _ = two_projects
    await bind_project_workspace(dir_a)
    (dir_a / "sub").mkdir()
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"reader": {"runner": "claude", "read_only": True}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await _bind_runner(app, auth_headers, "proj-test", "reader")

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    from hub.api.v1 import agent_trigger

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "reader", "message": "hi", "work_dir": "sub"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            while agent_trigger._background_runs:
                for task in list(agent_trigger._background_runs):
                    await task

    assert Path(fake_spawn.call_args.kwargs["cwd"]) == dir_a / "sub"


@pytest.mark.asyncio
async def test_work_dir_rejects_a_symlink_that_escapes_the_project(
    app, auth_headers, bind_project_workspace, two_projects
):
    """Task 3.3: `resolve_relative` resolves symlinks (`strict=False`) before checking
    containment, so a project-relative-looking `work_dir` that is actually a symlink
    pointing outside the project root must still be refused.

    Windows without Developer Mode/admin rights denies symlink creation (same caveat
    documented in `test_worktrees.py`'s `test_symlinks_shared_dependency_dirs_into_new_worktree`)
    — skip rather than fail when this environment can't create one.
    """
    dir_a, dir_b = two_projects
    await bind_project_workspace(dir_a)

    escape_link = dir_a / "escape"
    try:
        escape_link.symlink_to(dir_b, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"reader": {"runner": "claude", "read_only": True}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await _bind_runner(app, auth_headers, "proj-test", "reader")

    resp = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "reader", "message": "hi", "work_dir": "escape"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "work_dir" in resp.json()["detail"].lower()
