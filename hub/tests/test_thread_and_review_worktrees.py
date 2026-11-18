"""Thread and review worktrees (`one-profile-runs-many-turns-at-once-on-different-tasks`, task
`per-run-slots`: FR-2, FR-8, FR-13, FR-14, FR-17).

A chat the operator opens while the project's "profiles run in parallel" switch is on works in a
worktree of its own on `thread/<agent>/<thread>`, cut from the main branch at its first writing
turn and caught up with it before later ones; every other conversation keeps the agent's shared
`.agentweave/worktrees/<agent>`. Each review run gets its own detached checkout while the switch is
on. A thread's worktree is removed only once it is archived with nothing unmerged.

Unit tests run `worktrees` against a `tmp_path` repository; the trigger tests observe the spawned
process's `cwd`, the one fact an agent acts on (`test_turn_workspace.py`'s pattern).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub import thread_cleanup, worktrees
from hub.conversations import give_own_worktree_if_parallel, new_conversation, thread_of
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, Project

from .test_agent_trigger import _await_background_run, _fake_pty
from .test_review_turn import (
    _REAL_ENSURE_REVIEW_CHECKOUT,
    _author_commit,
    _reviewable_task,
    _trigger_review,
)
from .test_turn_workspace import _agent, _init_repo, _real_worktrees, _turn

THREAD_A = "conv-aaaaaaaaaaaa"
THREAD_B = "conv-bbbbbbbbbbbb"
_RESULT = ['{"type":"result","subtype":"success","is_error":false}\n']


def _git(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(path), capture_output=True, text=True)


def _rev(path: Path, ref: str = "HEAD") -> str:
    return _git(path, "rev-parse", ref).stdout.strip()


def _branch_of(path: Path) -> str:
    return _git(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def _commit_on_main(repo: Path, name: str, body: str = "main\n") -> str:
    (repo / name).write_text(body)
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", f"main adds {name}")
    return _rev(repo)


def _thread_branches(repo: Path) -> list:
    return _git(repo, "branch", "--list", "thread/*", "--format=%(refname:short)").stdout.split()


WRITER = {"runner": "claude"}


# ---------------------------------------------------------------------------
# worktrees: allocation, catch-up and the end-of-turn commit (FR-13)
# ---------------------------------------------------------------------------


def test_a_thread_branch_is_cut_from_main_beside_the_agents_own_branch(tmp_path):
    """`agentweave/<agent>` exists first: git would refuse `agentweave/<agent>/<thread>`, and the
    top-level `thread/` namespace is not refused."""
    repo = _init_repo(tmp_path / "repo")
    worktrees.ensure_worktree(repo, "writer")
    main_head = _rev(repo, "main")

    path = worktrees.ensure_thread_worktree(repo, "writer", THREAD_A, "main")

    assert path == worktrees.thread_worktree_path(repo, "writer", THREAD_A)
    assert path.parent == repo / ".agentweave" / "threads"
    assert _branch_of(path) == f"thread/writer/{THREAD_A}"
    assert _rev(path) == main_head
    # Reused, never re-cut.
    assert worktrees.ensure_thread_worktree(repo, "writer", THREAD_A, "main") == path


def test_a_threads_turns_share_its_worktree_catch_up_and_commit_to_its_branch_only(tmp_path):
    """ac-thread-branch: same worktree for both turns; first commit's parent is main's head at
    creation; main's later commit is merged in before the second turn; the end-of-turn commits
    are on the thread's branch only, and the agent's own branch never moves."""
    repo = _init_repo(tmp_path / "repo")
    worktrees.ensure_worktree(repo, "writer")
    agent_tip = _rev(repo, "agentweave/writer")
    main_at_creation = _rev(repo, "main")

    first = worktrees.resolve_turn_workspace(
        repo, "writer", WRITER, catch_up_to="main", thread=THREAD_A
    ).path
    (first / "a.txt").write_text("turn one\n")
    sha_one = worktrees.snapshot_worktree(first, "writer")
    branch = worktrees.thread_branch_name("writer", THREAD_A)
    assert _rev(repo, f"{sha_one}^") == main_at_creation

    main_later = _commit_on_main(repo, "main.txt")
    second = worktrees.resolve_turn_workspace(
        repo, "writer", WRITER, catch_up_to="main", thread=THREAD_A
    ).path
    assert second == first
    assert _git(second, "merge-base", "--is-ancestor", main_later, "HEAD").returncode == 0
    (second / "b.txt").write_text("turn two\n")
    sha_two = worktrees.snapshot_worktree(second, "writer")

    for sha in (sha_one, sha_two):
        holders = _git(repo, "branch", "--contains", sha, "--format=%(refname:short)").stdout
        assert holders.split() == [branch]
    assert _rev(repo, "agentweave/writer") == agent_tip
    assert worktrees.turn_branch_name(repo, "writer", WRITER, thread=THREAD_A) == branch


def test_without_a_thread_an_untasked_turn_keeps_the_agents_shared_worktree(tmp_path, monkeypatch):
    """FR-2 / FR-13: no thread, no `thread/` branch and no new worktree."""
    _real_worktrees(monkeypatch)
    repo = _init_repo(tmp_path / "repo")
    path = worktrees.resolve_turn_workspace(repo, "writer", WRITER, catch_up_to="main").path
    assert path == worktrees.worktree_path(repo, "writer")
    assert _branch_of(path) == "agentweave/writer"
    assert _thread_branches(repo) == []
    assert not worktrees.thread_root(repo).exists()


def test_a_read_only_agents_thread_shares_the_project_checkout(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    read_only = {"runner": "claude", "read_only": True}
    path = worktrees.resolve_turn_workspace(
        repo, "reader", read_only, catch_up_to="main", thread=THREAD_A
    ).path
    assert path == repo
    assert _thread_branches(repo) == []


def test_a_thread_name_is_refused_unless_the_hub_minted_it(tmp_path):
    for bad in ("../x", "conv-ABC", "main", "conv-12/34"):
        with pytest.raises(ValueError):
            worktrees.thread_worktree_path(tmp_path, "writer", bad)


# ---------------------------------------------------------------------------
# FR-8: separate trees
# ---------------------------------------------------------------------------


def test_two_threads_and_two_review_runs_never_share_a_tree(tmp_path):
    """ac-separate-trees, at the allocation: four different folders; the review runs are on no
    branch; a file written in one is in no other."""
    repo = _init_repo(tmp_path / "repo")
    sha = _rev(repo, "main")
    a = worktrees.ensure_thread_worktree(repo, "writer", THREAD_A, "main")
    b = worktrees.ensure_thread_worktree(repo, "writer", THREAD_B, "main")
    ensure = _REAL_ENSURE_REVIEW_CHECKOUT
    r1 = ensure(repo, "writer", sha, run_id="run-111111111111")
    r2 = ensure(repo, "writer", sha, run_id="run-222222222222")
    trees = [a, b, r1, r2]
    assert len(set(trees)) == 4
    for review in (r1, r2):
        assert _branch_of(review) == "HEAD"  # detached
        assert review != worktrees.review_path(repo, "writer")
    for index, tree in enumerate(trees):
        (tree / f"file{index}.txt").write_text(str(index))
    for index in range(len(trees)):
        for other_index, other in enumerate(trees):
            if other_index != index:
                assert not (other / f"file{index}.txt").exists()

    assert worktrees.release_review_run_checkout(repo, r1)
    assert not r1.exists() and r2.exists()
    # Only a run's own checkout is this function's to remove.
    shared = ensure(repo, "writer", sha)
    assert not worktrees.release_review_run_checkout(repo, shared)
    assert shared.exists()


# ---------------------------------------------------------------------------
# FR-17: the listing and the conflicts check see threads
# ---------------------------------------------------------------------------


def test_the_listing_and_conflicts_check_report_two_diverging_threads(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    for thread, body in ((THREAD_A, "a\n"), (THREAD_B, "b\n")):
        path = worktrees.ensure_thread_worktree(repo, "writer", thread, "main")
        (path / "README.md").write_text(body)
        worktrees.snapshot_worktree(path, "writer")

    listed = {(w.kind, w.name, w.branch, w.agent) for w in worktrees.list_workspace_branches(repo)}
    assert ("thread", THREAD_A, f"thread/writer/{THREAD_A}", "writer") in listed
    assert ("thread", THREAD_B, f"thread/writer/{THREAD_B}", "writer") in listed

    reports = worktrees.detect_conflicts(repo, "main")
    pairs = [
        ({w.name for w in report.workspaces}, report.paths)
        for report in reports
        if all(w.kind == "thread" for w in report.workspaces)
    ]
    assert pairs == [({THREAD_A, THREAD_B}, ["README.md"])]


# ---------------------------------------------------------------------------
# FR-14: removal
# ---------------------------------------------------------------------------


def test_a_merged_threads_worktree_goes_and_an_unmerged_one_stays_with_its_branch(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    merged = worktrees.ensure_thread_worktree(repo, "writer", THREAD_A, "main")
    (merged / "merged.txt").write_text("in main\n")
    worktrees.snapshot_worktree(merged, "writer")
    _git(repo, "merge", "-q", "--ff-only", f"thread/writer/{THREAD_A}")
    unmerged = worktrees.ensure_thread_worktree(repo, "writer", THREAD_B, "main")
    (unmerged / "unmerged.txt").write_text("not in main\n")
    worktrees.snapshot_worktree(unmerged, "writer")

    gone = worktrees.release_thread_worktree(repo, "writer", THREAD_A, "main")
    kept = worktrees.release_thread_worktree(repo, "writer", THREAD_B, "main")

    assert gone.removed and not merged.exists()
    # Removing a worktree never removes its branch (D6).
    assert f"thread/writer/{THREAD_A}" in _thread_branches(repo)
    assert not kept.removed and "not on main" in (kept.kept_reason or "")
    assert unmerged.exists() and f"thread/writer/{THREAD_B}" in _thread_branches(repo)


def test_a_thread_with_uncommitted_work_is_kept(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    path = worktrees.ensure_thread_worktree(repo, "writer", THREAD_A, "main")
    (path / "draft.txt").write_text("not committed\n")
    result = worktrees.release_thread_worktree(repo, "writer", THREAD_A, "main")
    assert not result.removed and result.kept_reason == "it has uncommitted changes"
    assert (path / "draft.txt").exists()


async def _thread_conversation(agent: str, thread_id: str, *, lifecycle: str) -> None:
    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent=agent, origin="operator")
        conversation.id = thread_id
        conversation.lineage_id = thread_id
        conversation.own_worktree = True
        conversation.lifecycle = lifecycle
        session.add(conversation)
        await session.commit()


async def _set_project(**values) -> None:
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        for key, value in values.items():
            setattr(project, key, value)
        await session.commit()


@pytest.mark.asyncio
async def test_the_hubs_cleanup_removes_only_the_merged_archived_thread(
    app, bind_project_workspace, tmp_path
):
    """ac-thread-removal, through the cleanup pass the Hub runs."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _set_project(main_branch="main")
    merged = worktrees.ensure_thread_worktree(repo, "writer", THREAD_A, "main")
    (merged / "merged.txt").write_text("in main\n")
    worktrees.snapshot_worktree(merged, "writer")
    _git(repo, "merge", "-q", "--ff-only", f"thread/writer/{THREAD_A}")
    unmerged = worktrees.ensure_thread_worktree(repo, "writer", THREAD_B, "main")
    (unmerged / "unmerged.txt").write_text("not in main\n")
    worktrees.snapshot_worktree(unmerged, "writer")
    await _thread_conversation("writer", THREAD_A, lifecycle="archived")
    await _thread_conversation("writer", THREAD_B, lifecycle="archived")

    async with async_session_factory() as session:
        removed = await thread_cleanup.sweep_project(session, "proj-test")

    assert removed["threads"] == 1
    assert not merged.exists()
    assert unmerged.exists()
    assert set(_thread_branches(repo)) == {f"thread/writer/{THREAD_A}", f"thread/writer/{THREAD_B}"}


