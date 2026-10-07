"""`a-task-checkout-catches-up-with-its-approved-prerequisites` (F158), against real disposable git
repositories under `tmp_path`.

A dependent task's branch is cut once. A prerequisite approved after that -- the dependent started
first (shape 1), or the dependency was declared later (shape 2) -- never reached it: prerequisite work
was merged only at branch creation. Now every turn on an existing branch takes in the commits of its
**approved** prerequisites that it lacks, never destructively (D1-D3), and a refusal names what clears
it (D5); a git timeout leaves nothing half-done (D6).
"""

import subprocess
from pathlib import Path

import pytest

from hub import worktrees
from hub.worktrees import IsolationUnavailableError, ensure_task_worktree

from .test_task_worktrees import _commit_on_new_branch, _git, _init_repo

B = "task-b0b0b0b0b0b0"
A = "task-a0a0a0a0a0a0"


@pytest.fixture
def repo(tmp_path) -> Path:
    return _init_repo(tmp_path / "repo")


def _commit_in(checkout: Path, name: str, body: str) -> str:
    (checkout / name).write_text(body)
    _git(checkout, "add", "-A")
    _git(checkout, "commit", "-q", "-m", f"work on {name}")
    return _git(checkout, "rev-parse", "HEAD").stdout.strip()


def _is_ancestor(checkout: Path, sha: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=checkout, capture_output=True
        ).returncode
        == 0
    )


