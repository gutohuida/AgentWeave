"""F747: one side deleting a file the other modified writes no conflict markers, so the content
check cannot see it. What can is the index: the path stays unmerged until it is resolved, and
resolving it -- keeping the file (`git add`) or taking the deletion (`git rm`) -- is the decision
the conflict asks for. There is nothing left for a snapshot to second-guess, so these pin the two
halves: unresolved is declined, resolved either way is committed."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hub import worktrees


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def delete_modify(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    (repo / "keep.txt").write_text("k\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", "other")
    _git(repo, "rm", "-q", "f.txt")
    _git(repo, "commit", "-qm", "delete f")
    _git(repo, "checkout", "-q", "main")
    (repo / "f.txt").write_text("changed on main\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "modify f")
    merged = _git(repo, "merge", "--no-ff", "other")
    assert merged.returncode != 0 and worktrees._is_mid_merge(repo)
    return repo


def test_the_unresolved_path_is_named_and_the_snapshot_declines(delete_modify):
    repo = delete_modify
    assert worktrees.unresolved_merge_paths(repo) == ["f.txt"]
    head = _git(repo, "rev-parse", "HEAD").stdout
    assert worktrees.snapshot_worktree(repo, "agent") is None
    assert _git(repo, "rev-parse", "HEAD").stdout == head
    assert worktrees._is_mid_merge(repo)


@pytest.mark.parametrize("resolution", ["keep", "delete"])
def test_a_path_resolved_either_way_is_committed_and_concludes_the_merge(delete_modify, resolution):
    repo = delete_modify
    _git(repo, *(["add", "f.txt"] if resolution == "keep" else ["rm", "-q", "f.txt"]))
    assert worktrees.unresolved_merge_paths(repo) == []
    assert worktrees.snapshot_worktree(repo, "agent") is not None
    assert not worktrees._is_mid_merge(repo)
    assert (repo / "f.txt").exists() == (resolution == "keep")