@pytest.mark.asyncio
async def test_the_cleanup_leaves_an_open_threads_merged_worktree(
    app, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _set_project(main_branch="main")
    path = worktrees.ensure_thread_worktree(repo, "writer", THREAD_A, "main")
    await _thread_conversation("writer", THREAD_A, lifecycle="open")
    async with async_session_factory() as session:
        removed = await thread_cleanup.sweep_project(session, "proj-test")
    assert removed["threads"] == 0 and path.exists()


# ---------------------------------------------------------------------------
# Which conversations get a worktree of their own (FR-2, FR-13)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("switch", "origin", "expected"),
    [
        (False, "operator", False),
        (True, "operator", True),
        (True, "job", False),
        (True, "peer", False),
    ],
)
async def test_only_a_chat_the_operator_opens_with_the_switch_on_gets_one(
    app, switch, origin, expected
):
    await _set_project(profiles_run_in_parallel=switch)
    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent="writer", origin=origin)
        await give_own_worktree_if_parallel(session, conversation)
    assert conversation.own_worktree is expected
    assert (thread_of(conversation) is not None) is expected


async def _route_chat(app, auth_headers, message: str):
    fake_spawn = _fake_pty(_RESULT)
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "writer", "message": message},
                headers=auth_headers,
            )
            assert response.status_code == 200, response.text
            await _await_background_run()
    return response.json(), Path(fake_spawn.call_args.kwargs["cwd"])


