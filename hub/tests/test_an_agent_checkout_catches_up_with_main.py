"""An agent's own checkout is brought up to main before its turn (F607).

`spec/changes/an-agent-checkout-catches-up-with-main`, against real disposable git repositories. An
agent's branch was cut once and never moved, so a reconcile recorded false "missing" gaps against
shipped code and a later turn could not see a file committed to master. Never destructive: a dirty
tree or a conflict leaves the checkout exactly as it was, and the turn still runs.
"""

import subprocess
from pathlib import Path

import pytest

from hub import worktrees

from .test_task_worktrees import _git, _init_repo

AGENT = "catcher"

#: Captured at import, before conftest's `_no_real_worktree_provision` stubs the attribute to
#: return the repo root -- under that stub every assertion here would hold trivially.
_REAL_RESOLVE_AGENT_WORKSPACE = worktrees.resolve_agent_workspace


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    return _init_repo(tmp_path / "repo")


def _commit(checkout: Path, name: str, body: str) -> str:
    (checkout / name).write_text(body)
    _git(checkout, "add", "-A")
    _git(checkout, "commit", "-q", "-m", f"add {name}")
    return _git(checkout, "rev-parse", "HEAD").stdout.strip()


def _contains(checkout: Path, sha: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=checkout, capture_output=True
        ).returncode
        == 0
    )


def _turn(repo: Path, config=None) -> Path:
    return worktrees.resolve_turn_workspace(repo, AGENT, config or {}, catch_up_to="HEAD")


def test_a_worktree_behind_main_is_fast_forwarded(repo):
    worktree = _turn(repo)
    assert worktree != repo, "the real provisioning is in use"
    landed = _commit(repo, "RELEASE.txt", "codename\n")

    assert _turn(repo) == worktree
    assert _contains(worktree, landed)
    assert (worktree / "RELEASE.txt").read_text() == "codename\n"
    assert _git(worktree, "rev-parse", "HEAD").stdout.strip() == landed, "a fast-forward, no merge"


def test_a_worktree_with_its_own_commits_takes_main_in_by_merge(repo):
    worktree = _turn(repo)
    own = _commit(worktree, "notes.md", "mine\n")
    landed = _commit(repo, "RELEASE.txt", "codename\n")

    _turn(repo)

    assert _contains(worktree, landed) and _contains(worktree, own)
    assert (worktree / "notes.md").read_text() == "mine\n"


def test_uncommitted_work_is_left_exactly_as_it_was(repo):
    worktree = _turn(repo)
    before = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    (worktree / "draft.txt").write_text("unsaved\n")
    landed = _commit(repo, "RELEASE.txt", "codename\n")

    _turn(repo)

    assert not _contains(worktree, landed)
    assert _git(worktree, "rev-parse", "HEAD").stdout.strip() == before
    assert (worktree / "draft.txt").read_text() == "unsaved\n"


def test_a_conflict_is_aborted_and_the_turn_still_gets_its_checkout(repo):
    worktree = _turn(repo)
    _commit(worktree, "README.md", "the agent's version\n")
    before = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    _commit(repo, "README.md", "main's version\n")

    assert _turn(repo) == worktree
    assert _git(worktree, "rev-parse", "HEAD").stdout.strip() == before
    assert (worktree / "README.md").read_text() == "the agent's version\n"
    assert _git(worktree, "status", "--porcelain").stdout.strip() == "", "no half-done merge"


def test_a_read_only_agent_shares_the_project_checkout_untouched(repo):
    assert _turn(repo, {"read_only": True}) == repo


def test_an_unresolvable_base_changes_nothing(repo):
    worktree = _turn(repo)
    before = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    assert worktrees.catch_up_agent_worktree(repo, worktree, "no-such-branch") is not None
    assert _git(worktree, "rev-parse", "HEAD").stdout.strip() == before
