"""Tests for the review checkout — `2026-08-23-a-reviewer-can-see-the-work`, task group 1.

Real, disposable git repositories under `tmp_path`, never the real AgentWeave checkout. The named
imports below are deliberate for the same reason `test_worktrees.py` does it: conftest's autouse
`_no_real_worktree_provision` patches the module *attributes*, and a name bound here at collection
time is a separate reference to the real function, unaffected by that patch.
"""

import subprocess
from pathlib import Path

import pytest

from hub import worktrees
from hub.worktrees import (
    ensure_review_checkout,
    existing_review_checkout,
    release_review_checkout,
    release_worktree,
    resolve_review_commit,
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "shared.txt").write_text("base\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _commit_on_branch(repo: Path, branch: str, filename: str, body: str) -> str:
    """Commit *filename* on *branch* and return to where we were. Returns the new SHA.

    This is how the interesting case is built: work that exists on an author's branch and **not**
    on main, which is exactly what a reviewer cannot see today.
    """
    previous = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    _git(repo, "checkout", "-q", "-b", branch)
    (repo / filename).write_text(body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"work on {branch}")
    sha = _head(repo)
    _git(repo, "checkout", "-q", previous)
    return sha


@pytest.fixture
def repo(tmp_path) -> Path:
    return _init_repo(tmp_path / "repo")


# --------------------------------------------------------------------------------------
# task 1.1 — review_path
# --------------------------------------------------------------------------------------


def test_review_path_is_under_agentweave_reviews(repo):
    assert worktrees.review_path(repo, "critic") == repo / ".agentweave" / "reviews" / "critic"


def test_review_path_validates_the_agent_name_like_worktree_path(repo):
    for bad in ("../escape", "has space", "", "a" * 33, "user"):
        with pytest.raises(ValueError):
            worktrees.review_path(repo, bad)


def test_review_path_is_pure_and_provisions_nothing(repo):
    worktrees.review_path(repo, "critic")
    assert not (repo / ".agentweave" / "reviews").exists()


# --------------------------------------------------------------------------------------
# task 1.5 — created detached; re-pointed rather than duplicated; unknown sha refused
# --------------------------------------------------------------------------------------


def test_review_checkout_is_created_detached_at_the_named_commit(repo):
    sha = _commit_on_branch(repo, "agentweave/builder", "only_on_branch.txt", "author's work\n")

    path = ensure_review_checkout(repo, "critic", sha)

    assert path == repo / ".agentweave" / "reviews" / "critic"
    assert _head(path) == sha
    # Detached: `git symbolic-ref HEAD` fails, and `--abbrev-ref HEAD` reports HEAD rather
    # than a branch name. This is design D2 — the environment states the reviewing role.
    assert _git(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "HEAD"
    symbolic = subprocess.run(
        ["git", "symbolic-ref", "HEAD"], cwd=path, capture_output=True, text=True, timeout=30
    )
    assert symbolic.returncode != 0


def test_the_reviewer_can_read_a_file_that_does_not_exist_on_main(repo):
    """The assertion that distinguishes this change from doing nothing."""
    sha = _commit_on_branch(repo, "agentweave/builder", "only_on_branch.txt", "author's work\n")

    path = ensure_review_checkout(repo, "critic", sha)

    assert not (repo / "only_on_branch.txt").exists()
    assert (path / "only_on_branch.txt").read_text() == "author's work\n"


def test_a_second_review_repoints_the_same_directory_rather_than_duplicating_it(repo):
    first = _commit_on_branch(repo, "agentweave/builder", "one.txt", "first\n")
    second = _commit_on_branch(repo, "agentweave/other", "two.txt", "second\n")

    path_one = ensure_review_checkout(repo, "critic", first)
    path_two = ensure_review_checkout(repo, "critic", second)

    assert path_one == path_two
    assert _head(path_two) == second
    assert (path_two / "two.txt").exists()
    assert not (path_two / "one.txt").exists()
    # Bounded by the roster, not by the number of reviews (design D3).
    assert [p.name for p in (repo / ".agentweave" / "reviews").iterdir()] == ["critic"]


def test_the_number_of_review_checkouts_is_bounded_by_the_agents_that_reviewed(repo):
    sha = _commit_on_branch(repo, "agentweave/builder", "one.txt", "first\n")

    for _ in range(3):
        ensure_review_checkout(repo, "critic", sha)
        ensure_review_checkout(repo, "auditor", sha)

    names = sorted(p.name for p in (repo / ".agentweave" / "reviews").iterdir())
    assert names == ["auditor", "critic"]


def test_a_modified_tracked_file_does_not_block_the_next_review(repo):
    first = _commit_on_branch(repo, "agentweave/builder", "one.txt", "first\n")
    second = _commit_on_branch(repo, "agentweave/other", "two.txt", "second\n")
    path = ensure_review_checkout(repo, "critic", first)
    (path / "shared.txt").write_text("a reviewer scribbled here\n")

    ensure_review_checkout(repo, "critic", second)

    assert _head(path) == second
    assert (path / "shared.txt").read_text() == "base\n"


def test_an_untracked_scratch_file_survives_a_repoint(repo):
    first = _commit_on_branch(repo, "agentweave/builder", "one.txt", "first\n")
    second = _commit_on_branch(repo, "agentweave/other", "two.txt", "second\n")
    path = ensure_review_checkout(repo, "critic", first)
    (path / "notes.md").write_text("what I found\n")

    ensure_review_checkout(repo, "critic", second)

    assert (path / "notes.md").read_text() == "what I found\n"


def test_an_unknown_sha_is_refused_with_a_stated_reason(repo):
    with pytest.raises(worktrees.ReviewCommitUnavailableError) as excinfo:
        ensure_review_checkout(repo, "critic", "0" * 40)

    assert "not present in this repository" in str(excinfo.value)
    assert not (repo / ".agentweave" / "reviews" / "critic").exists()


def test_an_empty_sha_is_refused_rather_than_defaulting_to_head(repo):
    with pytest.raises(worktrees.ReviewCommitUnavailableError):
        ensure_review_checkout(repo, "critic", "")
    with pytest.raises(worktrees.ReviewCommitUnavailableError):
        ensure_review_checkout(repo, "critic", "   ")


def test_a_tree_or_tag_that_is_not_a_commit_is_refused(repo):
    tree = _git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()

    with pytest.raises(worktrees.ReviewCommitUnavailableError):
        resolve_review_commit(repo, tree)


def test_resolve_review_commit_expands_an_abbreviated_sha(repo):
    sha = _head(repo)

    assert resolve_review_commit(repo, sha[:8]) == sha


def test_a_foreign_directory_at_the_review_path_is_refused_not_overwritten(repo):
    sha = _head(repo)
    squatter = repo / ".agentweave" / "reviews" / "critic"
    squatter.mkdir(parents=True)
    (squatter / "someone-elses.txt").write_text("not ours\n")

    with pytest.raises(worktrees.IsolationUnavailableError) as excinfo:
        ensure_review_checkout(repo, "critic", sha)

    assert "not a detached git worktree" in str(excinfo.value)
    assert (squatter / "someone-elses.txt").exists()


# --------------------------------------------------------------------------------------
# task 1.3 — shared dependencies, or the reviewer cannot run the suite
# --------------------------------------------------------------------------------------


def test_shared_dependencies_are_symlinked_into_a_review_checkout(repo):
    node_modules = repo / "node_modules"
    node_modules.mkdir()
    (node_modules / "marker.txt").write_text("installed\n")
    sha = _head(repo)

    path = ensure_review_checkout(repo, "critic", sha)

    # Provisioning must succeed either way: `_symlink_shared_dependencies` degrades rather than
    # failing when the platform refuses symlinks (Windows without Developer Mode). So the contract
    # asserted is the same one `test_worktrees.py` asserts for a working worktree — when the link
    # *is* made, the content is genuinely shared — rather than skipping the test on this machine.
    assert path.is_dir()
    linked = path / "node_modules"
    if linked.exists():
        assert (linked / "marker.txt").read_text() == "installed\n"


# --------------------------------------------------------------------------------------
# task 1.4 — cleanup
# --------------------------------------------------------------------------------------


def test_existing_review_checkout_provisions_nothing(repo):
    assert existing_review_checkout(repo, "critic") is None
    assert not (repo / ".agentweave" / "reviews").exists()


def test_existing_review_checkout_finds_a_provisioned_one(repo):
    sha = _head(repo)
    ensure_review_checkout(repo, "critic", sha)

    assert existing_review_checkout(repo, "critic") == repo / ".agentweave" / "reviews" / "critic"


def test_existing_review_checkout_ignores_an_abandoned_directory(repo):
    """A git command run in an untracked directory answers about the enclosing repository."""
    abandoned = repo / ".agentweave" / "reviews" / "critic"
    abandoned.mkdir(parents=True)

    assert existing_review_checkout(repo, "critic") is None


def test_releasing_an_agent_removes_its_review_checkout(repo):
    sha = _head(repo)
    ensure_review_checkout(repo, "critic", sha)

    result = release_worktree(repo, "critic")

    assert result.review_checkout_released is True
    assert not (repo / ".agentweave" / "reviews" / "critic").exists()


def test_an_agent_that_only_ever_reviewed_still_has_its_checkout_released(repo):
    """The case the early return would otherwise skip: a review checkout and no worktree."""
    sha = _head(repo)
    ensure_review_checkout(repo, "critic", sha)
    assert not worktrees.worktree_path(repo, "critic").exists()

    result = release_worktree(repo, "critic")

    assert result.released is False
    assert result.review_checkout_released is True
    assert not (repo / ".agentweave" / "reviews" / "critic").exists()


def test_releasing_an_agent_with_no_review_checkout_says_so(repo):
    result = release_worktree(repo, "critic")

    assert result.review_checkout_released is False


def test_release_review_checkout_is_idempotent(repo):
    sha = _head(repo)
    ensure_review_checkout(repo, "critic", sha)

    assert release_review_checkout(repo, "critic") is True
    assert release_review_checkout(repo, "critic") is False


def test_a_released_review_checkout_can_be_provisioned_again(repo):
    sha = _head(repo)
    ensure_review_checkout(repo, "critic", sha)
    release_review_checkout(repo, "critic")

    path = ensure_review_checkout(repo, "critic", sha)

    assert _head(path) == sha


def test_a_review_checkout_does_not_appear_as_an_agent_branch(repo):
    """`detect_conflicts` walks the registered checkouts; a detached one has no branch record."""
    sha = _head(repo)
    ensure_review_checkout(repo, "critic", sha)

    assert worktrees.list_agent_branches(repo) == []
    # And not as a workspace of any kind: task checkouts joined this listing in phase 6A, and a
    # detached review checkout must not have been swept in alongside them.
    assert worktrees.list_workspace_branches(repo) == []