@pytest.mark.asyncio
async def test_with_the_switch_off_a_new_chat_runs_in_the_shared_worktree(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """ac-off-no-thread-worktree."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    worktrees_before = _git(repo, "worktree", "list").stdout.count("\n")

    body, cwd = await _route_chat(app, auth_headers, "hello")

    assert cwd == worktrees.worktree_path(repo, "writer")
    assert _branch_of(cwd) == "agentweave/writer"
    assert _thread_branches(repo) == []
    assert _git(repo, "worktree", "list").stdout.count("\n") == worktrees_before + 1
    async with async_session_factory() as session:
        conversation = (
            await session.execute(
                select(Conversation).where(Conversation.id == body["conversation_id"])
            )
        ).scalar_one()
    assert conversation.own_worktree is False


@pytest.mark.asyncio
async def test_with_the_switch_on_each_new_chat_runs_in_its_own_thread_worktree(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """ac-separate-trees and ac-thread-branch through the trigger route: two chats, two worktrees
    on two `thread/writer/<thread>` branches cut from main, two context files; and a conversation
    that existed before keeps `.agentweave/worktrees/writer`."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    worktrees.ensure_worktree(repo, "writer")
    async with async_session_factory() as session:
        before = new_conversation(project_id="proj-test", agent="writer", origin="operator")
        session.add(before)
        await session.commit()
        before_id = before.id
    await _set_project(profiles_run_in_parallel=True)
    main_head = _rev(repo, "main")

    first, cwd_a = await _route_chat(app, auth_headers, "chat a")
    second, cwd_b = await _route_chat(app, auth_headers, "chat b")

    assert cwd_a != cwd_b
    for body, cwd in ((first, cwd_a), (second, cwd_b)):
        thread = body["conversation_id"]
        assert cwd == worktrees.thread_worktree_path(repo, "writer", thread)
        assert _branch_of(cwd) == f"thread/writer/{thread}"
        assert _git(cwd, "merge-base", "--is-ancestor", main_head, "HEAD").returncode == 0
        assert (cwd / ".agentweave" / "context" / "writer.md").is_file()
        assert (cwd / ".agentweave" / "calls").is_dir()

    old = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="the old chat",
        conversation_id=before_id,
    )
    assert Path(old) == worktrees.worktree_path(repo, "writer")


