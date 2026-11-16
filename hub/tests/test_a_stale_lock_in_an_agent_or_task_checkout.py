"""A stale `index.lock` in an agent's or task's checkout is cleared while no run of it is live
(F1197 follow-up, AW-152).

AW-149 cleared a killed git's lock in a review checkout. The same lock in an agent's or task's
checkout blocked the Hub's own git there -- the switch back, the catch-up merges, the turn's
snapshot -- and then the next turn's first commit. Agents run their own git in these checkouts, so
the Hub clears a lock there only when no run of that agent or task is live, never in the operator's
main checkout, and names a lock it may not clear in a stall.

Real, disposable git repositories under `tmp_path`. conftest's autouse
`_no_real_worktree_provision` stubs the provisioning functions; the real ones are captured at import.
"""

import os
import time
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import run_liveness, stalls, worktrees
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, Stall

from .test_task_worktrees import _commit_on_new_branch, _git, _init_repo

_REAL_RESOLVE_AGENT_WORKSPACE = worktrees.resolve_agent_workspace
_REAL_ENSURE_TASK_WORKTREE = worktrees.ensure_task_worktree

AGENT = "builder"
TASK = "task-b0b0b0b0b0b0"
PREREQUISITE = "task-a0a0a0a0a0a0"


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    monkeypatch.setattr(worktrees, "ensure_task_worktree", _REAL_ENSURE_TASK_WORKTREE)
    return _init_repo(tmp_path / "repo")


def _lock_of(checkout: Path) -> Path:
    return Path(_git(checkout, "rev-parse", "--absolute-git-dir").stdout.strip()) / "index.lock"


def _stale_lock(checkout: Path) -> Path:
    """What F1197 found live: a zero-byte lock no git process was holding, older than any git the
    Hub starts can live."""
    lock = _lock_of(checkout)
    lock.write_bytes(b"")
    then = time.time() - worktrees.STALE_INDEX_LOCK_SECONDS - 5
    os.utime(lock, (then, then))
    return lock


def _contains(checkout: Path, sha: str) -> bool:
    import subprocess

    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=checkout, capture_output=True
        ).returncode
        == 0
    )


