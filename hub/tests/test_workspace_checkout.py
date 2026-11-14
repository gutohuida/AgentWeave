"""The workspace listing and file routes for a conversation's agent checkout (SPSFT-2).

Same fixtures as the Changes route test: `conftest` roots the project at `tmp_path`.
"""

import os
import subprocess

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Conversation, Project, Run  # noqa: F401
from tests.test_changes_route import P, add_branch, commit, seed, write  # noqa: F401
from tests.test_changes_route import repo as _repo

BASE = f"/api/v1/projects/{P}/workspace"
WT = ".agentweave/worktrees/worker"


async def paths(app, auth_headers, conv="conv-ch", **params):
    r = await app.get(
        f"{BASE}/paths", headers=auth_headers, params={"conversation_id": conv, **params}
    )
    assert r.status_code == 200, r.text
    return r.json()


async def file(app, auth_headers, path, conv="conv-ch", location="worktree"):
    return await app.get(
        f"{BASE}/file",
        headers=auth_headers,
        params={"path": path, "conversation_id": conv, "location": location},
    )


repo = _repo


def worker_wt(repo):
    return add_branch(repo, "agentweave/worker", worktree=repo / WT)


@pytest.mark.asyncio
async def test_ac_switch_worktree_file_not_in_root(app, auth_headers, repo):
    wt = worker_wt(repo)
    write(wt, "only_here.txt", "x\n")
    await seed(runs=[("completed", None, wt)])

    w = await paths(app, auth_headers)
    r = await paths(app, auth_headers, location="root")

    assert w["location"] == "worktree" and w["has_checkout"] is True
    assert "only_here.txt" in w["paths"]
    assert r["location"] == "root" and r["has_checkout"] is True
    assert "only_here.txt" not in r["paths"]


@pytest.mark.asyncio
async def test_ac_task_checkout_same_as_changes(app, auth_headers, repo):
    task_id = "task-aaaaaaaaaaaa"
    wt = add_branch(
        repo, f"agentweave/task/{task_id}", worktree=repo / ".agentweave" / "tasks" / task_id
    )
    write(wt, "feature.py", "x = 1\n")
    sha = commit(wt, "Auto-snapshot: worker's turn")
    await seed(runs=[("completed", sha, wt)], task=task_id)

    listing = await paths(app, auth_headers)
    changes = (
        await app.get(f"/api/v1/projects/{P}/conversations/conv-ch/changes", headers=auth_headers)
    ).json()

    assert listing["branch"] == changes["branch"] == f"agentweave/task/{task_id}"
    assert "feature.py" in listing["paths"]


@pytest.mark.asyncio
async def test_ac_no_checkout_read_only_and_not_created(app, auth_headers, repo):
    await seed(agent="reader", conv="conv-ro", read_only=True)
    ro = await paths(app, auth_headers, conv="conv-ro")
    assert ro["state"] == "no_checkout" and ro["location"] == "root"
    assert ro["has_checkout"] is False and "README.md" in ro["paths"]
    assert "read-only" in ro["message"]

    await seed(agent="fresh", conv="conv-fresh")
    fresh = await paths(app, auth_headers, conv="conv-fresh", location="worktree")
    assert fresh["state"] == "no_checkout" and fresh["location"] == "root"
    assert "no checkout yet" in fresh["message"] and "README.md" in fresh["paths"]
    assert not (repo / ".agentweave" / "worktrees" / "fresh").exists()


@pytest.mark.asyncio
async def test_ac_uncommitted_untracked_listed_ignored_not(app, auth_headers, repo):
    (repo / ".gitignore").write_text("*.log\n")
    commit(repo, "ignore")
    wt = worker_wt(repo)
    write(wt, "docs/deep/nested.md", "n\n")
    commit(wt, "nested")
    write(wt, "fresh.txt", "new\n")
    write(wt, "debug.log", "noise\n")
    await seed(runs=[("completed", None, wt)])

    got = (await paths(app, auth_headers))["paths"]

    assert "fresh.txt" in got and "docs/deep/nested.md" in got
    assert "debug.log" not in got


@pytest.mark.asyncio
async def test_ac_guards_each_refused(app, auth_headers, repo, tmp_path_factory):
    wt = worker_wt(repo)
    write(wt, "ok.txt", "fine\n")
    other = add_branch(repo, "agentweave/other", worktree=repo / ".agentweave/worktrees/other")
    write(other, "theirs.txt", "not yours\n")
    outside = tmp_path_factory.mktemp("outside")
    (outside / "secret.txt").write_text("SECRET\n")
    link = wt / "escape"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True)
    else:
        link.symlink_to(outside, target_is_directory=True)
    await seed(runs=[("completed", None, wt)])

    assert (await file(app, auth_headers, "ok.txt")).status_code == 200
    for bad in (
        "not-listed.txt",
        "escape/secret.txt",
        ".agentweave/worktrees/other/theirs.txt",
        "theirs.txt",
    ):
        r = await file(app, auth_headers, bad)
        assert r.status_code == 404, (bad, r.text)
        assert "SECRET" not in r.text and "not yours" not in r.text

    # Another project's conversation.
    async with async_session_factory() as session:
        session.add(Project(id="proj-other", name="o", working_directory="x", path_key="x"))
        await session.flush()
        session.add(
            Conversation(
                id="conv-foreign",
                project_id="proj-other",
                agent="worker",
                lifecycle="open",
                origin="operator",
            )
        )
        await session.commit()
    r = await file(app, auth_headers, "ok.txt", conv="conv-foreign")
    assert r.status_code == 404 and "fine" not in r.text


@pytest.mark.asyncio
async def test_ac_large_and_binary_match_root(app, auth_headers, repo):
    wt = worker_wt(repo)
    write(wt, "big.txt", "a" * (2 * 1024 * 1024))
    (wt / "blob.bin").write_bytes(b"\x00\x01\x02")
    await seed(runs=[("completed", None, wt)])

    assert (await file(app, auth_headers, "big.txt")).status_code == 413
    r = await file(app, auth_headers, "blob.bin")
    assert r.status_code == 200 and r.json()["binary"] is True and r.json()["content"] is None


@pytest.mark.asyncio
async def test_ac_changed_only_equals_since_main(app, auth_headers, repo):
    wt = worker_wt(repo)
    write(wt, "added.txt", "a\n")
    write(wt, "README.md", "one\nmore\n")
    (wt / "src" / "app.py").unlink()
    sha = commit(wt, "Auto-snapshot: worker's turn")
    await seed(runs=[("completed", sha, wt)])

    listing = await paths(app, auth_headers)
    changes = (
        await app.get(f"/api/v1/projects/{P}/conversations/conv-ch/changes", headers=auth_headers)
    ).json()

    assert listing["changed"] == {"added.txt": "A", "README.md": "M", "src/app.py": "D"}
    assert listing["changed"] == {f["path"]: f["status"] for f in changes["since_base"]}
    assert "src/app.py" in listing["paths"]  # a deleted file is still listed
    assert (await file(app, auth_headers, "src/app.py")).status_code == 404
