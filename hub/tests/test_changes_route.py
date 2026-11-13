"""The Changes route (SPSCT-2): what a conversation's agent changed, over temporary repositories.

`conftest` roots every project at the test's `tmp_path`, so the repository built here is the one
the route reads. Each test names the acceptance criterion of the change it carries.
"""

import subprocess
import time
from datetime import datetime, timedelta, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Agent, Conversation, Run, Task

P = "proj-test"
URL = f"/api/v1/projects/{P}/conversations"


def git(cwd, *args):
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit(cwd, message="c"):
    git(cwd, "add", "-A")
    git(cwd, "commit", "-q", "-m", message)
    return git(cwd, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    write(tmp_path, "README.md", "one\n")
    write(tmp_path, "src/app.py", "print(1)\n")
    commit(tmp_path, "base")
    return tmp_path


def add_branch(repo, branch, *, worktree):
    git(repo, "worktree", "add", "-q", "-b", branch, str(worktree), "main")
    return worktree


async def seed(*, agent="worker", conv="conv-ch", runs=(), read_only=False, task=None):
    async with async_session_factory() as session:
        if read_only:
            session.add(
                Agent(id=f"agt-{agent}", project_id=P, name=agent, config={"read_only": True})
            )
        if task:
            session.add(Task(id=task, project_id=P, title="Build the thing", status="in_progress"))
        session.add(
            Conversation(id=conv, project_id=P, agent=agent, lifecycle="open", origin="operator")
        )
        await session.flush()
        now = datetime.now(timezone.utc)
        for i, (status, sha, workspace) in enumerate(runs):
            session.add(
                Run(
                    id=f"run-ch-{i}",
                    project_id=P,
                    agent=agent,
                    status=status,
                    conversation_id=conv,
                    snapshot_commit_sha=sha,
                    workspace_dir=str(workspace) if workspace else None,
                    started_at=now + timedelta(seconds=i),
                )
            )
        await session.commit()


async def get(app, auth_headers, conv="conv-ch", **params):
    response = await app.get(f"{URL}/{conv}/changes", headers=auth_headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def by_path(files):
    return {f["path"]: f for f in files}


@pytest.mark.asyncio
async def test_ac_two_files_modified_and_added_with_counts(app, auth_headers, repo):
    wt = add_branch(
        repo, "agentweave/worker", worktree=repo / ".agentweave" / "worktrees" / "worker"
    )
    write(wt, "README.md", "one\ntwo\nthree\n")
    write(wt, "notes.txt", "alpha\nbeta\n")
    sha = commit(wt, "Auto-snapshot: worker's turn")
    await seed(runs=[("completed", sha, wt)])

    body = await get(app, auth_headers)

    assert body["state"] == "ok"
    files = by_path(body["turn"])
    assert files["README.md"]["status"] == "M"
    assert (files["README.md"]["added"], files["README.md"]["removed"]) == (2, 0)
    assert files["notes.txt"]["status"] == "A"
    assert (files["notes.txt"]["added"], files["notes.txt"]["removed"]) == (2, 0)


@pytest.mark.asyncio
async def test_ac_switch_last_turn_vs_since_main_and_header(app, auth_headers, repo):
    wt = add_branch(
        repo, "agentweave/worker", worktree=repo / ".agentweave" / "worktrees" / "worker"
    )
    write(wt, "a.txt", "a\n")
    first = commit(wt, "Auto-snapshot: worker's turn")
    write(wt, "b.txt", "b\n")
    second = commit(wt, "Auto-snapshot: worker's turn")
    # Runs start in list order, so the second turn is the most recent.
    await seed(runs=[("completed", first, wt), ("completed", second, wt)])

    body = await get(app, auth_headers)

    assert [f["path"] for f in body["turn"]] == ["b.txt"]
    assert [f["path"] for f in body["since_base"]] == ["a.txt", "b.txt"]
    assert body["branch"] == "agentweave/worker"
    assert body["base"] == "main"


@pytest.mark.asyncio
async def test_ac_task_branch_names_the_task(app, auth_headers, repo):
    task_id = "task-aaaaaaaaaaaa"
    wt = add_branch(
        repo, f"agentweave/task/{task_id}", worktree=repo / ".agentweave" / "tasks" / task_id
    )
    write(wt, "feature.py", "x = 1\n")
    sha = commit(wt, "Auto-snapshot: worker's turn")
    await seed(runs=[("completed", sha, wt)], task=task_id)

    body = await get(app, auth_headers)

    assert body["branch"] == f"agentweave/task/{task_id}"
    assert body["task"]["id"] == task_id
    assert body["task"]["title"] == "Build the thing"
    assert [f["path"] for f in body["turn"]] == ["feature.py"]


@pytest.mark.asyncio
async def test_ac_working_now_while_running_then_under_last_turn(app, auth_headers, repo):
    wt = add_branch(
        repo, "agentweave/worker", worktree=repo / ".agentweave" / "worktrees" / "worker"
    )
    write(wt, "wip.txt", "partial\n")
    await seed(runs=[("running", None, wt)])

    body = await get(app, auth_headers)
    assert body["running"] is True
    assert body["working_now"] == ["wip.txt"]
    assert body["turn"] == []

    sha = commit(wt, "Auto-snapshot: worker's turn")
    async with async_session_factory() as session:
        run = await session.get(Run, "run-ch-0")
        run.status, run.snapshot_commit_sha = "completed", sha
        await session.commit()

    body = await get(app, auth_headers)
    assert body["running"] is False
    assert body["working_now"] == []
    assert [f["path"] for f in body["turn"]] == ["wip.txt"]


@pytest.mark.asyncio
async def test_ac_empty_nothing_changed(app, auth_headers, repo):
    wt = add_branch(
        repo, "agentweave/worker", worktree=repo / ".agentweave" / "worktrees" / "worker"
    )
    await seed(runs=[("completed", None, wt)])

    body = await get(app, auth_headers)

    assert body["state"] == "empty"
    assert body["turn"] == [] and body["since_base"] == []
    assert body["message"] is None


@pytest.mark.asyncio
async def test_ac_empty_no_checkout_says_so_without_an_error(app, auth_headers, repo):
    await seed(agent="reader", conv="conv-ro", read_only=True)
    await seed(conv="conv-never")  # a writing agent whose branch was never made

    for conv in ("conv-ro", "conv-never"):
        body = await get(app, auth_headers, conv=conv)
        assert body["state"] == "no_checkout"
        assert "checkout" in body["message"]
        assert not any(ch.isdigit() for ch in body["message"].replace("agentweave", ""))


@pytest.mark.asyncio
async def test_ac_large_list_fast_binary_marked_and_big_diff_truncated(app, auth_headers, repo):
    wt = add_branch(
        repo, "agentweave/worker", worktree=repo / ".agentweave" / "worktrees" / "worker"
    )
    for i in range(198):
        write(wt, f"many/f{i:03}.txt", f"{i}\n")
    (wt / "blob.bin").write_bytes(bytes(range(256)) * 8)
    write(wt, "big.txt", "".join(f"line {i}\n" for i in range(6000)))
    sha = commit(wt, "Auto-snapshot: worker's turn")
    await seed(runs=[("completed", sha, wt)])

    started = time.monotonic()
    body = await get(app, auth_headers)
    elapsed = time.monotonic() - started

    assert len(body["turn"]) == 200
    assert elapsed < 2.0
    files = by_path(body["turn"])
    assert files["blob.bin"]["binary"] is True

    binary = await app.get(
        f"{URL}/conv-ch/changes/patch", headers=auth_headers, params={"path": "blob.bin"}
    )
    assert binary.json()["binary"] is True and binary.json()["patch"] == ""

    big = await app.get(
        f"{URL}/conv-ch/changes/patch", headers=auth_headers, params={"path": "big.txt"}
    )
    payload = big.json()
    assert payload["truncated"] is True
    assert payload["total_lines"] > 5000
    assert payload["patch"].count("\n") == 5000

    whole = await app.get(
        f"{URL}/conv-ch/changes/patch",
        headers=auth_headers,
        params={"path": "many/f001.txt", "scope": "branch"},
    )
    assert whole.json()["truncated"] is False
    assert "+1" in whole.json()["patch"]


@pytest.mark.asyncio
async def test_unknown_conversation_is_404(app, auth_headers, repo):
    response = await app.get(f"{URL}/conv-missing/changes", headers=auth_headers)
    assert response.status_code == 404
