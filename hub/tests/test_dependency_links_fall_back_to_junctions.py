"""The Hub links a project's dependency directories into a checkout itself, junctions if need be.

F1038 happened because it did not: on a machine that cannot create symbolic links (F567) the Hub
linked nothing, no turn had `node_modules` or `.venv`, and agents made junctions by hand -- links
the Hub then followed when it removed the worktree. And `_symlink_shared_dependencies` only ever
looked at the repository root, so `hub/ui/node_modules` was never linked at all.

Everything lives under `tmp_path`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from hub import worktrees

TASK = "task-ab12cd34ef56"

_REAL_ENSURE_TASK_WORKTREE = worktrees.ensure_task_worktree

IS_WINDOWS = sys.platform == "win32"
_PRIVILEGE = "[WinError 1314] A required privilege is not held by the client"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    return IS_WINDOWS and bool(
        os.lstat(path).st_file_attributes & 0x400  # FILE_ATTRIBUTE_REPARSE_POINT
    )


@pytest.fixture
def repo(tmp_path) -> Path:
    """A repository with the dependency directories of this one: a root `.venv`, a nested
    `hub/ui/node_modules` beside a tracked `package.json`, and two `node_modules` that must not be
    linked (no tracked `package.json` beside one; one beyond the third level)."""
    root = tmp_path / "repo"
    (root / "hub" / "ui").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "test")
    (root / "f.txt").write_text("base\n")
    (root / "hub" / "ui" / "package.json").write_text("{}\n")
    deep = root / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    (deep / "package.json").write_text("{}\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    # Ignored by default in a real project; here simply untracked, as they are in the main checkout.
    (root / ".venv").mkdir()
    (root / ".venv" / "marker.txt").write_text("venv\n")
    (root / "hub" / "ui" / "node_modules").mkdir()
    (root / "hub" / "ui" / "node_modules" / "marker.txt").write_text("modules\n")
    (root / "docs" / "node_modules").mkdir(parents=True)  # no package.json beside it
    (deep / "node_modules").mkdir()  # four directories down
    return root


def _refuse_symlinks(self, target, target_is_directory=False):  # noqa: ANN001, ANN202
    raise OSError(_PRIVILEGE)


@pytest.fixture
def symlinks_refused(monkeypatch):
    """This machine's usual state. Off Windows there is no junction to fall back to, so the links
    are made as symlinks and nothing is patched."""
    if IS_WINDOWS:
        monkeypatch.setattr(Path, "symlink_to", _refuse_symlinks)


def test_both_directories_are_reachable_through_links_and_no_failure_is_reported(
    repo, symlinks_refused
):
    checkout = _REAL_ENSURE_TASK_WORKTREE(repo, TASK, "main")

    assert (checkout / "hub" / "ui" / "node_modules" / "marker.txt").read_text() == "modules\n"
    assert (checkout / ".venv" / "marker.txt").read_text() == "venv\n"
    assert _is_link(checkout / "hub" / "ui" / "node_modules")
    assert _is_link(checkout / ".venv")
    # the F567 notice: nothing is missing that the Hub could not link
    assert worktrees.shared_dependency_link_failures(repo, checkout) == []
    assert worktrees._link_failures.get(str(checkout)) is None


def test_only_what_the_project_declares_is_linked(repo, symlinks_refused):
    checkout = _REAL_ENSURE_TASK_WORKTREE(repo, TASK, "main")

    assert not os.path.lexists(checkout / "docs" / "node_modules")
    assert not os.path.lexists(checkout / "a" / "b" / "c" / "d" / "node_modules")


def test_removing_the_checkout_leaves_the_originals_intact(repo, symlinks_refused):
    checkout = _REAL_ENSURE_TASK_WORKTREE(repo, TASK, "main")
    (checkout / "work.txt").write_text("uncommitted\n")  # forces the snapshot path

    result = worktrees.release_task_worktree(repo, TASK)

    assert result.released
    assert not os.path.lexists(checkout)
    assert (repo / "hub" / "ui" / "node_modules" / "marker.txt").read_text() == "modules\n"
    assert (repo / ".venv" / "marker.txt").read_text() == "venv\n"


def test_a_symlink_is_still_preferred_where_it_works(repo):
    if IS_WINDOWS:
        probe = repo.parent / "probe"
        try:
            probe.symlink_to(repo, target_is_directory=True)
        except OSError:
            pytest.skip("this account cannot create symbolic links")
        else:
            os.rmdir(probe)
    checkout = _REAL_ENSURE_TASK_WORKTREE(repo, TASK, "main")

    assert (checkout / "hub" / "ui" / "node_modules").is_symlink()
    assert (checkout / ".venv").is_symlink()


@pytest.mark.skipif(not IS_WINDOWS, reason="directory junctions are Windows-only")
def test_a_failure_of_both_kinds_of_link_is_still_reported(repo, symlinks_refused, monkeypatch):
    def refuse(source, target):  # noqa: ANN001, ANN202
        raise OSError("no junction either")

    monkeypatch.setattr(worktrees, "_make_junction", refuse)

    checkout = _REAL_ENSURE_TASK_WORKTREE(repo, TASK, "main")

    names = {f.name for f in worktrees.shared_dependency_link_failures(repo, checkout)}
    assert names == {".venv", "hub/ui/node_modules"}
    assert {f.name for f in worktrees._link_failures[str(checkout)]} == names
    assert not os.path.lexists(checkout / ".venv")


def test_an_existing_directory_in_the_checkout_is_left_alone(repo, symlinks_refused):
    """The operator installed into the checkout itself: nothing is linked over it."""
    checkout = _REAL_ENSURE_TASK_WORKTREE(repo, TASK, "main")
    # remove what was linked, install for real, and prepare again
    for rel in (".venv", "hub/ui/node_modules"):
        link = checkout / rel
        try:
            os.unlink(link)
        except OSError:
            os.rmdir(link)
        link.mkdir()
        (link / "own.txt").write_text("own\n")

    assert worktrees._symlink_shared_dependencies(repo, checkout) == []

    assert (checkout / "hub" / "ui" / "node_modules" / "own.txt").read_text() == "own\n"
    assert not (checkout / ".venv" / "marker.txt").exists()
