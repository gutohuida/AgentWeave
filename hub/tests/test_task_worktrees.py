"""Tests for the *per-task* half of `hub.worktrees` (change
`2026-08-27-work-is-isolated-per-task`, design D1 and D6), against real disposable git
repositories under `tmp_path` — never the real AgentWeave checkout.

Kept in its own file rather than appended to `test_worktrees.py` because the two answer
different questions: that file pins one checkout per *agent*, this one pins one checkout per
*task*, and D4 keeps both alive at once. A reader looking for why a task branch cannot collide
with an agent branch should not have to find it among the agent tests.
"""

import subprocess
from pathlib import Path

import pytest

from hub import worktrees

TASK = "task-ab12cd34ef56"
OTHER = "task-00ff11ee22dd"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "f.txt").write_text("line1\nline2\nline3\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


@pytest.fixture
def repo(tmp_path) -> Path:
    return _init_repo(tmp_path / "repo")


def _commit_on_new_branch(repo: Path, branch: str, name: str, body: str) -> str:
    """Commit *body* to *name* on a new *branch* cut from `main`, and return to `main`."""
    _git(repo, "checkout", "-q", "-b", branch, "main")
    (repo / name).write_text(body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"work on {branch}")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-q", "main")
    return sha


def _count_commits(repo: Path, rev: str) -> int:
    return len(_git(repo, "rev-list", rev).stdout.split())


def _branch_exists(repo: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", branch],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0


# --- 2.1: the pure half -------------------------------------------------------------------


def test_task_paths_and_names_are_pure(repo):
    """They answer where a task's work goes. Answering must not create it."""
    path = worktrees.task_worktree_path(repo, TASK)
    branch = worktrees.task_branch_name(TASK)

    assert path == repo / ".agentweave" / "tasks" / TASK
    assert branch == f"agentweave/task/{TASK}"
    assert not path.exists()
    assert not (repo / ".agentweave" / "tasks").exists()
    assert not _branch_exists(repo, branch)


@pytest.mark.parametrize(
    "task_id",
    [
        "",
        "ab12cd34ef56",
        "task-",
        "task-../escape",
        "task-nested/name",
        "task-not_hex",
        "task-AB12CD34EF56",
        "proj-ab12cd34ef56",
        "task-ab12cd34ef56 ",
    ],
)
def test_an_id_that_is_not_a_task_id_is_refused(task_id):
    """Mirrors `validate_agent_name`'s coverage: a value that becomes both a path component
    and a git ref suffix is refused at this module's boundary, not at the git call.

    Uppercase hex is refused deliberately. Two ids differing only in case are two distinct git
    refs but, on Windows, one directory — so accepting both would let one task's checkout be
    handed to another.
    """
    with pytest.raises(ValueError, match="task id"):
        worktrees.task_worktree_path(Path("/repo"), task_id)
    with pytest.raises(ValueError, match="task id"):
        worktrees.task_branch_name(task_id)


# --- 2.2: the collision the extra path segment exists to prevent ----------------------------


def test_a_task_branch_can_never_collide_with_an_agent_branch(repo):
    """`_AGENT_NAME_RE` accepts `task-ab12cd34ef56` as an agent name, so without the `task/`
    segment the two schemes would name the same ref and the same directory. `/` is not in the
    agent name character class, which is what makes the separation total rather than merely
    unlikely.
    """
    collider = TASK  # a legal agent name and a legal task id at once

    assert worktrees.branch_name(collider) != worktrees.task_branch_name(TASK)
    assert worktrees.worktree_path(repo, collider) != worktrees.task_worktree_path(repo, TASK)

    worktrees.ensure_worktree(repo, collider)
    worktrees.ensure_task_worktree(repo, TASK, base="main")

    assert _branch_exists(repo, f"agentweave/{collider}")
    assert _branch_exists(repo, f"agentweave/task/{TASK}")
    assert (repo / ".agentweave" / "worktrees" / collider).is_dir()
    assert (repo / ".agentweave" / "tasks" / TASK).is_dir()


# --- 2.4: creation and idempotence ---------------------------------------------------------


def test_ensure_task_worktree_creates_a_checkout_at_the_base(repo):
    base_sha = _git(repo, "rev-parse", "main").stdout.strip()

    path = worktrees.ensure_task_worktree(repo, TASK, base="main")

    assert path == worktrees.task_worktree_path(repo, TASK)
    assert (path / "f.txt").read_text() == "line1\nline2\nline3\n"
    assert _git(path, "rev-parse", "HEAD").stdout.strip() == base_sha
    assert (
        _git(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == f"agentweave/task/{TASK}"
    )


def test_ensure_task_worktree_is_idempotent(repo):
    first = worktrees.ensure_task_worktree(repo, TASK, base="main")
    (first / "wip.txt").write_text("mid-turn work\n")

    second = worktrees.ensure_task_worktree(repo, TASK, base="main")

    assert first == second
    assert (second / "wip.txt").read_text() == "mid-turn work\n"


def test_ensure_task_worktree_cuts_from_the_base_it_is_given_not_from_head(repo):
    """`HEAD` is whatever the operator's checkout is sitting on; the base is the project's
    integration target. D1 rejected `HEAD` as the base for exactly this reason.
    """
    _git(repo, "checkout", "-q", "-b", "operator-side-quest")
    (repo / "sidequest.txt").write_text("not on main\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "side quest")

    path = worktrees.ensure_task_worktree(repo, TASK, base="main")

    assert not (path / "sidequest.txt").exists()


# --- 2.5: prerequisites -------------------------------------------------------------------


def test_a_prerequisite_not_reachable_from_the_base_is_merged_in(repo):
    """And merged with `--no-ff`, which the commit count is what pins.

    The task branch sits at `main` and the prerequisite is `main` plus one commit, so a plain
    merge would **fast-forward**: the task branch tip would become the prerequisite's own commit,
    two tasks would share a tip, and the act of bringing the work in would leave no record. Three
    commits (base, prerequisite, merge) is that fast-forward not happening.
    """
    prerequisite = _commit_on_new_branch(
        repo, worktrees.task_branch_name(OTHER), "dep.py", "def dep():\n    return 1\n"
    )

    path = worktrees.ensure_task_worktree(repo, TASK, base="main", prerequisites=[prerequisite])

    assert (path / "dep.py").read_text() == "def dep():\n    return 1\n"
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", prerequisite, "HEAD"],
            cwd=path,
            capture_output=True,
            timeout=30,
        ).returncode
        == 0
    )
    assert _count_commits(path, "HEAD") == 3
    assert _git(path, "rev-parse", "HEAD").stdout.strip() != prerequisite


def test_a_prerequisite_already_reachable_from_the_base_is_not_merged_twice(repo):
    """The prerequisite was integrated into `main` before this task started — the ordinary
    case. Merging it again would put a pointless merge commit on every task branch.

    **This test does not discriminate a reachability check in our own code, and there isn't
    one.** `git merge --no-ff <ancestor>` was measured to be a no-op, so the guarantee is git's;
    what is asserted here is the guarantee, which is what a caller depends on.
    """
    (repo / "dep.py").write_text("def dep():\n    return 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "integrated prerequisite")
    prerequisite = _git(repo, "rev-parse", "HEAD").stdout.strip()
    commits_on_main = _count_commits(repo, "main")

    path = worktrees.ensure_task_worktree(repo, TASK, base="main", prerequisites=[prerequisite])

    assert (path / "dep.py").exists()
    assert _count_commits(path, "HEAD") == commits_on_main


# --- 2.6 and 2.6b: the two ways provisioning fails, and the unwind --------------------------


def test_a_conflicting_prerequisite_leaves_no_checkout_and_no_branch(repo):
    prerequisite = _commit_on_new_branch(
        repo, worktrees.task_branch_name(OTHER), "f.txt", "PREREQUISITE\nline2\nline3\n"
    )
    (repo / "f.txt").write_text("MAIN\nline2\nline3\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main moves too")

    with pytest.raises(worktrees.IsolationUnavailableError) as excinfo:
        worktrees.ensure_task_worktree(repo, TASK, base="main", prerequisites=[prerequisite])

    message = str(excinfo.value)
    assert prerequisite[:12] in message
    assert "conflict" in message.lower()

    # All-or-nothing. The branch is the half that would otherwise be reused silently by the
    # next turn, carrying a conflicted tree, so assert it by ref and not only by directory.
    assert not worktrees.task_worktree_path(repo, TASK).exists()
    assert not _branch_exists(repo, worktrees.task_branch_name(TASK))


def test_a_prerequisite_commit_missing_from_the_repository_says_so(repo):
    """D1's other failure shape, added in R3: the recorded commit is gone (an operator deleted
    the branch carrying it). `git merge <unknown>` fails without ever reaching a conflict, and
    the two ask the operator for different things.
    """
    missing = "0" * 40

    with pytest.raises(worktrees.IsolationUnavailableError) as excinfo:
        worktrees.ensure_task_worktree(repo, TASK, base="main", prerequisites=[missing])

    message = str(excinfo.value)
    assert missing[:12] in message
    assert "missing" in message.lower()
    assert "conflict" not in message.lower()

    assert not worktrees.task_worktree_path(repo, TASK).exists()
    assert not _branch_exists(repo, worktrees.task_branch_name(TASK))


# --- 2.7b: the state a killed process can leave behind -------------------------------------


def test_a_task_checkout_left_mid_merge_is_refused_rather_than_handed_over(repo):
    """`ensure_worktree`'s idempotent path returns any correctly-registered directory
    unexamined. If the Hub died between `worktree add` and the unwind, that directory is full
    of conflict markers, and handing it to an agent asks the agent to guess what happened.
    """
    conflicting = _commit_on_new_branch(
        repo, worktrees.task_branch_name(OTHER), "f.txt", "PREREQUISITE\nline2\nline3\n"
    )
    path = worktrees.ensure_task_worktree(repo, TASK, base="main")
    (path / "f.txt").write_text("TASK\nline2\nline3\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "the task's own work")

    # Reproduce the interrupted state: a merge that conflicted and was never cleaned up.
    subprocess.run(["git", "merge", conflicting], cwd=path, capture_output=True, timeout=30)
    assert _git(path, "rev-parse", "--verify", "MERGE_HEAD").stdout.strip()

    with pytest.raises(worktrees.IsolationUnavailableError, match="unfinished merge"):
        worktrees.ensure_task_worktree(repo, TASK, base="main")


# --- 2.9: release --------------------------------------------------------------------------


def test_release_task_worktree_snapshots_removes_and_keeps_the_branch(repo):
    path = worktrees.ensure_task_worktree(repo, TASK, base="main")
    (path / "done.py").write_text("finished\n")
    committed = _git(path, "rev-parse", "HEAD").stdout.strip()

    result = worktrees.release_task_worktree(repo, TASK)

    assert result.released is True
    assert result.branch == worktrees.task_branch_name(TASK)
    assert result.had_uncommitted_changes is True
    assert result.snapshot_commit
    assert not path.exists()

    branch = worktrees.task_branch_name(TASK)
    assert _branch_exists(repo, branch)
    assert _git(repo, "rev-parse", branch).stdout.strip() == result.snapshot_commit
    assert committed in _git(repo, "rev-list", branch).stdout
    assert "done.py" in _git(repo, "show", "--pretty=format:", "--name-only", branch).stdout


def test_release_task_worktree_reports_nothing_when_never_provisioned(repo):
    result = worktrees.release_task_worktree(repo, TASK)

    assert result.released is False
    assert result.branch == worktrees.task_branch_name(TASK)
    assert result.snapshot_commit is None