@pytest.mark.asyncio
async def test_with_the_switch_on_a_job_conversation_keeps_the_shared_worktree(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """ac-shared-worktree-serial, its allocation half: no thread worktree for a firing."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    await _set_project(profiles_run_in_parallel=True)
    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent="writer", origin="job")
        await give_own_worktree_if_parallel(session, conversation)
        session.add(conversation)
        await session.commit()
        conversation_id = conversation.id

    cwd = await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="scheduled",
        conversation_id=conversation_id,
    )
    assert Path(cwd) == worktrees.worktree_path(repo, "writer")
    assert _thread_branches(repo) == []


# ---------------------------------------------------------------------------
# FR-17: the routes show the thread's branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_threads_changes_view_workspace_route_and_listing_name_its_branch(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    await _set_project(profiles_run_in_parallel=True, main_branch="main")

    first, cwd_a = await _route_chat(app, auth_headers, "chat a")
    second, cwd_b = await _route_chat(app, auth_headers, "chat b")
    (cwd_a / "README.md").write_text("thread a\n")
    worktrees.snapshot_worktree(cwd_a, "writer")
    (cwd_b / "README.md").write_text("thread b\n")
    worktrees.snapshot_worktree(cwd_b, "writer")
    thread_a, thread_b = first["conversation_id"], second["conversation_id"]
    branch_a = f"thread/writer/{thread_a}"

    changes = await app.get(
        f"/api/v1/projects/proj-test/conversations/{thread_a}/changes", headers=auth_headers
    )
    assert changes.status_code == 200, changes.text
    assert changes.json()["branch"] == branch_a
    assert "README.md" in [f["path"] for f in changes.json()["since_base"]]
    patch_response = await app.get(
        f"/api/v1/projects/proj-test/conversations/{thread_a}/changes/patch",
        params={"path": "README.md", "scope": "branch"},
        headers=auth_headers,
    )
    assert patch_response.status_code == 200, patch_response.text
    assert "thread a" in patch_response.json()["patch"]

    workspace = await app.get(
        "/api/v1/projects/proj-test/worktrees/writer",
        params={"conversation_id": thread_a},
        headers=auth_headers,
    )
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["branch"] == branch_a
    assert Path(workspace.json()["working_dir"]) == cwd_a
    assert {t["branch"] for t in workspace.json()["thread_checkouts"]} == {
        branch_a,
        f"thread/writer/{thread_b}",
    }

    listing = await app.get("/api/v1/projects/proj-test/worktrees", headers=auth_headers)
    threads = {
        (w["name"], w["branch"], w["agent"])
        for w in listing.json()["worktrees"]
        if w["kind"] == "thread"
    }
    assert threads == {
        (thread_a, branch_a, "writer"),
        (thread_b, f"thread/writer/{thread_b}", "writer"),
    }

    conflicts = await app.get(
        "/api/v1/projects/proj-test/worktrees/conflicts", headers=auth_headers
    )
    between_threads = [
        c
        for c in conflicts.json()["conflicts"]
        if all(w["kind"] == "thread" for w in c["workspaces"])
    ]
    assert len(between_threads) == 1 and between_threads[0]["paths"] == ["README.md"]


# ---------------------------------------------------------------------------
# FR-8: a review run's own checkout, released when it ends
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_the_switch_on_a_review_run_gets_its_own_checkout_and_releases_it(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _agent(app, auth_headers, bind_runner, "critic")
    await _reviewable_task(commit=sha)
    await _set_project(profiles_run_in_parallel=True)

    seen = {}

    def _spawn(*args, **kwargs):
        cwd = Path(kwargs["cwd"])
        seen["cwd"] = cwd
        seen["branch"] = _branch_of(cwd)
        seen["file"] = (cwd / "ledger.py").read_text()
        return _fake_pty(_RESULT)(*args, **kwargs)

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", _spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            response = await _trigger_review(app, auth_headers)
            assert response.status_code == 200, response.text
            await _await_background_run()

    run_id = response.json()["run_id"]
    assert seen["cwd"] == worktrees.review_run_path(repo, "critic", run_id)
    assert seen["branch"] == "HEAD" and seen["file"] == "x = 1\n"
    assert not seen["cwd"].exists()
    assert not worktrees.review_path(repo, "critic").exists()


@pytest.mark.asyncio
async def test_with_the_switch_off_a_review_uses_the_reviewers_shared_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """FR-2: off, the review checkout is exactly what it was."""
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _agent(app, auth_headers, bind_runner, "critic")
    await _reviewable_task(commit=sha)

    fake_spawn = _fake_pty(_RESULT)
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            response = await _trigger_review(app, auth_headers)
            assert response.status_code == 200, response.text
            await _await_background_run()

    cwd = Path(fake_spawn.call_args.kwargs["cwd"])
    assert cwd == worktrees.review_path(repo, "critic")
    assert cwd.exists()


# ---------------------------------------------------------------------------
# FR-2: with the switch off, one profile still runs one turn at a time
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_the_switch_off_a_second_task_start_waits_for_the_first(
    app, auth_headers, bind_runner
):
    """ac-off-serial: two ready tasks of one profile, both started; the second is queued with
    the existing "agent is already running" wait."""
    import threading
    from unittest.mock import MagicMock

    from hub.db.models import Task

    await _agent(app, auth_headers, bind_runner, "writer")
    async with async_session_factory() as session:
        for task_id in ("task-0a0a0a0a0a0a", "task-0b0b0b0b0b0b"):
            session.add(
                Task(
                    id=task_id,
                    project_id="proj-test",
                    title=task_id,
                    status="assigned",
                    assignee="writer",
                )
            )
        await session.commit()

    release = threading.Event()
    hanging = MagicMock()
    hanging.pid = 999
    hanging.read.side_effect = lambda size=4096: (release.wait(), "")[1]
    hanging.wait.return_value = 0
    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=hanging)
    ):
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            try:
                first = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "writer", "message": "one", "task_id": "task-0a0a0a0a0a0a"},
                    headers=auth_headers,
                )
                assert first.status_code == 200, first.text
                assert first.json()["status"] == "running"
                second = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "writer", "message": "two", "task_id": "task-0b0b0b0b0b0b"},
                    headers=auth_headers,
                )
                assert second.status_code == 200, second.text
                assert second.json()["status"] == "queued"
                assert "already running" in second.json()["waiting_reason"]
            finally:
                release.set()
                await _await_background_run()


@pytest.mark.asyncio
async def test_with_the_switch_on_a_read_only_run_in_the_project_directory_has_its_own_context(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """FR-8: runs of one read-only agent share the project directory, so each is given a context
    file named by the run, removed when the run ends; `<agent>.md` is never written there."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _agent(app, auth_headers, bind_runner, "reader", {"read_only": True})
    await _set_project(profiles_run_in_parallel=True)
    seen = []

    def _spawn(*args, **kwargs):
        assert Path(kwargs["cwd"]) == repo
        seen.append(sorted(p.name for p in (repo / ".agentweave" / "context").iterdir()))
        return _fake_pty(_RESULT)(*args, **kwargs)

    run_ids = []
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", _spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            for message in ("one", "two"):
                response = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "reader", "message": message},
                    headers=auth_headers,
                )
                assert response.status_code == 200, response.text
                run_ids.append(response.json()["run_id"])
                await _await_background_run()

    assert seen == [[f"reader.{run_ids[0]}.md"], [f"reader.{run_ids[1]}.md"]]
    assert list((repo / ".agentweave" / "context").iterdir()) == []


