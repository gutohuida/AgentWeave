"""What an agent changed, read from git: the data behind the side panel's Changes tab.

Blocking git work only; the route calls these through `asyncio.to_thread`. Every function is
read-only and takes the repository (or the agent's checkout) explicitly, so none of it can
provision anything or touch the operator's own working copy.

Two scopes, matching the tab's switch: `turn` is what one auto-snapshot commit changed, `branch`
is everything the branch has that the base does not (`base...branch`, the merge-base form).
"""

from __future__ import annotations

import contextvars
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from . import worktrees

#: A single file's patch longer than this is cut to its start and marked truncated.
MAX_PATCH_LINES = 5000

_STATUS_LETTERS = {"A", "M", "D", "R", "C", "T"}


@dataclass
class ChangedFile:
    path: str
    status: str  # A added, M modified, D deleted, R renamed
    added: int = 0
    removed: int = 0
    binary: bool = False
    old_path: Optional[str] = None


@dataclass
class Patch:
    patch: str
    binary: bool
    truncated: bool
    total_lines: int


def local_branches(repo_root: Path) -> set:
    """Every local branch name, in one git process."""
    result = worktrees._run_git(
        repo_root, "for-each-ref", "--format=%(refname:short)", "refs/heads", check=False
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def resolve_base(
    repo_root: Path, configured: Optional[str], branches: Optional[set] = None
) -> Optional[str]:
    """The branch the tab compares with: the project's accepted main branch, else a conventional
    name that exists, else whatever the project's own checkout has out. None when none is found.
    Pass *branches* (from `local_branches`) to avoid a probe per candidate."""
    if branches is None:
        branches = local_branches(repo_root)
    candidates = [configured] if configured else []
    candidates += ["main", "master"]
    for name in candidates:
        if name and name in branches:
            return name
    head = worktrees._run_git(repo_root, "symbolic-ref", "--short", "-q", "HEAD", check=False)
    name = head.stdout.strip() if head.returncode == 0 else ""
    return name or None


def _parse_raw_and_numstat(raw: str):
    """Parse the output of one `git diff --raw --numstat -z`: the raw records (`:modes shas S`
    then the path, or both paths for a rename) and the numstat records (`added<TAB>removed<TAB>path`,
    the path empty for a rename with both names following). Fields are consumed record by record,
    so a path that looks like either kind is never mistaken for one.
    Returns (files in raw order, path -> (added, removed, binary))."""
    fields = raw.split("\0")
    files: List[ChangedFile] = []
    counts: dict = {}
    i = 0
    while i < len(fields):
        entry = fields[i]
        if not entry:
            i += 1
            continue
        if entry.startswith(":"):
            letter = entry.rsplit(" ", 1)[-1][:1]
            if letter in ("R", "C"):
                if i + 2 >= len(fields):
                    break
                files.append(ChangedFile(path=fields[i + 2], status="R", old_path=fields[i + 1]))
                i += 3
            else:
                if i + 1 >= len(fields):
                    break
                status = letter if letter in _STATUS_LETTERS else "M"
                files.append(
                    ChangedFile(path=fields[i + 1], status="M" if status == "T" else status)
                )
                i += 2
            continue
        parts = entry.split("\t", 2)
        if len(parts) < 3:
            i += 1
            continue
        added, removed, path = parts
        if path == "":  # a rename: the old and new names follow as their own fields
            if i + 2 >= len(fields):
                break
            path = fields[i + 2]
            i += 3
        else:
            i += 1
        binary = added == "-" and removed == "-"
        counts[path] = (0 if binary else int(added), 0 if binary else int(removed), binary)
    return files, counts


def parallel(*calls):
    """Run independent blocking git reads at once (each is its own process), keeping the
    caller's context so trace spans still attach. Results come back in call order."""
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = [pool.submit(contextvars.copy_context().run, call) for call in calls]
        return [f.result() for f in futures]


def _files(repo_root: Path, command: List[str], scope_args: List[str]) -> List[ChangedFile]:
    """One git process per scope, however many files: statuses and line counts together."""
    out = worktrees._run_git(repo_root, *command, "--raw", "--numstat", "-M", "-z", *scope_args)
    files, counts = _parse_raw_and_numstat(out.stdout)
    for entry in files:
        entry.added, entry.removed, entry.binary = counts.get(entry.path, (0, 0, False))
    return sorted(files, key=lambda f: f.path)


def turn_files(repo_root: Path, sha: str) -> List[ChangedFile]:
    """The files one commit changed. `--root` so a branch's first commit answers too."""
    return _files(repo_root, ["diff-tree", "-r", "--root", "--no-commit-id"], [sha])


def branch_files(repo_root: Path, base: str, branch: str) -> List[ChangedFile]:
    return _files(repo_root, ["diff"], [f"{base}...{branch}"])


def uncommitted_paths(checkout: Path) -> List[str]:
    """Paths changed in *checkout* and not yet committed, sorted. Untracked files included."""
    result = worktrees._run_git(
        checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all", check=False
    )
    if result.returncode != 0:
        return []
    paths: List[str] = []
    fields = result.stdout.split("\0")
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in ("R", "C"):
            i += 1  # the rename's source follows as its own field
    return sorted(set(paths))


def _cut(text: str) -> Patch:
    lines = text.splitlines(keepends=True)
    if len(lines) <= MAX_PATCH_LINES:
        return Patch(patch=text, binary=False, truncated=False, total_lines=len(lines))
    return Patch(
        patch="".join(lines[:MAX_PATCH_LINES]),
        binary=False,
        truncated=True,
        total_lines=len(lines),
    )


def file_patch(
    repo_root: Path, *, path: str, sha: Optional[str], base: Optional[str], branch: str
) -> Patch:
    """One file's unified diff, for a turn commit (*sha*) or for the branch against *base*.

    A binary file has no body. A patch over `MAX_PATCH_LINES` lines is cut to its start.
    """
    if sha is not None:
        command = ["diff-tree", "-p", "-r", "--root", "--no-commit-id", "-M", sha, "--", path]
    else:
        command = ["diff", "-M", f"{base}...{branch}", "--", path]
    text = worktrees._run_git(repo_root, *command).stdout
    if (
        "\nBinary files " in text
        or text.startswith("Binary files ")
        or "\nGIT binary patch" in text
    ):
        return Patch(patch="", binary=True, truncated=False, total_lines=0)
    return _cut(text)
