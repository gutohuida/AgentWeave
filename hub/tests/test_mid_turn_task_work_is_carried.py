"""Work from a turn that claimed its task mid-turn reaches the task (F603).

`spec/changes/work-from-a-mid-turn-claim-reaches-the-task`, against real disposable repositories. A
turn ran in the agent's own worktree, claimed a task partway through and fixed it there, while the
review and Land read the task's own branch -- which never received the fix.
"""

from pathlib import Path

import pytest

from hub import worktrees
from hub.worktrees import ensure_task_worktree

from .test_task_worktrees import _git, _init_repo

AGENT = "carrier"
TASK = "task-c0ffee000001"

#: Captured at import, before conftest's autouse stubs replace the module attributes.
_REAL_RESOLVE_AGENT_WORKSPACE = worktrees.resolve_agent_workspace
_REAL_ENSURE_TASK_WORKTREE = ensure_task_worktree


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    monkeypatch.setattr(worktrees, "ensure_task_worktree", _REAL_ENSURE_TASK_WORKTREE)
    return _init_repo(tmp_path / "repo")


def _agent_worktree(repo: Path) -> Path:
    worktree = worktrees.resolve_agent_workspace(repo, AGENT, {})
    assert worktree != repo
    return worktree


def _commit(checkout: Path, name: str, body: str) -> str:
    (checkout / name).write_text(body)
    _git(checkout, "add", "-A")
    _git(checkout, "commit", "-q", "-m", f"add {name}")
    return _git(checkout, "rev-parse", "HEAD").stdout.strip()


def _on_branch(repo: Path, name: str):
    shown = _git_ok(repo, "show", f"{worktrees.task_branch_name(TASK)}:{name}")
    return shown.stdout if shown.returncode == 0 else None


def _git_ok(repo: Path, *args):
    import subprocess

    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def test_the_turns_commits_reach_a_task_branch_that_did_not_exist(repo):
    worktree = _agent_worktree(repo)
    start = worktrees.head_of(worktree)
    _commit(worktree, "FIX.txt", "fixed\n")

    assert worktrees.carry_turn_work_to_task(repo, worktree, start, TASK, "HEAD") is None
    assert _on_branch(repo, "FIX.txt") == "fixed\n"


def test_only_this_turns_commits_are_carried_not_the_agents_earlier_work(repo):
    """A cherry-pick of the turn's range, never a merge of the agent's branch (F58)."""
    worktree = _agent_worktree(repo)
    _commit(worktree, "EARLIER.txt", "another task's work\n")
    start = worktrees.head_of(worktree)
    _commit(worktree, "FIX.txt", "fixed\n")

    assert worktrees.carry_turn_work_to_task(repo, worktree, start, TASK, "HEAD") is None
    assert _on_branch(repo, "FIX.txt") == "fixed\n"
    assert _on_branch(repo, "EARLIER.txt") is None


def test_a_turn_that_committed_nothing_carries_nothing(repo):
    worktree = _agent_worktree(repo)
    start = worktrees.head_of(worktree)
    assert worktrees.carry_turn_work_to_task(repo, worktree, start, TASK, "HEAD") is None
    assert _git_ok(repo, "rev-parse", "--verify", worktrees.task_branch_name(TASK)).returncode != 0


def test_a_dirty_task_checkout_is_left_as_it_was(repo):
    worktree = _agent_worktree(repo)
    checkout = ensure_task_worktree(repo, TASK, "HEAD")
    (checkout / "draft.txt").write_text("unsaved\n")
    before = worktrees.head_of(checkout)
    start = worktrees.head_of(worktree)
    _commit(worktree, "FIX.txt", "fixed\n")

    problem = worktrees.carry_turn_work_to_task(repo, worktree, start, TASK, "HEAD")

    assert problem is not None and "uncommitted" in problem
    assert worktrees.head_of(checkout) == before
    assert (checkout / "draft.txt").read_text() == "unsaved\n"


def test_a_conflicting_pick_leaves_the_task_branch_as_it_was(repo):
    worktree = _agent_worktree(repo)
    checkout = ensure_task_worktree(repo, TASK, "HEAD")
    _commit(checkout, "FIX.txt", "the task's own version\n")
    before = worktrees.head_of(checkout)
    start = worktrees.head_of(worktree)
    _commit(worktree, "FIX.txt", "the turn's version\n")

    problem = worktrees.carry_turn_work_to_task(repo, worktree, start, TASK, "HEAD")

    assert problem is not None and "conflicts" in problem
    assert worktrees.head_of(checkout) == before
    assert (checkout / "FIX.txt").read_text() == "the task's own version\n"
    assert _git_ok(checkout, "status", "--porcelain").stdout.strip() == ""
