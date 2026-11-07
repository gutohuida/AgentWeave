"""A build lands as one pull request (`a-build-lands-as-one-pull-request`), task `notice`.

The Hub asks GitHub for an open PR's state on actions, in the background, never on a timer
(FR-9 asks-on-actions, ask-ac1); a PR found merged lands its tasks naming the merge commit, and one
closed records them not landed and keeps the branch (FR-10 merged-or-closed, mc-ac1, mc-ac2); the
local main is fast-forwarded to GitHub's when that is safe, and otherwise the project says it is
behind and Update says why (FR-11 local-main, lm-ac1, lm-ac2).

Real git throughout, against a local bare repository standing in for GitHub's remote; GitHub's
merge is made in that bare repository, and the GitHub CLI is the push tests' fake.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import landing_queue, pull_requests, worktrees
from hub.db.engine import async_session_factory
from hub.db.models import Build, TaskIntegration

from .test_a_build_has_a_driver_a_level_and_its_people import (
    BASE,
    _tasks_by_key,
    author_headers,  # noqa: F401 -- a fixture
)
from .test_a_build_lands_as_one_pull_request_push import (
    _approve,
    _build_row,
    _latest,
    _pr_build,
    _remote,
    _work,
)
from .test_task_integration import git
from .test_turn_workspace import (
    BOUND_TASK,
    _agent,
    _conversation,
    _init_repo,
    _real_worktrees,
    _task,
    _turn,
)

PROJECT = "/api/v1/projects/proj-test"


async def _pushed_build(  # noqa: F811
    app, auth_headers, author_headers, bind, tmp_path, monkeypatch  # noqa: F811
):
    """A PR build with both tasks pushed: an open, ready PR #1 on the fake GitHub."""
    repo, bare, fake, build_id = await _pr_build(
        app, auth_headers, author_headers, bind, tmp_path, monkeypatch
    )
    tasks = await _tasks_by_key()
    await _work(repo, tasks["t1"], "alpha.py", "a = 1\n")
    await _approve(tasks["t1"])
    await _work(repo, tasks["t2"], "beta.py", "b = 2\n")
    await _approve(tasks["t2"])
    assert (await _build_row(build_id)).pr_state == "ready"
    return repo, bare, fake, build_id, tasks


def _merge_on_github(bare: Path, fake, build_id: str) -> str:
    """GitHub merging PR #1: a merge commit of the build branch onto main, in the remote."""
    branch = f"refs/heads/{pull_requests.build_branch_name(build_id)}"
    head, main = _remote(bare, branch), _remote(bare, "refs/heads/main")
    tree = git(bare, "rev-parse", f"{head}^{{tree}}").stdout.strip()
    merge = git(
        bare,
        "-c",
        "user.name=GitHub",
        "-c",
        "user.email=noreply@github.com",
        "commit-tree",
        tree,
        "-p",
        main,
        "-p",
        head,
        "-m",
        "Merge pull request #1",
    ).stdout.strip()
    git(bare, "update-ref", "refs/heads/main", merge, main)
    fake.prs[1].update(state="MERGED", isDraft=False, mergeCommit={"oid": merge})
    return merge


async def _check_now(app, auth_headers, build_id, *, wait=True):
    answered = await app.post(
        f"{BASE}/builds/{build_id}/pull-request/check",
        params={"wait": "true" if wait else "false"},
        headers=auth_headers,
    )
    assert answered.status_code == 200, answered.text
    return answered.json()


# --- mc-ac2, lm-ac1 ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_merged_pr_lands_its_tasks_naming_the_merge_commit_and_moves_main(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    repo, bare, fake, build_id, tasks = await _pushed_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    merge = _merge_on_github(bare, fake, build_id)
    assert git(repo, "rev-parse", "main").stdout.strip() != merge

    # mc-ac2: 'check now' finds it merged, and its tasks read landed, naming GitHub's merge commit.
    read = await _check_now(app, auth_headers, build_id)
    assert read["pull_request"]["state"] == "merged"
    for key in ("t1", "t2"):
        landing = await _latest(tasks[key].id)
        assert (landing.state, landing.landed_sha) == (landing_queue.LANDED, merge)
        assert "#1" in landing.reason and merge[:12] in landing.reason
    async with async_session_factory() as db:
        merged = (
            await db.execute(select(TaskIntegration).where(TaskIntegration.merged_sha == merge))
        ).scalars()
        assert {row.task_id for row in merged} == {tasks["t1"].id, tasks["t2"].id}

    # lm-ac1: main is not checked out with changes, so the local main now equals GitHub's.
    assert git(repo, "rev-parse", "main").stdout.strip() == merge
    assert (repo / "alpha.py").is_file() and (repo / "beta.py").is_file()
    assert read["main"]["behind"] is False

    # Merged is not asked about again: it is no longer an open PR.
    asked = sum(call[:2] == ["pr", "view"] for call in fake.calls)
    await _check_now(app, auth_headers, build_id)
    assert sum(call[:2] == ["pr", "view"] for call in fake.calls) == asked
    # Never a merge, an approval or a base change: only reads and the PR's own updates.
    for call in fake.calls:
        pull_requests.check_gh_call(call)