def test_0184_adds_own_worktree_false_for_every_conversation_and_round_trips(tmp_path):
    """0184 runs on the operator's real data: every existing conversation reads false (it keeps the
    shared worktree), no other value changes, and the downgrade removes only the column."""
    import sqlite3

    from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

    from .test_migration_0151_the_hub_may_override_checks import _add_project, _columns

    db_file = tmp_path / "threads.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0184')")
        conn.commit()
    _downgrade_to(db_url, "0183")
    with sqlite3.connect(db_file) as conn:
        assert "own_worktree" not in _columns(conn, "conversations")
        _add_project(conn, "proj-a")
        conn.execute(
            "INSERT INTO conversations (id, project_id, agent, lifecycle, origin, title_set_by_"
            "operator, created_at, updated_at) VALUES ('conv-1', 'proj-a', 'writer', 'open', "
            "'operator', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        conn.commit()
        names = [row[1] for row in conn.execute("PRAGMA table_info(conversations)")]
        before = conn.execute(f"SELECT {', '.join(names)} FROM conversations").fetchall()

    _upgrade_to(db_url, "0184")
    with sqlite3.connect(db_file) as conn:
        assert _columns(conn, "conversations") == set(names) | {"own_worktree"}
        assert conn.execute(f"SELECT {', '.join(names)} FROM conversations").fetchall() == before
        assert conn.execute("SELECT own_worktree FROM conversations").fetchall() == [(0,)]

    _downgrade_to(db_url, "0183")
    with sqlite3.connect(db_file) as conn:
        assert "own_worktree" not in _columns(conn, "conversations")
        assert conn.execute(f"SELECT {', '.join(names)} FROM conversations").fetchall() == before
