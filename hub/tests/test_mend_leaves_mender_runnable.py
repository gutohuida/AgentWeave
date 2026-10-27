"""A mend leaves the mender runnable (slice A, `worktrees-never-destroy-or-strand-anything`).

The mender used to mend in its own checkout: `git checkout -B mend/<id>` there, never switched back,
so every later mender turn was refused with "not the registered git worktree for
refs/heads/agentweave/mender" -- which misnames the cause: the directory is registered, just on
another branch. The operator switched it back by hand on 2026-10-23.

Now the Hub makes a scratch checkout for the mend, inside the mender's workspace, and removes it
when the mend lands or the stall ends; and a mender left on another branch is put back where that
loses nothing, or refused with both branches named.
"""

# ruff: noqa: F811  (`builder` is an imported fixture, then a test argument)

import re
from pathlib import Path

import pytest

from hub import stalls, worktrees
from hub.db.engine import async_session_factory

from .test_a_stalled_project_wakes_the_mender import (  # noqa: F401  (builder is a fixture)
    MENDER_LAND,
    MENDER_STALLS,
    RETRY,
    all_stalls,
    approved_on_a_dirty_checkout,
    builder,
    mender_run,
)
from .test_task_integration import commits_on, git, integrations

MENDER = stalls.MENDER