# --- mc-ac1 --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_closed_pr_records_its_tasks_not_landed_and_keeps_the_branch(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    repo, bare, fake, build_id, tasks = await _pushed_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    branch = pull_requests.build_branch_name(build_id)
    main_before = git(repo, "rev-parse", "main").stdout.strip()
    fake.prs[1].update(state="CLOSED")

    # The operator opens the build: asked in the background.
    await _check_now(app, auth_headers, build_id, wait=False)
    await pull_requests.settle_asks()

    assert (await _build_row(build_id)).pr_state == "closed"
    for key in ("t1", "t2"):
        landing = await _latest(tasks[key].id)
        assert landing.state == landing_queue.NOT_LANDED
        assert "closed" in landing.reason and branch in landing.reason
    assert _remote(bare, f"refs/heads/{branch}") is not None, "kept on GitHub"
    assert git(repo, "rev-parse", "--verify", "--quiet", branch).returncode == 0, "kept locally"
    assert git(repo, "rev-parse", "main").stdout.strip() == main_before


# --- lm-ac2 --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_main_checked_out_with_a_change_is_left_alone_and_shown_behind(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    repo, bare, fake, build_id, tasks = await _pushed_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    main_before = git(repo, "rev-parse", "main").stdout.strip()
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    (repo / "README.md").write_text("the operator's own edit\n", encoding="utf-8")
    merge = _merge_on_github(bare, fake, build_id)

    read = await _check_now(app, auth_headers, build_id)

    # Found merged, and the tasks landed, but the local main and the change are untouched ...
    assert read["pull_request"]["state"] == "merged"
    assert (await _latest(tasks["t1"].id)).landed_sha == merge
    assert git(repo, "rev-parse", "main").stdout.strip() == main_before
    assert (repo / "README.md").read_text(encoding="utf-8") == "the operator's own edit\n"
    # ... and the project shows that main is behind GitHub, with why Update cannot yet.
    shown = (await app.get(f"{PROJECT}/main/github", headers=auth_headers)).json()["main"]
    assert shown["behind"] is True and shown["can_update"] is False
    assert shown["github"] == merge and "uncommitted" in shown["reason"]
    update = await app.post(f"{PROJECT}/main/update", headers=auth_headers)
    assert update.status_code == 200, update.text
    refused = update.json()["main"]
    assert refused["updated"] is False and "uncommitted" in refused["reason"]
    assert git(repo, "rev-parse", "main").stdout.strip() == main_before
    assert (repo / "README.md").read_text(encoding="utf-8") == "the operator's own edit\n"

    # Once the change is gone, Update does the same fast-forward.
    git(repo, "checkout", "--", "README.md")
    done = (await app.post(f"{PROJECT}/main/update", headers=auth_headers)).json()["main"]
    assert done["updated"] is True and done["behind"] is False
    assert git(repo, "rev-parse", "main").stdout.strip() == merge


@pytest.mark.asyncio
async def test_main_not_checked_out_is_moved_by_ref_and_a_diverged_main_is_not(tmp_path):
    """`main_state` on its own: main checked out nowhere moves by ref; one with its own commits is
    behind but not a fast-forward, and says so."""
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    repo = tmp_path / "repo"
    repo.mkdir()
    from .test_task_integration import make_repo

    make_repo(repo)
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "checkout", "-q", "-b", "elsewhere")
    git(repo, "commit", "-q", "--allow-empty", "-m", "ahead on GitHub")
    git(repo, "push", "-q", "origin", "elsewhere:main")
    github = git(repo, "rev-parse", "HEAD").stdout.strip()

    moved = pull_requests.main_state(repo, "origin", "main", fetch=True, move=True)
    assert (moved.updated, moved.behind) == (True, False)
    assert git(repo, "rev-parse", "main").stdout.strip() == github

    git(repo, "checkout", "-q", "main")
    git(repo, "commit", "-q", "--allow-empty", "-m", "local only")
    git(repo, "checkout", "-q", "elsewhere")
    git(repo, "commit", "-q", "--allow-empty", "-m", "GitHub again")
    git(repo, "push", "-q", "origin", "elsewhere:main")
    diverged = pull_requests.main_state(repo, "origin", "main", fetch=True, move=True)
    assert diverged.behind is True and diverged.updated is False
    assert "cannot be fast-forwarded" in diverged.reason


# --- ask-ac1 -------------------------------------------------------------------------------------


class SlowGitHub:
    """A GitHub CLI that counts its calls and does not answer until released (standing in for one
    that takes 30 s), answering an open draft PR."""

    def __init__(self) -> None:
        self.calls: list = []
        self.release = threading.Event()

    def __call__(self, root: Path, args: list) -> subprocess.CompletedProcess:
        self.calls.append(list(args))
        self.release.wait(30)
        answer = {"state": "OPEN", "isDraft": True, "mergeCommit": None}
        return subprocess.CompletedProcess(args, 0, json.dumps(answer), "")


