"""Task 4.3 of `a-blocked-agent-workspace-holds-its-input`: each obstruction states *its own*
remedy, and the remedy is true.

Asserted at the `worktrees` layer, against real disposable git repositories under `tmp_path`, and
**per branch against the obstruction it was written for** -- never by substring-matching one
phrase that all three refusals happen to share. The three obstructions live at the same two paths
(an agent's workspace, a task's checkout), which is what the requirement's third scenario is
about: a link is cleared by removing the link, a foreign directory by removing the directory, and
a checkout left mid-merge by finishing the merge and *not* removing anything.

Where a remedy claims something happens next -- "the next turn runs `git worktree prune` and
provisions the checkout itself" -- the test performs the operator's half and then calls the real
function again. A remedy is a promise about the product, so an assertion that only reads the
sentence would leave the promise unmeasured.

A fourth obstruction was added 2026-09-22 (F347): nothing is in the way, and there is simply
nothing to cut a checkout from. It splits the same way the three above do, because the repairs
differ -- a repository with no commit anywhere is asked for a first commit, while one whose
commits are on other refs (an unborn HEAD after `git checkout --orphan`, a deleted `base`) is told
which ref failed, since another commit on the orphan branch would not help. Neither sentence names
the agent or the task: unlike the three above, the caller's prefix already does.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from hub import worktrees

# Named import, before conftest's autouse `_no_real_worktree_provision` replaces the module
# attribute, for the reason `test_task_worktrees.py` records: this file is one of the few that
# must reach the real per-task provisioning.
from hub.worktrees import ensure_task_worktree

AGENT = "remedy-agent"
TASK = "task-ab12cd34ef56"
OTHER_TASK = "task-00ff11ee22dd"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result


@pytest.fixture
def repo(tmp_path) -> Path:
    path = tmp_path / "repo"
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "f.txt").write_text("line1\nline2\nline3\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


def _symlink_or_skip(link: Path, target: Path) -> None:
    """Create a real symlink at *link*, or skip.

    Not a synthetic `is_symlink` patch: the branch under test asks the filesystem, so a patched
    answer would assert the patch. Windows without Developer Mode or admin rights refuses to
    create symlinks at all (`worktrees._symlink_shared_dependencies` already degrades for the
    same reason), so on such a machine this is skipped rather than quietly passing -- CI's Linux
    job is where it runs.
    """
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:  # pragma: no cover - privilege-dependent
        pytest.skip(f"cannot create a symlink on this machine: {exc}")


# --- The agent's own workspace ---------------------------------------------------------------


def test_a_symlinked_agent_workspace_asks_for_the_link_and_nothing_else(repo, tmp_path):
    """The link is the obstruction, so the link is what the remedy names.

    `rm -r` here would be actively wrong: the target is somebody's real directory, and an
    operator who reads the foreign-directory remedy by mistake would delete it.
    """
    elsewhere = tmp_path / "somebody-elses-directory"
    elsewhere.mkdir()
    (elsewhere / "keep.txt").write_text("this must survive\n")
    link = worktrees.worktree_path(repo, AGENT)
    _symlink_or_skip(link, elsewhere)

    with pytest.raises(worktrees.IsolationUnavailableError) as caught:
        worktrees.ensure_worktree(repo, AGENT)

    message = str(caught.value)
    assert "symlink" in message
    assert f"rm {link}" in message
    assert f"rm -r {link}" not in message

    # The remedy, performed.
    link.unlink()
    provisioned = worktrees.ensure_worktree(repo, AGENT)
    assert provisioned == link
    assert (elsewhere / "keep.txt").read_text() == "this must survive\n"


def test_a_foreign_registered_worktree_asks_for_the_directory_and_the_prune_is_real(repo):
    """The other half of `ensure_worktree`'s split, and the harder version of it.

    The blocking path is a *registered* worktree for another ref rather than a plain directory
    (which `test_a_blocked_agent_workspace_holds_its_input.py` covers), so removing it leaves
    `.git/worktrees/<name>` metadata behind -- exactly the state the remedy's second clause
    promises the next turn handles. Without the prune `ensure_worktree` already runs, the
    reprovision below fails, so the sentence is measured rather than trusted.
    """
    path = worktrees.worktree_path(repo, AGENT)
    path.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "worktree", "add", "-b", "someone-else", str(path), "HEAD")

    with pytest.raises(worktrees.IsolationUnavailableError) as caught:
        worktrees.ensure_worktree(repo, AGENT)

    message = str(caught.value)
    assert "not the registered git worktree" in message
    assert f"rm -r {path}" in message
    assert "prune" in message
    # Not the link remedy: this directory is real, and "remove the link itself" would read as a
    # no-op to an operator standing in front of it.
    assert "symlink" not in message

    shutil.rmtree(path)
    # Stale metadata, as promised -- git still lists the gone directory, flagged `prunable`.
    # Matched on git's own flag rather than on the path, which git prints with forward slashes
    # even on Windows.
    listed = _git(repo, "worktree", "list").stdout
    assert "prunable" in listed and path.name in listed

    provisioned = worktrees.ensure_worktree(repo, AGENT)
    assert provisioned == path
    assert worktrees.existing_worktree(repo, AGENT) == path


# --- A task's checkout, where all three obstructions share one path --------------------------


def test_a_symlinked_task_checkout_names_the_task_and_asks_for_the_link(repo, tmp_path):
    elsewhere = tmp_path / "somebody-elses-directory"
    elsewhere.mkdir()
    link = worktrees.task_worktree_path(repo, TASK)
    _symlink_or_skip(link, elsewhere)

    with pytest.raises(worktrees.IsolationUnavailableError) as caught:
        ensure_task_worktree(repo, TASK, base="main")

    message = str(caught.value)
    assert TASK in message
    assert "symlink" in message
    assert f"rm {link}" in message

    link.unlink()
    assert ensure_task_worktree(repo, TASK, base="main") == link


def test_a_foreign_directory_at_a_task_checkout_asks_for_the_directory(repo):
    path = worktrees.task_worktree_path(repo, TASK)
    path.mkdir(parents=True)
    (path / "left-behind.txt").write_text("not a worktree\n")

    with pytest.raises(worktrees.IsolationUnavailableError) as caught:
        ensure_task_worktree(repo, TASK, base="main")

    message = str(caught.value)
    assert TASK in message
    assert "not the registered git worktree" in message
    assert f"rm -r {path}" in message

    shutil.rmtree(path)
    assert ensure_task_worktree(repo, TASK, base="main") == path


def test_a_mid_merge_task_checkout_asks_for_the_merge_and_says_not_to_remove_it(repo):
    """The third obstruction, at the path the other two also refuse -- and the one whose remedy
    is the opposite of theirs. This directory is the task's real checkout carrying the task's own
    commits; an operator who applied the foreign-directory remedy here would destroy them.
    """
    conflicting = _commit_on_new_branch(repo, worktrees.task_branch_name(OTHER_TASK), "OTHER\n")
    path = ensure_task_worktree(repo, TASK, base="main")
    (path / "f.txt").write_text("THE TASK'S OWN WORK\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "the task's own work")
    subprocess.run(["git", "merge", conflicting], cwd=path, capture_output=True, timeout=30)
    assert worktrees._is_mid_merge(path)

    with pytest.raises(worktrees.IsolationUnavailableError) as caught:
        ensure_task_worktree(repo, TASK, base="main")

    message = str(caught.value)
    assert "unfinished merge" in message
    assert f"git -C {path} merge --abort" in message
    assert "Do not remove the directory" in message
    # The cross-negative that makes this a per-branch assertion rather than a shared phrase: the
    # remedy the other two obstructions at this same path state must not appear here.
    assert f"rm -r {path}" not in message
    assert "prune" not in message

    _git(path, "merge", "--abort")
    assert ensure_task_worktree(repo, TASK, base="main") == path
    assert (path / "f.txt").read_text() == "THE TASK'S OWN WORK\n"


def _commit_on_new_branch(repo: Path, branch: str, content: str) -> str:
    _git(repo, "checkout", "-q", "-b", branch)
    (repo / "f.txt").write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"work on {branch}")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-q", "main")
    return sha


# --- A repository with no commit yet (F347) ----------------------------------------------------


@pytest.fixture
def unborn(tmp_path) -> Path:
    """A repository `git init` has made and nobody has committed to. `HEAD` names nothing."""
    path = tmp_path / "unborn"
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "f.txt").write_text("written, never committed\n")
    return path


def _first_commit(repo: Path) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "first")


def test_an_unborn_head_asks_for_a_first_commit_rather_than_naming_git_plumbing(unborn):
    """F347, decided option (a). The operator saw `fatal: invalid reference: HEAD` and had to
    leave the product to work out what it meant. The sentence names the repair instead, and the
    remedy is then performed here: after one commit the same call provisions the checkout.
    """
    with pytest.raises(worktrees.IsolationUnavailableError) as caught:
        worktrees.ensure_worktree(unborn, AGENT)

    message = str(caught.value)
    assert message == (
        f"{unborn.name} is a git repository with no commit yet. "
        f"Make a first commit in {unborn}, and the turn will start."
    )
    # What it must NOT say: git's own words, which is what F347 was filed about.
    assert "invalid reference" not in message
    assert "worktree add" not in message
    # Nor the agent, unlike the refusals above: `agent_trigger` wraps this in "Could not prepare
    # {agent}'s own workspace: ...", so naming it here would say it twice.
    assert AGENT not in message

    _first_commit(unborn)
    path = worktrees.ensure_worktree(unborn, AGENT)
    assert path.is_dir()
    assert worktrees._registered_worktree_branch(unborn, path) == (
        f"refs/heads/{worktrees.branch_name(AGENT)}"
    )


def test_a_task_checkout_in_an_unborn_repository_refuses_the_same_way(unborn):
    """The task path reaches the identical git failure, and F347 recorded only the agent path."""
    with pytest.raises(worktrees.IsolationUnavailableError) as caught:
        ensure_task_worktree(unborn, TASK, base="main")

    message = str(caught.value)
    assert "no commit yet" in message
    assert f"Make a first commit in {unborn}" in message
    assert "invalid reference" not in message
    # Same sentence as the agent path's: same obstruction, same repair, and the caller's prefix
    # ("Could not prepare the checkout for task ...") is what distinguishes them.
    assert TASK not in message

    _first_commit(unborn)
    assert ensure_task_worktree(unborn, TASK, base="main").is_dir()


def test_the_refusal_creates_no_commit_and_no_branch(unborn):
    """Option (b) -- an orphan branch -- was rejected, and (a) says the Hub writes nothing."""
    with pytest.raises(worktrees.IsolationUnavailableError):
        worktrees.ensure_worktree(unborn, AGENT)

    assert (
        subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", "HEAD"], cwd=unborn, capture_output=True
        ).returncode
        != 0
    ), "the repository still has no commit"
    branches = subprocess.run(
        ["git", "branch", "--list", "--all"], cwd=unborn, capture_output=True, text=True
    ).stdout
    assert branches.strip() == "", f"the refusal left a branch behind: {branches!r}"
    assert not (unborn / ".agentweave" / "worktrees").exists()


def test_a_repository_with_a_commit_is_untouched_by_the_guard(repo):
    """The guard must not refuse the ordinary case; `repo` has one commit."""
    assert worktrees._has_a_commit(repo) is True
    assert worktrees.ensure_worktree(repo, AGENT).is_dir()


def test_an_unborn_head_beside_real_branches_is_not_called_an_empty_repository(unborn):
    """The review's case, and a regression the first version of this guard introduced.

    `git checkout --orphan` leaves HEAD unborn in a repository whose other branches carry commits.
    `git worktree add <path> <branch>` still succeeds there, so provisioning an agent whose branch
    already exists must not be refused — and telling that operator to "make a first commit" names a
    repair they have already made.
    """
    _first_commit(unborn)
    _git(unborn, "branch", worktrees.branch_name(AGENT))
    _git(unborn, "checkout", "-q", "--orphan", "fresh-start")
    assert not worktrees._resolves(unborn, "HEAD"), "HEAD is unborn"
    assert worktrees._has_a_commit(unborn), "but the repository is not empty"

    path = worktrees.ensure_worktree(unborn, AGENT)
    assert path.is_dir()


def test_a_base_that_no_longer_exists_says_so_rather_than_asking_for_a_first_commit(unborn):
    """A task checkout is cut from `base`, which the Hub layer passes in and which can name a
    branch somebody deleted. "Make a first commit" is the wrong remedy for that."""
    _first_commit(unborn)

    with pytest.raises(worktrees.IsolationUnavailableError) as caught:
        ensure_task_worktree(unborn, TASK, base="branch-that-was-deleted")

    message = str(caught.value)
    assert "branch-that-was-deleted" in message
    assert "no commit yet" not in message, "the repository has commits; this ref does not resolve"
    assert not worktrees.task_root(unborn).exists(), "a refusal leaves no directory behind"