def _branch_of(checkout: Path) -> str:
    return git(checkout, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def _registered(repo: Path, path: Path) -> bool:
    listing = git(repo, "worktree", "list", "--porcelain").stdout.replace("\\", "/")
    return str(path).replace("\\", "/") in listing


async def _conflicting_task(app, auth_headers, builder, tmp_path):
    """Approved work whose merge fails: main moved under it. Returns (task, work, stall)."""
    task, work = await approved_on_a_dirty_checkout(app, auth_headers, builder, tmp_path)
    git(tmp_path, "commit", "-q", "-am", "the operator commits their notes")
    (tmp_path / "README.md").write_text("main's own line\n", encoding="utf-8")
    git(tmp_path, "commit", "-q", "-am", "someone else's change")
    assert (await app.post(RETRY.format(task), headers=auth_headers)).status_code == 200
    await stalls.drain()
    newest = (await integrations(app, auth_headers, task))[-1]
    assert newest["outcome"] == "failed", newest["reason"]
    failed = [row for row in await all_stalls() if row.cause == "integration_failed"]
    assert failed
    return task, work, failed[0]


async def _scratch_path_the_brief_names(stall) -> Path:
    async with async_session_factory() as session:
        brief = await stalls.brief(session, stall)
    named = re.search(r"it is ready at (.+?), on branch mend/", brief)
    assert named, f"the brief names no scratch checkout for the mend:\n{brief}"
    assert (
        "git checkout -B mend" not in brief
    ), "the brief still sends the mender to its own checkout"
    return Path(named.group(1))


def _mend_in(scratch: Path, work: str) -> str:
    """What a mender does there: main merged into the work, the conflict resolved, committed."""
    assert (scratch / "README.md").read_text(encoding="utf-8") == "the task's line\n"
    git(scratch, "merge", "-q", "main", "--no-commit", "--no-ff")  # conflicts; resolved below
    (scratch / "README.md").write_text("the task's line\n", encoding="utf-8")
    git(scratch, "add", "README.md")
    git(scratch, "commit", "-q", "-m", "mend: keep the task's line")
    return git(scratch, "rev-parse", "HEAD").stdout.strip()


@pytest.mark.asyncio
async def test_a_landed_mend_leaves_the_mender_runnable_and_nothing_behind(
    app, auth_headers, builder, tmp_path
):
    task, work, stall = await _conflicting_task(app, auth_headers, builder, tmp_path)
    mender = await mender_run()

    scratch = await _scratch_path_the_brief_names(stall)
    own = worktrees.worktree_path(tmp_path, MENDER)
    assert scratch.is_dir() and own in scratch.parents  # inside the mender's workspace
    assert _branch_of(scratch) == f"mend/{task}"
    assert _branch_of(own) == f"agentweave/{MENDER}"
    assert git(own, "status", "--porcelain").stdout.strip() == "", "the scratch checkout is hidden"

    resolution = _mend_in(scratch, work)
    assert _branch_of(own) == f"agentweave/{MENDER}", "mending moved the mender's own checkout"

    landed = await app.post(MENDER_LAND.format(task), json={"commit": resolution}, headers=mender)
    await stalls.drain()

    assert landed.status_code == 200, landed.text
    assert [r["outcome"] for r in landed.json()["results"]] == ["merged"]
    assert resolution in commits_on(tmp_path, "main")
    # abandoned-mend-leaves-nothing, for the mend that landed
    assert not scratch.exists()
    assert not _registered(tmp_path, scratch)
    # mend-leaves-mender-runnable: the next turn's preparation
    assert worktrees.ensure_worktree(tmp_path, MENDER) == own
    assert _branch_of(own) == f"agentweave/{MENDER}"


@pytest.mark.asyncio
async def test_an_abandoned_mend_leaves_nothing_behind(app, auth_headers, builder, tmp_path):
    task, work, stall = await _conflicting_task(app, auth_headers, builder, tmp_path)
    mender = await mender_run()
    scratch = await _scratch_path_the_brief_names(stall)
    (scratch / "README.md").write_text("half-resolved, never committed\n", encoding="utf-8")

    # The task has two open stalls (the skipped merge, then the failed one), and the mender works
    # one thread across them: the checkout stays until the last of them is ended.
    open_stalls = [row for row in await all_stalls() if row.ended_at is None]
    assert len(open_stalls) == 2
    for row in open_stalls:
        assert scratch.is_dir()
        ended = await app.post(
            f"{MENDER_STALLS}/{row.id}/end",
            json={"outcome": "gave_up", "summary": "The conflict needs the operator."},
            headers=mender,
        )
        assert ended.status_code == 200, ended.text
    await stalls.drain()

    own = worktrees.worktree_path(tmp_path, MENDER)
    assert not scratch.exists()
    assert not _registered(tmp_path, scratch)
    assert worktrees.ensure_worktree(tmp_path, MENDER) == own
    assert _branch_of(own) == f"agentweave/{MENDER}"


@pytest.mark.asyncio
async def test_a_refused_landing_keeps_the_scratch_checkout_for_the_next_attempt(
    app, auth_headers, builder, tmp_path
):
    task, work, stall = await _conflicting_task(app, auth_headers, builder, tmp_path)
    mender = await mender_run()
    scratch = await _scratch_path_the_brief_names(stall)

    # A commit that drops the task's work is refused, and the mender tries again from the same place.
    refused = await app.post(
        MENDER_LAND.format(task), json={"commit": commits_on(tmp_path, "main")[0]}, headers=mender
    )

    assert refused.status_code == 409, refused.text
    assert scratch.is_dir()


# --- a mender found on another branch ------------------------------------------------------------


@pytest.fixture
def repo(tmp_path) -> Path:
    from .test_worktrees import _init_repo

    return _init_repo(tmp_path / "repo")


def _leave_on_a_mend_branch(repo: Path, *, merged: bool) -> Path:
    """What the old brief did to the mender's checkout: a mend branch with a commit, left checked out."""
    own = worktrees.ensure_worktree(repo, MENDER)
    git(own, "checkout", "-q", "-b", "mend/task-ab12cd34ef56")
    (own / "mended.txt").write_text("the mend\n", encoding="utf-8")
    git(own, "add", "mended.txt")
    git(own, "commit", "-q", "-m", "mend")
    if merged:
        git(repo, "merge", "-q", "--ff-only", "mend/task-ab12cd34ef56")
    return own


def test_a_mender_left_on_a_merged_mend_branch_is_switched_back(repo):
    own = _leave_on_a_mend_branch(repo, merged=True)
    assert _branch_of(own) == "mend/task-ab12cd34ef56"

    assert worktrees.ensure_worktree(repo, MENDER) == own

    assert _branch_of(own) == f"agentweave/{MENDER}"


def test_the_refusal_for_unmerged_work_names_both_branches(repo):
    own = _leave_on_a_mend_branch(repo, merged=False)

    with pytest.raises(worktrees.IsolationUnavailableError) as caught:
        worktrees.ensure_worktree(repo, MENDER)

    message = str(caught.value)
    assert "mend/task-ab12cd34ef56" in message
    assert f"agentweave/{MENDER}" in message
    assert "not the registered git worktree" not in message
    assert f"git -C {own} switch" in message
    assert _branch_of(own) == "mend/task-ab12cd34ef56", "unmerged work was left where it was"


def test_a_dirty_checkout_on_another_branch_is_not_switched(repo):
    own = _leave_on_a_mend_branch(repo, merged=True)
    (own / "mended.txt").write_text("edited since\n", encoding="utf-8")

    with pytest.raises(worktrees.IsolationUnavailableError) as caught:
        worktrees.ensure_worktree(repo, MENDER)

    assert "uncommitted" in str(caught.value)
    assert _branch_of(own) == "mend/task-ab12cd34ef56"


def test_a_directory_that_is_no_worktree_still_gets_the_old_remedy(repo):
    blocked = worktrees.worktree_path(repo, MENDER)
    blocked.mkdir(parents=True)
    (blocked / "left-behind.txt").write_text("not a worktree\n", encoding="utf-8")

    with pytest.raises(worktrees.IsolationUnavailableError) as caught:
        worktrees.ensure_worktree(repo, MENDER)

    assert "not the registered git worktree" in str(caught.value)
