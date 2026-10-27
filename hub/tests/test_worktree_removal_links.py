"""F1038: removing a worktree must never follow a link inside it.

On 2026-10-23 an agent linked `hub/ui/node_modules` into its task worktree with a directory
junction; when the Hub removed that worktree, `git worktree remove --force` followed the junction
and emptied the main checkout's `hub/ui/node_modules`. Twice in 20 minutes. A link can point
anywhere, so these tests link to a directory holding a file that has to survive.

Everything here lives under `tmp_path`: the junctions and links point only at a sibling temporary
directory, and they are removed with `os.rmdir` / `os.unlink` -- never `shutil.rmtree` over a tree
that may still contain one, which on Python 3.11 follows a junction.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

import pytest

from hub import project_checks, worktrees

TASK = "task-ab12cd34ef56"
AGENT = "alice"

# conftest stubs these on the module for every other test; the real ones are held from import time.
_REAL_ENSURE_TASK_WORKTREE = worktrees.ensure_task_worktree
_REAL_ENSURE_REVIEW_CHECKOUT = worktrees.ensure_review_checkout

IS_WINDOWS = sys.platform == "win32"


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
    # The link a test makes is not a change the worktree carries (as a real `node_modules` is not).
    exclude = path / ".git" / "info" / "exclude"
    exclude.parent.mkdir(exist_ok=True)
    exclude.write_text("linked\n")
    return path


def _junction(link: Path, target: Path) -> None:
    import _winapi  # type: ignore[import-not-found]  # Windows only

    _winapi.CreateJunction(str(target), str(link))


def _symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:  # no privilege: this machine's usual state
        pytest.skip(f"this account cannot create symbolic links: {exc}")


def _drop_link(link: Path) -> None:
    """Remove a link and nothing it points at."""
    if not os.path.lexists(link):
        return
    try:
        os.unlink(link)
    except OSError:
        os.rmdir(link)


KINDS = [
    pytest.param(
        "junction",
        marks=pytest.mark.skipif(not IS_WINDOWS, reason="directory junctions are Windows-only"),
    ),
    "symlink",
]


@pytest.fixture
def repo(tmp_path) -> Path:
    return _init_repo(tmp_path / "repo")


@pytest.fixture
def outside(tmp_path) -> Path:
    """A directory outside every worktree, holding the file a removal must not touch."""
    directory = tmp_path / "outside"
    directory.mkdir()
    (directory / "keep.txt").write_text("precious\n")
    (directory / "sub").mkdir()
    (directory / "sub" / "deep.txt").write_text("also precious\n")
    return directory


@pytest.fixture
def link_to(outside):
    """Make a link of *kind* at a path, and take every one made out again afterwards."""
    made: list[Path] = []

    def make(kind: str, link: Path) -> Path:
        (_junction if kind == "junction" else _symlink)(link, outside)
        made.append(link)
        return link

    yield make
    for link in made:
        _drop_link(link)


def _assert_untouched(outside: Path) -> None:
    assert (outside / "keep.txt").read_text() == "precious\n"
    assert (outside / "sub" / "deep.txt").read_text() == "also precious\n"


def _registered(repo: Path, path: Path) -> bool:
    listing = _git(repo, "worktree", "list", "--porcelain").stdout
    wanted = os.path.normcase(os.path.abspath(path))
    return any(
        line.startswith("worktree ")
        and os.path.normcase(os.path.abspath(line[len("worktree ") :].strip())) == wanted
        for line in listing.splitlines()
    )


# --- one case per removal path ---------------------------------------------------------------------


def _agent_release(repo: Path) -> tuple[Path, Callable[[], object]]:
    path = worktrees.ensure_worktree(repo, AGENT)
    return path, lambda: worktrees.release_worktree(repo, AGENT)


def _task_release(repo: Path) -> tuple[Path, Callable[[], object]]:
    path = _REAL_ENSURE_TASK_WORKTREE(repo, TASK, "main")
    return path, lambda: worktrees.release_task_worktree(repo, TASK)


def _task_discard(repo: Path) -> tuple[Path, Callable[[], object]]:
    path = _REAL_ENSURE_TASK_WORKTREE(repo, TASK, "main")
    return path, lambda: worktrees.discard_task_checkout(repo, TASK)


def _review_release(repo: Path) -> tuple[Path, Callable[[], object]]:
    path = _REAL_ENSURE_REVIEW_CHECKOUT(repo, AGENT, "HEAD")
    return path, lambda: worktrees.release_review_checkout(repo, AGENT)


def _unwind(repo: Path) -> tuple[Path, Callable[[], object]]:
    path = _REAL_ENSURE_TASK_WORKTREE(repo, TASK, "main")
    return path, lambda: worktrees._unwind_task_worktree(
        repo, path, worktrees.task_branch_name(TASK)
    )


def _check_checkout(repo: Path) -> tuple[Path, Callable[[], object]]:
    path = project_checks._checkout(repo, TASK, "HEAD")
    return path, lambda: project_checks._remove_checkout(repo, path)


PATHS = {
    "release_worktree": _agent_release,
    "release_task_worktree": _task_release,
    "discard_task_checkout": _task_discard,
    "release_review_checkout": _review_release,
    "_unwind_task_worktree": _unwind,
    "project_checks._remove_checkout": _check_checkout,
}


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("which", sorted(PATHS))
def test_removal_never_follows_a_link_and_still_completes(which, kind, repo, outside, link_to):
    path, remove = PATHS[which](repo)
    link_to(kind, path / "linked")
    assert (path / "linked" / "keep.txt").exists()  # the link works while the worktree stands

    remove()

    # removal-never-follows-links
    _assert_untouched(outside)
    # removal-still-completes
    assert not os.path.lexists(path), f"{which} left {path} behind"
    assert not _registered(repo, path)


@pytest.mark.parametrize("kind", KINDS)
def test_the_fallback_removal_never_follows_a_link_either(
    kind, repo, outside, link_to, monkeypatch
):
    """When git's own removal fails, the Hub deletes the directory itself, and so must not follow."""
    path, remove = _review_release(repo)
    link_to(kind, path / "linked")

    real_run_git = worktrees._run_git

    def git_that_cannot_remove(cwd, *args, **kwargs):  # noqa: ANN001, ANN202
        if args[:2] == ("worktree", "remove"):
            return subprocess.CompletedProcess(args, 1, "", "refused")
        return real_run_git(cwd, *args, **kwargs)

    monkeypatch.setattr(worktrees, "_run_git", git_that_cannot_remove)

    remove()

    _assert_untouched(outside)
    assert not os.path.lexists(path)


@pytest.mark.skipif(not IS_WINDOWS, reason="directory junctions are Windows-only")
def test_a_link_nested_inside_a_real_directory_is_not_followed(repo, outside, link_to):
    """Links are found wherever they sit, not only at the top of the worktree."""
    path = worktrees.ensure_worktree(repo, AGENT)
    nested = path / "a" / "b"
    nested.mkdir(parents=True)
    link_to("junction", nested / "linked")

    worktrees.release_worktree(repo, AGENT)

    _assert_untouched(outside)
    assert not os.path.lexists(path)


def test_removing_links_from_a_tree_without_any_changes_nothing(tmp_path):
    tree = tmp_path / "tree"
    (tree / "d").mkdir(parents=True)
    (tree / "d" / "f.txt").write_text("x")

    assert worktrees.remove_links_in(tree) == []
    assert (tree / "d" / "f.txt").read_text() == "x"