@pytest.mark.asyncio
async def test_a_task_worktree_asks_once_in_the_background_and_idle_time_asks_nothing(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    _real_worktrees(monkeypatch)
    await _agent(app, auth_headers, bind_runner, "writer")
    conversation_id = await _conversation("writer")
    await _task(BOUND_TASK)
    async with async_session_factory() as db:
        db.add(
            Build(
                id="build-open-pr",
                project_id="proj-test",
                document_id="spdoc-x",
                driver="hand",
                level="reviewed",
                builders=[],
                reviewers=[],
                landing="pull_request",
                pr_number=7,
                pr_state="draft",
            )
        )
        await db.commit()
    slow = SlowGitHub()
    monkeypatch.setattr(pull_requests, "_run_gh", slow)
    monkeypatch.setattr(pull_requests, "gh_executable", lambda: "gh")

    started = time.monotonic()
    try:
        cwd = await _turn(
            async_session_factory,
            project_id="proj-test",
            agent="writer",
            message="work on it",
            conversation_id=conversation_id,
            task_id=BOUND_TASK,
        )
        took = time.monotonic() - started
        # The turn started in its new worktree without waiting for GitHub ...
        assert Path(cwd) == worktrees.task_worktree_path(repo, BOUND_TASK)
        assert not slow.release.is_set() and took < 25
        # ... which was asked, once, for the worktree's creation.
        for _ in range(500):
            if slow.calls:
                break
            await asyncio.sleep(0.01)
        assert [call[:3] for call in slow.calls] == [["pr", "view", "7"]]
    finally:
        slow.release.set()
        await pull_requests.settle_asks()
    assert (await _build_row("build-open-pr")).pr_last_asked_at is not None

    # An hour with no action: nothing is scheduled to ask, so nothing does. No task of the module
    # is left waiting, and the module arms no timer of any kind.
    leftover = [
        job
        for job in asyncio.all_tasks()
        if "pull_requests" in repr(job.get_coro()) and not job.done()
    ]
    assert leftover == [] and not pull_requests._asking
    source = Path(pull_requests.__file__).read_text(encoding="utf-8")
    for timer in ("asyncio.sleep", "call_later", "call_at", "threading.Timer", "time.sleep"):
        assert timer not in source, timer
    await asyncio.sleep(0.2)
    assert len(slow.calls) == 1

    # A second turn on the same task creates no worktree, so it asks nothing.
    await _turn(
        async_session_factory,
        project_id="proj-test",
        agent="writer",
        message="again",
        conversation_id=conversation_id,
        task_id=BOUND_TASK,
    )
    await pull_requests.settle_asks()
    assert len(slow.calls) == 1


@pytest.mark.asyncio
async def test_the_hub_starting_and_a_failed_ask_are_recorded_on_the_build(
    app, bind_project_workspace, tmp_path, monkeypatch
):
    """The Hub starting asks about every open PR in the background; GitHub's error from a failed
    ask is kept on the build (FR-13), and the PR's state is left as it was."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    async with async_session_factory() as db:
        for build_id, state in (("build-open", "ready"), ("build-done", "merged")):
            db.add(
                Build(
                    id=build_id,
                    project_id="proj-test",
                    document_id=f"spdoc-{build_id}",
                    driver="hand",
                    level="reviewed",
                    builders=[],
                    reviewers=[],
                    landing="pull_request",
                    pr_number=3,
                    pr_state=state,
                )
            )
        await db.commit()
    calls: list = []

    def refused(root, args):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 1, "", "HTTP 502: GitHub is down")

    monkeypatch.setattr(pull_requests, "_run_gh", refused)

    assert await pull_requests.notice_at_startup() == 1
    await pull_requests.settle_asks()

    assert calls == [["pr", "view", "3", "--json", "state,isDraft,mergeCommit"]]
    build = await _build_row("build-open")
    assert build.pr_state == "ready" and "GitHub is down" in build.pr_error
    assert build.pr_last_asked_at is not None
    assert (await _build_row("build-done")).pr_last_asked_at is None


# --- sh-ac1: the task shows its build's PR -------------------------------------------------------


@pytest.mark.asyncio
async def test_a_task_read_carries_its_builds_pr_link_state_and_last_asked_time(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch  # noqa: F811
):
    _repo, _bare, _fake, build_id, tasks = await _pushed_build(
        app, auth_headers, author_headers, bind_project_workspace, tmp_path, monkeypatch
    )
    await _check_now(app, auth_headers, build_id)
    read = await app.get(f"{PROJECT}/tasks/{tasks['t1'].id}", headers=auth_headers)
    assert read.status_code == 200, read.text
    shown = read.json()["pull_request"]
    assert shown["state"] == "ready" and shown["number"] == 1 and shown["url"]
    assert shown["last_asked_at"] and shown["error"] is None
