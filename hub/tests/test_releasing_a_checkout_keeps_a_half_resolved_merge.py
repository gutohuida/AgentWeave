"""F746: releasing a task's checkout force-removes the directory. When the snapshot declines to
commit an unfinished conflicted merge (F695) that removal was the only copy of the author's partial
resolution, and it was thrown away without a word. The checkout is now kept, and the result says
why, so the caller can tell the operator."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hub import worktrees
from hub.worktrees import ensure_task_worktree

TASK = "task-ab12cd34ef56"


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


@pytest.fixture
def half_merged(tmp_path) -> Path:
    """A task checkout in the middle of a merge: `a.txt` resolved and staged, `f.txt` still
    conflicted."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    (repo / "a.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    path = ensure_task_worktree(repo, TASK, base="main")
    (path / "f.txt").write_text("task side\n", encoding="utf-8")
    (path / "a.txt").write_text("task side\n", encoding="utf-8")
    _git(path, "commit", "-qam", "task work")
    (repo / "f.txt").write_text("main side\n", encoding="utf-8")
    (repo / "a.txt").write_text("main side\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "main moved")
    assert _git(path, "merge", "main", check=False).returncode != 0
    (path / "a.txt").write_text("resolved by hand\n", encoding="utf-8")
    _git(path, "add", "a.txt")
    assert worktrees.unresolved_merge_paths(path) == ["f.txt"]
    return repo


def test_release_keeps_the_checkout_while_a_merge_is_half_resolved(half_merged):
    repo = half_merged
    path = worktrees.task_worktree_path(repo, TASK)

    result = worktrees.release_task_worktree(repo, TASK)

    assert result.released is False
    assert result.kept_reason and "f.txt" in result.kept_reason
    assert path.exists()
    assert (path / "a.txt").read_text(encoding="utf-8") == "resolved by hand\n"
    assert worktrees._is_mid_merge(path)


def test_release_removes_it_once_the_merge_is_resolved(half_merged):
    repo = half_merged
    path = worktrees.task_worktree_path(repo, TASK)
    (path / "f.txt").write_text("both\n", encoding="utf-8")
    _git(path, "add", "f.txt")

    result = worktrees.release_task_worktree(repo, TASK)

    assert result.released is True
    assert result.kept_reason is None
    assert not path.exists()