def _commit_on_main(repo: Path, name: str) -> str:
    (repo / name).write_text(f"{name}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"add {name}")
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


# --- the agent's own checkout ---------------------------------------------------------------------


def test_the_agent_checkout_catches_up_past_a_stale_lock_when_no_run_is_live(repo):
    checkout = worktrees.resolve_turn_workspace(repo, AGENT, {}).path
    lock = _stale_lock(checkout)
    ahead = _commit_on_main(repo, "later.txt")

    worktrees.resolve_turn_workspace(repo, AGENT, {}, catch_up_to="HEAD", clear_stale_lock=True)

    assert not lock.exists()
    assert _contains(checkout, ahead)


def test_a_live_runs_lock_in_the_agent_checkout_is_left_alone(repo):
    checkout = worktrees.resolve_turn_workspace(repo, AGENT, {}).path
    lock = _stale_lock(checkout)
    ahead = _commit_on_main(repo, "later.txt")

    worktrees.resolve_turn_workspace(repo, AGENT, {}, catch_up_to="HEAD", clear_stale_lock=False)

    assert lock.exists()
    assert not _contains(checkout, ahead)


def test_the_agent_checkout_is_switched_back_past_a_stale_lock(repo):
    checkout = worktrees.resolve_turn_workspace(repo, AGENT, {}).path
    _git(checkout, "checkout", "-q", "-b", "mend/task-x")
    lock = _stale_lock(checkout)

    worktrees.resolve_turn_workspace(repo, AGENT, {}, clear_stale_lock=True)

    assert not lock.exists()
    branch = _git(checkout, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert branch == worktrees.branch_name(AGENT)


# --- a task's checkout ----------------------------------------------------------------------------


def _task_turn(repo: Path, approved=(), clear_stale_lock=False) -> Path:
    return worktrees.resolve_turn_workspace(
        repo,
        AGENT,
        {},
        task_id=TASK,
        base="main",
        approved=approved,
        clear_stale_lock=clear_stale_lock,
    ).path


def test_a_task_checkout_takes_in_approved_work_past_a_stale_lock(repo):
    checkout = _task_turn(repo)
    (checkout / "own.txt").write_text("the task's own work\n")
    lock = _stale_lock(checkout)
    prerequisite = _commit_on_new_branch(repo, "agentweave/task/" + PREREQUISITE, "a.txt", "a\n")

    _task_turn(repo, approved=[(PREREQUISITE, prerequisite)], clear_stale_lock=True)

    assert not lock.exists()
    assert _contains(checkout, prerequisite)
    # The uncommitted work was committed before the merge, not lost to it.
    assert _git(checkout, "status", "--porcelain").stdout.strip() == ""
    assert (checkout / "own.txt").exists()


def test_a_young_lock_is_refused_by_name_and_kept(repo):
    checkout = _task_turn(repo)
    lock = _lock_of(checkout)
    lock.write_bytes(b"")  # young: a live git's, as far as the Hub can tell

    with pytest.raises(worktrees.CheckoutLockedError) as excinfo:
        _task_turn(repo, clear_stale_lock=True)

    assert lock.exists()
    assert excinfo.value.lock == lock
    assert str(lock) in str(excinfo.value)


def test_the_turns_snapshot_commits_past_a_stale_lock(repo):
    checkout = _task_turn(repo)
    (checkout / "work.txt").write_text("work\n")
    lock = _stale_lock(checkout)

    sha = worktrees.snapshot_worktree(checkout, AGENT, clear_stale_lock=True)

    assert sha is not None
    assert not lock.exists()
    assert _git(checkout, "status", "--porcelain").stdout.strip() == ""


def test_the_snapshot_leaves_a_live_runs_lock(repo):
    checkout = _task_turn(repo)
    (checkout / "work.txt").write_text("work\n")
    lock = _stale_lock(checkout)

    with pytest.raises(worktrees.GitCommandError):
        worktrees.snapshot_worktree(checkout, AGENT, clear_stale_lock=False)

    assert lock.exists()


def test_the_main_checkouts_lock_is_never_touched(repo):
    checkout = _task_turn(repo)
    (checkout / "work.txt").write_text("work\n")
    main_lock = repo / ".git" / "index.lock"
    main_lock.write_bytes(b"")
    then = time.time() - worktrees.STALE_INDEX_LOCK_SECONDS - 5
    os.utime(main_lock, (then, then))

    worktrees.clear_stale_index_lock(repo)
    _task_turn(repo, clear_stale_lock=True)
    worktrees.snapshot_worktree(checkout, AGENT, clear_stale_lock=True)

    assert main_lock.exists()


# --- the Hub decides "no run is live" -------------------------------------------------------------


async def _add_run(run_id: str, *, agent: str, task_id=None, status="running") -> None:
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status=status,
                turn_depth=0,
                task_id=task_id,
                capability_token_hash=hash_run_token(f"aw_{run_id}-secret"),
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_a_running_turn_of_the_agent_or_on_the_task_is_live(app):
    await _add_run("run-own", agent=AGENT, task_id=TASK)
    await _add_run("run-done", agent="other", task_id="task-c0c0c0c0c0c0", status="completed")

    async with async_session_factory() as session:
        ask = run_liveness.has_running_turn
        assert await ask(session, "proj-test", agent=AGENT)
        assert await ask(session, "proj-test", agent="someone", task_id=TASK)
        # A turn is never in its own way: the run whose snapshot this is is excluded.
        assert not await ask(
            session, "proj-test", agent=AGENT, task_id=TASK, excluding_run_id="run-own"
        )
        assert not await ask(session, "proj-test", agent="other", task_id="task-c0c0c0c0c0c0")
        assert not await ask(session, "other-project", agent=AGENT, task_id=TASK)


@pytest.mark.asyncio
async def test_a_turn_ending_clears_the_stale_lock_only_when_no_other_run_is_live(app, repo):
    from hub.api.v1.agent_trigger import _snapshot_turn

    checkout = _task_turn(repo)
    (checkout / "work.txt").write_text("work\n")
    lock = _stale_lock(checkout)
    await _add_run("run-ending", agent=AGENT, task_id=TASK)
    await _add_run("run-other", agent="reviewer", task_id=TASK)

    kept = await _snapshot_turn(
        project_id="proj-test", agent=AGENT, run_id="run-ending", worktree=checkout
    )
    assert kept is None
    assert lock.exists()

    async with async_session_factory() as session:
        other = await session.get(Run, "run-other")
        other.status = "completed"
        await session.commit()

    sha = await _snapshot_turn(
        project_id="proj-test", agent=AGENT, run_id="run-ending", worktree=checkout
    )
    assert sha is not None
    assert not lock.exists()


@pytest.mark.asyncio
async def test_a_lock_the_hub_may_not_clear_raises_a_stall_naming_it(app, repo, monkeypatch):
    from hub.api.v1.agent_trigger import _snapshot_turn

    async def _no_wake(db, stall) -> bool:
        return False

    monkeypatch.setattr(stalls, "wake", _no_wake)
    checkout = _task_turn(repo)
    (checkout / "work.txt").write_text("work\n")
    lock = _lock_of(checkout)
    lock.write_bytes(b"")  # young

    sha = await _snapshot_turn(
        project_id="proj-test", agent=AGENT, run_id="run-ending", worktree=checkout
    )
    await stalls.drain()

    assert sha is None
    assert lock.exists()
    async with async_session_factory() as session:
        stall = (await session.execute(select(Stall))).scalar_one()
    assert stall.key == f"delivery_refused:{TASK}"
    assert stall.task_id == TASK
    assert str(lock) in stall.reason