def _state(checkout: Path) -> tuple:
    """The branch tip and the bytes of every file, to compare before and after a refusal."""
    tip = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    files = {
        p.relative_to(checkout).as_posix(): p.read_bytes()
        for p in checkout.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
    return tip, files


def _b_started_before_a(repo: Path, *, b_file="b.txt", b_body="b's work\n") -> Path:
    """B's checkout cut from main while A was still being worked, with B's own commit on it."""
    checkout = ensure_task_worktree(repo, B, "main", ())
    _commit_in(checkout, b_file, b_body)
    return checkout


def test_a_prerequisite_approved_after_the_branch_was_cut_is_brought_in(repo):
    """1.1 (D1, shape 1). FAILS today: an existing branch is returned untouched."""
    checkout = _b_started_before_a(repo)
    own = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    a_commit = _commit_on_new_branch(repo, "agentweave/task/" + A, "a.txt", "a's work\n")
    assert not _is_ancestor(checkout, a_commit)

    again = ensure_task_worktree(repo, B, "main", (), approved=((A, a_commit),))

    assert again == checkout
    assert _is_ancestor(checkout, a_commit)
    assert _is_ancestor(checkout, own)
    assert (checkout / "a.txt").read_text() == "a's work\n"


def test_a_released_branch_resumed_also_catches_up(repo):
    """1.2's path (D1): the re-attached branch -- a task released and worked again -- tops up too."""
    checkout = _b_started_before_a(repo)
    _git(repo, "worktree", "remove", "--force", str(checkout))
    a_commit = _commit_on_new_branch(repo, "agentweave/task/" + A, "a.txt", "a's work\n")

    again = ensure_task_worktree(repo, B, "main", (), approved=((A, a_commit),))

    assert _is_ancestor(again, a_commit)
    assert (again / "b.txt").exists()


def test_a_conflicting_prerequisite_refuses_and_changes_nothing(repo):
    """1.3 (D2) and 1.9 (D5): refused naming the prerequisite, the commit, the checkout and the
    command; the branch tip and the files are byte-identical."""
    checkout = _b_started_before_a(repo, b_file="f.txt", b_body="b rewrote line one\n")
    a_commit = _commit_on_new_branch(repo, "agentweave/task/" + A, "f.txt", "a rewrote it too\n")
    before = _state(checkout)

    with pytest.raises(IsolationUnavailableError) as refused:
        ensure_task_worktree(repo, B, "main", (), approved=((A, a_commit),))

    message = str(refused.value)
    assert A in message
    assert a_commit[:12] in message
    assert str(checkout) in message
    assert f"merge --no-ff {a_commit}" in message
    assert "conflicts with its base" not in message
    assert _state(checkout) == before
    assert not worktrees._is_mid_merge(checkout)


def test_uncommitted_changes_refuse_without_touching_them(repo):
    """1.4 (D2): something to merge and a dirty checkout -- refused, the file untouched."""
    checkout = _b_started_before_a(repo)
    (checkout / "scratch.txt").write_text("not committed\n")
    a_commit = _commit_on_new_branch(repo, "agentweave/task/" + A, "a.txt", "a's work\n")

    with pytest.raises(IsolationUnavailableError) as refused:
        ensure_task_worktree(repo, B, "main", (), approved=((A, a_commit),))

    assert A in str(refused.value)
    assert "uncommitted" in str(refused.value)
    assert (checkout / "scratch.txt").read_text() == "not committed\n"
    assert not _is_ancestor(checkout, a_commit)


def test_a_dirty_checkout_whose_prerequisite_is_already_in_starts(repo):
    """1.8 (review LOW): nothing to merge means no refusal, dirty or not."""
    a_commit = _commit_on_new_branch(repo, "agentweave/task/" + A, "a.txt", "a's work\n")
    checkout = ensure_task_worktree(repo, B, "main", (a_commit,))
    (checkout / "scratch.txt").write_text("not committed\n")

    again = ensure_task_worktree(repo, B, "main", (), approved=((A, a_commit),))

    assert again == checkout
    assert (checkout / "scratch.txt").read_text() == "not committed\n"


def test_a_merge_git_does_not_finish_in_time_is_aborted(repo, monkeypatch):
    """1.7 (D6). FAILS today: `TimeoutExpired` escapes and can leave a merge half-done."""
    checkout = _b_started_before_a(repo)
    a_commit = _commit_on_new_branch(repo, "agentweave/task/" + A, "a.txt", "a's work\n")
    real = worktrees._run_git
    calls = []

    def run_git(cwd, *args, check=True):
        calls.append(args)
        if "merge" in args and "--no-ff" in args:
            raise subprocess.TimeoutExpired(["git", *args], 60)
        return real(cwd, *args, check=check)

    monkeypatch.setattr(worktrees, "_run_git", run_git)
    with pytest.raises(IsolationUnavailableError) as refused:
        ensure_task_worktree(repo, B, "main", (), approved=((A, a_commit),))

    assert "did not finish" in str(refused.value)
    assert any(args[:2] == ("merge", "--abort") for args in calls)
    assert not worktrees._is_mid_merge(checkout)


def test_a_task_with_no_approved_prerequisites_asks_git_nothing(repo, monkeypatch):
    """1.6 (control): the common case costs nothing -- no merge, no merge-base."""
    checkout = _b_started_before_a(repo)
    real = worktrees._run_git
    asked = []

    def run_git(cwd, *args, check=True):
        asked.append(args[0] if args else "")
        return real(cwd, *args, check=check)

    monkeypatch.setattr(worktrees, "_run_git", run_git)
    assert ensure_task_worktree(repo, B, "main", ()) == checkout
    assert "merge" not in asked and "merge-base" not in asked


@pytest.mark.asyncio
async def test_only_approved_prerequisites_are_offered_for_the_top_up(app, monkeypatch, tmp_path):
    """1.5 (D3) at the resolver: an in-progress prerequisite with accepted evidence still seeds a
    *new* checkout (`prerequisites`, F159) but is not chased into an existing one (`approved`)."""
    from hub import task_integration, task_workspace
    from hub.db.engine import async_session_factory
    from hub.db.models import Task, TaskDependency

    async with async_session_factory() as session:
        for task_id, status in (
            (A, "in_progress"),
            ("task-c0c0c0c0c0c0", "approved"),
            (B, "pending"),
        ):
            session.add(Task(id=task_id, project_id="proj-test", title=task_id, status=status))
        await session.flush()
        for n, prerequisite in enumerate((A, "task-c0c0c0c0c0c0")):
            session.add(
                TaskDependency(
                    id=f"dep-{n}",
                    project_id="proj-test",
                    task_id=B,
                    depends_on_task_id=prerequisite,
                )
            )
        await session.commit()

    commits = {A: "a" * 40, "task-c0c0c0c0c0c0": "c" * 40}

    async def merge_targets(session, task, repo_root):
        return [
            task_integration.Target(
                commit_sha=commits[task.id], branch=f"agentweave/task/{task.id}"
            )
        ]

    async def governs(session, task):
        return True

    monkeypatch.setattr(task_integration, "merge_targets", merge_targets)
    monkeypatch.setattr(task_integration, "evidence_governs", governs)

    async with async_session_factory() as session:
        task = await session.get(Task, B)
        task.workspace_scheme = task_workspace.TASK_SCHEME
        inputs = await task_workspace.resolve_turn_workspace_inputs(
            session, project_id="proj-test", repo_root=tmp_path, task=task
        )

    assert set(inputs.prerequisites) == {"a" * 40, "c" * 40}
    assert inputs.approved == (("task-c0c0c0c0c0c0", "c" * 40),)
